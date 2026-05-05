# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Storage Account management for Terraform state backend.

Creates a Storage Account + blob container to store Terraform state.
The azurerm backend requires: storage_account_name, container_name, key.
"""

import hashlib
import json
import subprocess
import time
from typing import Optional

from az_shared.execute_cmd import execute
from common.shell import Cmd

from .config import Config
from .errors import StorageAccountError
from .reporter import Reporter, AgentlessStep


CONTAINER_NAME = "tfstate"
BLOB_KEY = "datadog-agentless.tfstate"
STORAGE_BLOB_DATA_CONTRIBUTOR = "Storage Blob Data Contributor"
RBAC_PROPAGATION_RETRIES = 6
RBAC_PROPAGATION_DELAY = 10


def get_storage_account_name(scanner_subscription: str) -> str:
    """Generate a deterministic, globally unique storage account name.

    Azure constraints:
      - 3–24 characters, lowercase letters and digits only
      - Must be globally unique across all of Azure

    We use a truncated SHA-256 of the subscription ID to keep it short
    and deterministic (same subscription always gets the same name).
    """
    digest = hashlib.sha256(scanner_subscription.encode()).hexdigest()[:12]
    return f"datadog{digest}"


def storage_account_exists(
    account_name: str,
    resource_group: str,
    subscription: Optional[str] = None,
) -> bool:
    """Check if a Storage Account exists in the resource group.

    Pass ``subscription`` so the check uses the correct subscription when the
    Azure CLI default account differs (e.g. Cloud Shell).
    """
    try:
        cmd = (
            Cmd(["az", "storage", "account", "show"])
            .param("--name", account_name)
            .param("--resource-group", resource_group)
        )
        if subscription:
            cmd = cmd.param("--subscription", subscription)
        result = execute(cmd, can_fail=True)
        return bool(result)
    except Exception:
        return False


def find_storage_account_rg(account_name: str, subscription: str) -> Optional[str]:
    """Return the resource group containing a Storage Account, or None.

    Storage Account names are unique within a subscription, so ``az storage
    account show`` without ``--resource-group`` finds it wherever it lives.
    Used by the deploy preflight to detect the "user re-runs with a different
    SCANNER_RESOURCE_GROUP" case before any mutations: the deterministic SA
    name is shared across runs but the SA can only live in one RG.
    """
    try:
        raw = execute(
            Cmd(["az", "storage", "account", "show"])
            .param("--name", account_name)
            .param("--subscription", subscription)
            .param("--query", "resourceGroup")
            .param("--output", "tsv"),
            can_fail=True,
        )
        return (raw or "").strip() or None
    except Exception:
        return None


def create_storage_account(
    account_name: str,
    resource_group: str,
    location: str,
    subscription: str,
) -> None:
    """Create an Azure Storage Account for Terraform state.

    Security features:
    - Standard_LRS replication (locally redundant, cheapest)
    - Blob-only access (no file/queue/table)
    - HTTPS-only transport
    - TLS 1.2 minimum

    Raises:
        StorageAccountError: If the account cannot be created.
    """
    try:
        execute(
            Cmd(["az", "storage", "account", "create"])
            .param("--name", account_name)
            .param("--resource-group", resource_group)
            .param("--location", location)
            .param("--subscription", subscription)
            .param("--sku", "Standard_LRS")
            .param("--kind", "StorageV2")
            .param("--min-tls-version", "TLS1_2")
            .param("--allow-blob-public-access", "false")
            .param_list("--tags", ["Datadog=true", "DatadogAgentlessScanner=true"])
        )
    except Exception as e:
        raise StorageAccountError(
            f"Failed to create storage account: {account_name}",
            str(e),
        ) from e


def container_exists(account_name: str) -> bool:
    """Check if the tfstate blob container exists."""
    try:
        result = execute(
            Cmd(["az", "storage", "container", "show"])
            .param("--name", CONTAINER_NAME)
            .param("--account-name", account_name)
            .param("--auth-mode", "login"),
            can_fail=True,
        )
        return bool(result)
    except Exception:
        return False


def create_container(account_name: str) -> None:
    """Create the tfstate blob container.

    Raises:
        StorageAccountError: If the container cannot be created.
    """
    try:
        execute(
            Cmd(["az", "storage", "container", "create"])
            .param("--name", CONTAINER_NAME)
            .param("--account-name", account_name)
            .param("--auth-mode", "login")
        )
    except Exception as e:
        raise StorageAccountError(
            f"Failed to create blob container '{CONTAINER_NAME}' in {account_name}",
            str(e),
        ) from e


def grant_current_user_blob_data_contributor(account_name: str, resource_group: str) -> bool:
    """Grant the current user 'Storage Blob Data Contributor' on the storage account.

    The azurerm TF backend with `use_azuread_auth = true` requires
    data-plane access. The control-plane Owner/Contributor role is
    not sufficient for blob operations.

    Returns:
        True if a new role assignment was created (caller should wait
        for RBAC propagation), False if the role already existed.

    Raises:
        StorageAccountError: If the role assignment fails.
    """
    try:
        user_object_id = execute(
            Cmd(["az", "ad", "signed-in-user", "show"])
            .param("--query", "id")
            .param("--output", "tsv")
        ).strip()

        account_info_raw = execute(
            Cmd(["az", "storage", "account", "show"])
            .param("--name", account_name)
            .param("--resource-group", resource_group)
        )
        account_id = json.loads(account_info_raw)["id"]

        existing = execute(
            Cmd(["az", "role", "assignment", "list"])
            .param("--assignee", user_object_id)
            .param("--role", STORAGE_BLOB_DATA_CONTRIBUTOR)
            .param("--scope", account_id)
            .param("--query", "length(@)")
            .param("--output", "tsv"),
            can_fail=True,
        )
        if existing.strip() not in ("", "0"):
            return False

        execute(
            Cmd(["az", "role", "assignment", "create"])
            .param("--assignee-object-id", user_object_id)
            .param("--assignee-principal-type", "User")
            .param("--role", STORAGE_BLOB_DATA_CONTRIBUTOR)
            .param("--scope", account_id)
        )
        return True
    except StorageAccountError:
        raise
    except Exception as e:
        raise StorageAccountError(
            "Failed to grant Storage Blob Data Contributor role to current user",
            str(e),
        ) from e


def wait_for_blob_access(account_name: str, reporter: Reporter) -> None:
    """Wait for Storage Blob Data Contributor role to propagate.

    Probes actual blob data-plane access instead of sleeping a fixed
    duration. Listing containers with --auth-mode login exercises the
    same Azure AD path that Terraform will use.

    Uses subprocess directly instead of execute() to avoid noisy
    log.error output on every expected retry attempt.
    """
    probe_cmd = str(
        Cmd(["az", "storage", "container", "list"])
        .param("--account-name", account_name)
        .param("--auth-mode", "login")
        .param("--query", "length(@)")
        .param("--output", "tsv")
    )

    for attempt in range(RBAC_PROPAGATION_RETRIES):
        result = subprocess.run(probe_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return

        remaining = RBAC_PROPAGATION_RETRIES - attempt - 1
        if remaining > 0:
            reporter.info(
                f"Waiting for blob data access to propagate ({RBAC_PROPAGATION_DELAY}s)..."
            )
            time.sleep(RBAC_PROPAGATION_DELAY)

    reporter.info("Role propagation timeout — proceeding (Terraform will retry if needed)")


def resource_group_exists(resource_group: str, subscription: str) -> bool:
    """Check whether a resource group exists in the subscription."""
    try:
        result = execute(
            Cmd(["az", "group", "show"])
            .param("--name", resource_group)
            .param("--subscription", subscription),
            can_fail=True,
        )
        return bool(result)
    except Exception:
        return False


def ensure_resource_group(resource_group: str, location: str, subscription: str) -> None:
    """Create the resource group if it doesn't exist.

    Raises:
        StorageAccountError: If the resource group cannot be created.
    """
    if resource_group_exists(resource_group, subscription):
        return

    try:
        execute(
            Cmd(["az", "group", "create"])
            .param("--name", resource_group)
            .param("--location", location)
            .param("--subscription", subscription)
            .param_list("--tags", ["Datadog=true", "DatadogAgentlessScanner=true"])
        )
    except Exception as e:
        raise StorageAccountError(
            f"Failed to create resource group: {resource_group}",
            str(e),
        ) from e


def prepare_storage_account(config: Config, reporter: Reporter) -> tuple[str, bool]:
    """Ensure the Terraform-state Storage Account exists and the current user
    has Storage Blob Data Contributor on it.

    Splitting this out from ``ensure_state_storage`` lets the orchestrator
    run the Storage Account and Key Vault control-plane work in parallel
    and share a single RBAC propagation wait. Caller is responsible for:

    * waiting for the role to propagate when the returned ``role_created``
      is ``True``;
    * creating the blob container afterwards via
      :func:`finalize_storage_container` (the container is data-plane and
      requires the role to have propagated).

    Returns ``(account_name, role_created)``.
    """
    if config.state_storage_account:
        account_name = config.state_storage_account
        if not storage_account_exists(
            account_name, config.resource_group, config.scanner_subscription
        ):
            reporter.fatal(
                f"Custom storage account does not exist: {account_name}",
                f"Create the storage account in resource group '{config.resource_group}' first,\n"
                "or remove TF_STATE_STORAGE_ACCOUNT to use the default.",
            )
        reporter.success(f"Using custom storage account: {account_name}")
    else:
        account_name = get_storage_account_name(config.scanner_subscription)
        if storage_account_exists(
            account_name, config.resource_group, config.scanner_subscription
        ):
            reporter.success(f"Using existing storage account: {account_name}")
        else:
            reporter.info(f"Creating storage account: {account_name}")
            create_storage_account(
                account_name,
                config.resource_group,
                config.locations[0],
                config.scanner_subscription,
            )
            reporter.success(f"Created storage account: {account_name}")

    reporter.info("Granting blob data access to current user...")
    role_created = grant_current_user_blob_data_contributor(account_name, config.resource_group)
    return account_name, role_created


def finalize_storage_container(account_name: str, reporter: Reporter) -> None:
    """Create the tfstate blob container if missing.

    Must run after the current user's Storage Blob Data Contributor role
    has propagated to the blob data plane (otherwise this fails with
    AuthorizationPermissionMismatch).
    """
    if not container_exists(account_name):
        reporter.info(f"Creating blob container: {CONTAINER_NAME}")
        create_container(account_name)


def ensure_state_storage(config: Config, reporter: Reporter) -> str:
    """Ensure the Terraform state storage infrastructure exists.

    Sequential wrapper around :func:`prepare_storage_account` +
    :func:`wait_for_blob_access` + :func:`finalize_storage_container`.
    Kept for callers that want to provision state storage independently
    of the Key Vault (the deploy command goes through the parallel
    orchestrator in ``main.py`` instead).
    """
    reporter.start_step("Setting up Terraform state storage", AgentlessStep.CREATE_STATE_STORAGE)

    if not config.state_storage_account:
        ensure_resource_group(
            config.resource_group, config.locations[0], config.scanner_subscription
        )

    account_name, role_created = prepare_storage_account(config, reporter)

    if role_created:
        wait_for_blob_access(account_name, reporter)

    finalize_storage_container(account_name, reporter)

    reporter.finish_step()
    return account_name
