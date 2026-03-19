# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Storage Account management for Terraform state backend.

Creates a Storage Account + blob container to store Terraform state.
The azurerm backend requires: storage_account_name, container_name, key.
"""

import hashlib

from az_shared.execute_cmd import execute, execute_json
from common.shell import Cmd

from .config import Config
from .errors import StorageAccountError
from .reporter import Reporter, AgentlessStep


CONTAINER_NAME = "tfstate"
BLOB_KEY = "datadog-agentless.tfstate"


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


def storage_account_exists(account_name: str, resource_group: str) -> bool:
    """Check if a Storage Account exists in the resource group."""
    try:
        execute(
            Cmd(["az", "storage", "account", "show"])
            .param("--name", account_name)
            .param("--resource-group", resource_group),
            can_fail=True,
        )
        return True
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
            .param("--tags", "Datadog=true", "DatadogAgentlessScanner=true")
        )
    except Exception as e:
        raise StorageAccountError(
            f"Failed to create storage account: {account_name}",
            str(e),
        ) from e


def container_exists(account_name: str) -> bool:
    """Check if the tfstate blob container exists."""
    try:
        result = execute_json(
            Cmd(["az", "storage", "container", "show"])
            .param("--name", CONTAINER_NAME)
            .param("--account-name", account_name)
            .param("--auth-mode", "login")
        )
        return result is not None
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


def ensure_resource_group(resource_group: str, location: str, subscription: str) -> None:
    """Create the resource group if it doesn't exist.

    Raises:
        StorageAccountError: If the resource group cannot be created.
    """
    result = execute(
        Cmd(["az", "group", "show"])
        .param("--name", resource_group)
        .param("--subscription", subscription),
        can_fail=True,
    )
    if result:
        return

    try:
        execute(
            Cmd(["az", "group", "create"])
            .param("--name", resource_group)
            .param("--location", location)
            .param("--subscription", subscription)
            .param("--tags", "Datadog=true", "DatadogAgentlessScanner=true")
        )
    except Exception as e:
        raise StorageAccountError(
            f"Failed to create resource group: {resource_group}",
            str(e),
        ) from e


def ensure_state_storage(config: Config, reporter: Reporter) -> str:
    """Ensure the Terraform state storage infrastructure exists.

    Creates (if needed):
    1. Resource group
    2. Storage Account
    3. Blob container

    If config.state_storage_account is set, uses that account (must already exist).
    Otherwise, creates a default account named with a hash of the subscription ID.

    Returns:
        The storage account name.

    Raises:
        StorageAccountError: If any storage operation fails.
    """
    reporter.start_step("Setting up Terraform state storage", AgentlessStep.CREATE_STATE_STORAGE)

    if config.state_storage_account:
        account_name = config.state_storage_account
        if not storage_account_exists(account_name, config.resource_group):
            reporter.fatal(
                f"Custom storage account does not exist: {account_name}",
                f"Create the storage account in resource group '{config.resource_group}' first,\n"
                "or remove TF_STATE_STORAGE_ACCOUNT to use the default.",
            )
        reporter.success(f"Using custom storage account: {account_name}")
    else:
        account_name = get_storage_account_name(config.scanner_subscription)

        # Ensure the resource group exists before creating the storage account
        ensure_resource_group(config.resource_group, config.locations[0], config.scanner_subscription)

        if storage_account_exists(account_name, config.resource_group):
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

    # Ensure the blob container exists
    if not container_exists(account_name):
        reporter.info(f"Creating blob container: {CONTAINER_NAME}")
        create_container(account_name)

    reporter.finish_step()
    return account_name
