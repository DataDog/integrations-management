# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Key Vault management for storing the Datadog API key.

Creates a Key Vault and stores the API key as a secret. The Terraform
module's `roles` sub-module grants the managed identity "Key Vault
Secrets User" access so scanner VMs can retrieve the key at runtime.
"""

import hashlib
import json
from time import sleep
from typing import Optional

from az_shared.execute_cmd import execute, execute_json
from common.shell import Cmd

from .errors import KeyVaultError
from .reporter import Reporter, AgentlessStep


API_KEY_SECRET_NAME = "datadog-api-key"


def get_key_vault_name(scanner_subscription: str) -> str:
    """Generate a deterministic, globally unique Key Vault name.

    Azure constraints:
      - 3–24 characters, alphanumeric and hyphens only
      - Must start with a letter
      - Must be globally unique across all of Azure
    """
    digest = hashlib.sha256(scanner_subscription.encode()).hexdigest()[:12]
    return f"datadog-{digest}"


def key_vault_exists(vault_name: str, resource_group: str) -> bool:
    """Check if a Key Vault exists in the resource group."""
    try:
        result = execute(
            Cmd(["az", "keyvault", "show"])
            .param("--name", vault_name)
            .param("--resource-group", resource_group),
            can_fail=True,
        )
        return bool(result)
    except Exception:
        return False


def _is_soft_deleted(vault_name: str, location: str) -> bool:
    """Check if a Key Vault exists in soft-deleted state."""
    try:
        result = execute(
            Cmd(["az", "keyvault", "show-deleted"])
            .param("--name", vault_name)
            .param("--location", location),
            can_fail=True,
        )
        return bool(result)
    except Exception:
        return False


def _recover_soft_deleted(vault_name: str) -> None:
    """Recover a soft-deleted Key Vault."""
    execute(
        Cmd(["az", "keyvault", "recover"])
        .param("--name", vault_name)
    )


def create_key_vault(
    vault_name: str,
    resource_group: str,
    location: str,
    subscription: str,
) -> None:
    """Create an Azure Key Vault for storing the Datadog API key.

    If a soft-deleted vault with the same name exists, recovers it
    instead of requiring a manual purge (which can take several minutes).

    Uses RBAC authorization (--enable-rbac-authorization) so that the
    Terraform roles module can grant access via role assignments rather
    than vault access policies.

    Raises:
        KeyVaultError: If the Key Vault cannot be created.
    """
    try:
        if _is_soft_deleted(vault_name, location):
            _recover_soft_deleted(vault_name)
            return

        execute(
            Cmd(["az", "keyvault", "create"])
            .param("--name", vault_name)
            .param("--resource-group", resource_group)
            .param("--location", location)
            .param("--subscription", subscription)
            .param("--enable-rbac-authorization", "true")
            .param("--retention-days", "7")
            .param_list("--tags", ["Datadog=true", "DatadogAgentlessScanner=true"])
        )
    except Exception as e:
        raise KeyVaultError(
            f"Failed to create Key Vault: {vault_name}",
            str(e),
        ) from e


def grant_current_user_secrets_officer(vault_name: str, subscription: str) -> None:
    """Grant the current user 'Key Vault Secrets Officer' on the vault.

    With RBAC-enabled Key Vaults, the creator doesn't automatically get
    data-plane access. We need this role to set/get secrets.

    Raises:
        KeyVaultError: If the role assignment fails.
    """
    try:
        user_object_id = execute(
            Cmd(["az", "ad", "signed-in-user", "show"])
            .param("--query", "id")
            .param("--output", "tsv")
        ).strip()

        vault_info = execute_json(
            Cmd(["az", "keyvault", "show"])
            .param("--name", vault_name)
        )
        vault_resource_id = vault_info["id"]

        # Check if assignment already exists to avoid errors on re-run
        existing = execute(
            Cmd(["az", "role", "assignment", "list"])
            .param("--assignee", user_object_id)
            .param("--role", "Key Vault Secrets Officer")
            .param("--scope", vault_resource_id)
            .param("--query", "length(@)")
            .param("--output", "tsv"),
            can_fail=True,
        )
        if existing.strip() not in ("", "0"):
            return

        execute(
            Cmd(["az", "role", "assignment", "create"])
            .param("--assignee-object-id", user_object_id)
            .param("--assignee-principal-type", "User")
            .param("--role", "Key Vault Secrets Officer")
            .param("--scope", vault_resource_id)
        )
    except KeyVaultError:
        raise
    except Exception as e:
        raise KeyVaultError(
            "Failed to grant Key Vault Secrets Officer role to current user",
            str(e),
        ) from e


def get_secret_value(vault_name: str) -> Optional[str]:
    """Get the current value of the API key secret.

    Retries on failure to handle Azure RBAC propagation delay after
    granting Key Vault Secrets Officer role.

    Returns:
        The secret value, or None if the secret doesn't exist.
    """
    cmd = (
        Cmd(["az", "keyvault", "secret", "show"])
        .param("--vault-name", vault_name)
        .param("--name", API_KEY_SECRET_NAME)
    )
    for attempt in range(RBAC_PROPAGATION_RETRIES):
        try:
            raw = execute(cmd, can_fail=True)
            if raw:
                data = json.loads(raw)
                return data.get("value")
            if attempt < RBAC_PROPAGATION_RETRIES - 1:
                print(f"      Waiting for role assignment to propagate ({RBAC_PROPAGATION_DELAY}s)...")
                sleep(RBAC_PROPAGATION_DELAY)
                continue
            return None
        except Exception:
            return None


RBAC_PROPAGATION_RETRIES = 6
RBAC_PROPAGATION_DELAY = 10  # seconds


def set_secret(vault_name: str, api_key: str) -> str:
    """Create or update the API key secret in Key Vault.

    Retries on failure to handle Azure RBAC propagation delay after
    granting Key Vault Secrets Officer role.

    Returns:
        The secret data-plane URL (https://<vault>.vault.azure.net/secrets/<name>/<version>).

    Raises:
        KeyVaultError: If the secret cannot be set after all retries.
    """
    cmd = (
        Cmd(["az", "keyvault", "secret", "set"])
        .param("--vault-name", vault_name)
        .param("--name", API_KEY_SECRET_NAME)
        .param("--value", api_key)
    )
    for attempt in range(RBAC_PROPAGATION_RETRIES):
        try:
            raw = execute(cmd, can_fail=True)
            if raw:
                data = json.loads(raw)
                return data["id"]
            if attempt < RBAC_PROPAGATION_RETRIES - 1:
                print(f"      Waiting for role assignment to propagate ({RBAC_PROPAGATION_DELAY}s)...")
                sleep(RBAC_PROPAGATION_DELAY)
                continue
        except Exception as e:
            raise KeyVaultError(
                f"Failed to store API key in Key Vault: {vault_name}",
                str(e),
            ) from e

    raise KeyVaultError(
        f"Failed to store API key in Key Vault: {vault_name}",
        "Timed out waiting for Key Vault RBAC role assignment to propagate.\n"
        "Please wait a few minutes and re-run the command.",
    )


def get_secret_resource_id(vault_name: str, resource_group: str) -> str:
    """Get the ARM resource ID for the API key secret (versionless).

    The roles module expects a resource ID like:
    /subscriptions/.../resourceGroups/.../providers/Microsoft.KeyVault/vaults/<vault>/secrets/<name>

    Raises:
        KeyVaultError: If the vault info cannot be retrieved.
    """
    try:
        vault_info = execute_json(
            Cmd(["az", "keyvault", "show"])
            .param("--name", vault_name)
            .param("--resource-group", resource_group)
        )
        vault_id = vault_info["id"]
        return f"{vault_id}/secrets/{API_KEY_SECRET_NAME}"
    except Exception as e:
        raise KeyVaultError(
            f"Failed to get Key Vault resource ID: {vault_name}",
            str(e),
        ) from e


def ensure_api_key_secret(
    config_api_key: str,
    vault_name: str,
    resource_group: str,
    location: str,
    subscription: str,
    reporter: Reporter,
) -> str:
    """Create or update the API key secret in Key Vault.

    If the Key Vault doesn't exist, creates it with RBAC authorization.
    If the secret doesn't exist or has a different value, creates/updates it.

    Args:
        config_api_key: Datadog API key to store.
        vault_name: Key Vault name.
        resource_group: Azure resource group name.
        location: Azure location for creating the vault.
        subscription: Azure subscription ID.
        reporter: Reporter for progress output.

    Returns:
        The ARM resource ID of the secret (versionless), for passing to
        the Terraform roles module as `api_key_secret_id`.

    Raises:
        KeyVaultError: If any Key Vault operation fails.
    """
    reporter.start_step("Storing API key in Key Vault", AgentlessStep.STORE_API_KEY)

    if not key_vault_exists(vault_name, resource_group):
        reporter.info(f"Creating Key Vault: {vault_name}")
        create_key_vault(vault_name, resource_group, location, subscription)
        reporter.info("Granting secrets access to current user...")
        grant_current_user_secrets_officer(vault_name, subscription)
        reporter.info(f"Storing API key secret: {API_KEY_SECRET_NAME}")
        set_secret(vault_name, config_api_key)
        reporter.success(f"API key stored in Key Vault: {vault_name}")
    else:
        reporter.info("Granting secrets access to current user...")
        grant_current_user_secrets_officer(vault_name, subscription)

        current_value = get_secret_value(vault_name)
        if current_value == config_api_key:
            reporter.success(f"API key secret exists (unchanged): {vault_name}/{API_KEY_SECRET_NAME}")
        else:
            reporter.info(f"Updating API key secret in {vault_name}...")
            set_secret(vault_name, config_api_key)
            reporter.success(f"API key secret updated: {vault_name}/{API_KEY_SECRET_NAME}")

    secret_resource_id = get_secret_resource_id(vault_name, resource_group)
    reporter.finish_step()
    return secret_resource_id
