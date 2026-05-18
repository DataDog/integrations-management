# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Storage Account management for Terraform state backend.

Creates a Storage Account + blob container to store Terraform state.
The azurerm backend requires: storage_account_name, container_name, key.
"""

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

# Marker tag applied by the setup script (and by the Terraform module) to
# every resource it creates. Used by tag-based discovery to find existing
# Agentless Scanner installations without consulting a central registry.
# Kept in sync with `terraform-module-datadog-agentless-scanner/azure`
# (modules/{resource-group,virtual-machine,virtual-network,managed-identity}).
AGENTLESS_TAG_KEY = "DatadogAgentlessScanner"
AGENTLESS_TAG_VALUE = "true"


def get_storage_account_name(install_id: str) -> str:
    """Build the storage account name from a per-install identifier.

    Azure constraints:
      - 3–24 characters, lowercase letters and digits only
      - Must be globally unique across all of Azure

    ``install_id`` is a 12-char lowercase hex string (see
    :func:`azure_agentless_setup.config.compute_install_id`); prefixed with
    ``datadog`` we land at 19 chars total, well inside the limit, and two
    deploys with different resource groups in the same scanner subscription
    resolve to different names — which is what makes future multi-install
    per subscription possible without storage-account name collisions.
    """
    return f"datadog{install_id}"


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


def _signed_in_user_object_id() -> Optional[str]:
    """Best-effort lookup of the current user's Entra object ID.

    Returns ``None`` on failure so error messages remain useful even when
    we cannot fetch the ID. Reading ``signed-in-user`` only needs the
    default Microsoft Graph scope every authenticated user already has.
    """
    try:
        raw = execute(
            Cmd(["az", "ad", "signed-in-user", "show"])
            .param("--query", "id")
            .param("--output", "tsv"),
            can_fail=True,
        )
    except Exception:
        return None
    return (raw or "").strip() or None


def ensure_current_user_blob_data_access(
    account_name: str,
    resource_group: str,
    subscription: str,
    reporter: Reporter,
) -> None:
    """Grant the current user 'Storage Blob Data Contributor' on
    ``account_name`` and wait for RBAC propagation, with a focused error
    when self-grant is not possible.

    Callers about to do blob data-plane reads or writes (deploy's
    metadata probe, destroy's metadata read) must invoke this *before*
    the first blob call so they don't surface Azure's opaque "you do not
    have the required permissions" error.

    Azure separates control-plane RBAC (Owner / Contributor on the
    subscription, the resource group, or the storage account itself)
    from data-plane RBAC. Owner on the resource group manages the
    Storage Account but does NOT read or write the blobs inside it -
    that's reserved for the ``Storage Blob Data *`` roles.

    Idempotent: returns silently when the role already exists.
    """
    try:
        role_created = grant_current_user_blob_data_contributor(
            account_name, resource_group
        )
    except StorageAccountError as e:
        object_id = _signed_in_user_object_id() or "<your-object-id>"
        raise StorageAccountError(
            "Cannot access existing deployment's Terraform state",
            f"An Agentless Scanner deployment already exists in resource group\n"
            f"'{resource_group}', and the current user cannot self-grant\n"
            f"'Storage Blob Data Contributor' on its state Storage Account\n"
            f"'{account_name}'.\n"
            f"\n"
            f"Note: Azure separates control-plane RBAC (Owner / Contributor on\n"
            f"a resource group) from data-plane RBAC. Owner on the resource\n"
            f"group is NOT sufficient to read or write blobs in a Storage\n"
            f"Account inside it.\n"
            f"\n"
            f"Ask a subscription Owner (typically the user who originally\n"
            f"deployed) to run, in the scanner subscription:\n"
            f"\n"
            f"  az role assignment create \\\n"
            f"    --assignee {object_id} \\\n"
            f"    --role 'Storage Blob Data Contributor' \\\n"
            f"    --scope $(az storage account show \\\n"
            f"      --name {account_name} \\\n"
            f"      --resource-group {resource_group} \\\n"
            f"      --subscription {subscription} \\\n"
            f"      --query id -o tsv)\n"
            f"\n"
            f"Then re-run.\n"
            f"\n"
            f"Underlying error: {e.detail or e.message}",
        ) from e

    if role_created:
        wait_for_blob_access(account_name, reporter)


# Markers indicating the blob-data-plane responded with a clean 404 -
# i.e. the request was authorized and merely targeted a blob or
# container that does not exist yet. ``wait_for_blob_access`` treats
# these as a success signal because they still demonstrate that the
# caller has data-plane reachability.
_BLOB_PROBE_BENIGN_MARKERS = (
    "blobnotfound",
    "containernotfound",
    "resourcenotfound",
    "the specified blob does not exist",
    "the specified container does not exist",
    "the specified resource does not exist",
)


def wait_for_blob_access(account_name: str, reporter: Reporter) -> None:
    """Wait for Storage Blob Data Contributor role to propagate.

    Probes the exact same data-plane API the wizard will hit next -
    ``az storage blob show config.json`` - and tolerates only the
    ``BlobNotFound`` / ``ContainerNotFound`` family of errors as
    success signals (the metadata blob is missing on first deploys but
    the response still proves data-plane reachability). Any other
    failure - typically ``AuthorizationPermissionMismatch`` - is
    treated as "role not yet propagated" and retried.

    The previous probe (``az storage container list``) was unreliable
    on second-user-joining paths: some az CLI builds quietly returned
    an empty array with ``rc=0`` when the caller lacked the
    data-plane role (because the CLI silently re-authenticated with
    storage account keys harvested via the control plane), so the wait
    returned immediately and the subsequent metadata read failed with
    a confusing "permissions" error. Mirroring the exact downstream
    operation eliminates that gap.

    Uses subprocess directly instead of execute() so we can inspect
    stderr for the not-found markers and to avoid noisy log.error
    output on every expected retry attempt.
    """
    from .metadata import METADATA_BLOB

    probe_cmd = str(
        Cmd(["az", "storage", "blob", "show"])
        .param("--account-name", account_name)
        .param("--container-name", CONTAINER_NAME)
        .param("--name", METADATA_BLOB)
        .param("--auth-mode", "login")
        .param("--query", "properties.etag")
        .param("--output", "tsv")
    )

    for attempt in range(RBAC_PROPAGATION_RETRIES):
        result = subprocess.run(probe_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return

        stderr_lc = (result.stderr or "").lower()
        if any(marker in stderr_lc for marker in _BLOB_PROBE_BENIGN_MARKERS):
            return

        remaining = RBAC_PROPAGATION_RETRIES - attempt - 1
        if remaining > 0:
            reporter.info(
                f"Waiting for blob data access to propagate ({RBAC_PROPAGATION_DELAY}s)..."
            )
            time.sleep(RBAC_PROPAGATION_DELAY)

    reporter.info("Role propagation timeout, proceeding (Terraform will retry if needed)")


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


def find_agentless_resource_groups(scanner_subscription: str) -> list[str]:
    """List resource groups tagged as an Agentless Scanner deployment.

    Filters on the ``DatadogAgentlessScanner=true`` marker tag that the
    setup script applies on RG creation (and that the Terraform module
    re-applies to every resource it manages). Returns the bare RG names
    in deterministic order — typically zero or one entry today, since
    multi-install on a single scanner subscription is blocked.

    Failures (auth, throttling, network) are swallowed and treated as
    "no tagged RGs found": the caller falls back to the metadata blob
    and (in this release) the deterministic Storage Account lookup,
    which together still detect a previous install for the same RG name.
    Once those legacy nets are removed in a follow-up commit, this
    function will need to fail loudly instead.
    """
    try:
        raw = execute(
            Cmd(["az", "group", "list"])
            .param("--subscription", scanner_subscription)
            .param("--tag", f"{AGENTLESS_TAG_KEY}={AGENTLESS_TAG_VALUE}")
            .param("--query", "[].name")
            .param("--output", "tsv"),
            can_fail=True,
        )
    except Exception:
        return []
    return sorted({line.strip() for line in (raw or "").splitlines() if line.strip()})


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
        account_name = get_storage_account_name(config.install_id)
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
