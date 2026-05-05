# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Key Vault management for storing the Datadog API key.

Creates a Key Vault and stores the API key as a secret. The Terraform
module's `roles` sub-module grants the managed identity "Key Vault
Secrets User" access so scanner VMs can retrieve the key at runtime.
"""

import hashlib
import json
import subprocess
from time import sleep
from typing import Optional

from az_shared.execute_cmd import execute, execute_json
from common.shell import Cmd

from .errors import KeyVaultError
from .reporter import Reporter, AgentlessStep


API_KEY_SECRET_NAME = "datadog-api-key"

RBAC_PROPAGATION_RETRIES = 6
RBAC_PROPAGATION_DELAY = 10  # seconds


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


def _get_soft_deleted_vault(vault_name: str, location: str) -> Optional[dict]:
    """Return the soft-deleted vault descriptor, or None if not soft-deleted.

    The descriptor exposes ``properties.vaultId`` from which the original
    resource group can be recovered.
    """
    try:
        raw = execute(
            Cmd(["az", "keyvault", "show-deleted"])
            .param("--name", vault_name)
            .param("--location", location),
            can_fail=True,
        )
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _resource_group_from_arm_id(arm_id: str) -> Optional[str]:
    """Extract the resource group segment from an ARM resource ID.

    Format: ``/subscriptions/<sub>/resourceGroups/<rg>/providers/...``.
    Case-insensitive on the segment name (Azure mixes ``resourceGroups``
    and ``resourcegroups`` depending on the API).
    """
    if not arm_id:
        return None
    parts = arm_id.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1] or None
    return None


def _soft_delete_rg_mismatch_detail(
    *,
    vault_name: str,
    location: str,
    original_rg: str,
    requested_rg: str,
) -> str:
    return (
        f"A soft-deleted Datadog Key Vault named '{vault_name}' exists in\n"
        f"location '{location}', originally in resource group:\n"
        f"  - {original_rg}\n"
        f"\n"
        f"It cannot be recovered into a different resource group ('{requested_rg}').\n"
        f"\n"
        f"You can:\n"
        f"  - Re-run with SCANNER_RESOURCE_GROUP={original_rg} to recover it there, OR\n"
        f"  - Purge it (irreversible — deletes the secret) and let this run\n"
        f"    create a new vault:\n"
        f"      az keyvault purge --name {vault_name} --location {location}"
    )


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
    A soft-deleted vault can only be recovered into its *original*
    resource group, so we refuse to recover one whose original RG
    differs from ``resource_group`` and tell the user how to proceed
    (re-run targeting the original RG, or purge).

    Uses RBAC authorization (--enable-rbac-authorization) so that the
    Terraform roles module can grant access via role assignments rather
    than vault access policies.

    Raises:
        KeyVaultError: If the Key Vault cannot be created.
    """
    deleted = _get_soft_deleted_vault(vault_name, location)
    if deleted is not None:
        original_vault_id = (deleted.get("properties") or {}).get("vaultId") or ""
        original_rg = _resource_group_from_arm_id(original_vault_id)
        if original_rg and original_rg != resource_group:
            raise KeyVaultError(
                "Soft-deleted Key Vault belongs to a different resource group",
                _soft_delete_rg_mismatch_detail(
                    vault_name=vault_name,
                    location=location,
                    original_rg=original_rg,
                    requested_rg=resource_group,
                ),
            )
        try:
            _recover_soft_deleted(vault_name)
            return
        except Exception as e:
            raise KeyVaultError(
                f"Failed to recover soft-deleted Key Vault: {vault_name}",
                str(e),
            ) from e

    try:
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


def grant_current_user_secrets_officer(vault_name: str, subscription: str) -> bool:
    """Grant the current user 'Key Vault Secrets Officer' on the vault.

    With RBAC-enabled Key Vaults, the creator doesn't automatically get
    data-plane access. We need this role to set/get secrets.

    Returns:
        True if a new role assignment was created (caller should wait
        for RBAC propagation), False if the role already existed.

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
            return False

        execute(
            Cmd(["az", "role", "assignment", "create"])
            .param("--assignee-object-id", user_object_id)
            .param("--assignee-principal-type", "User")
            .param("--role", "Key Vault Secrets Officer")
            .param("--scope", vault_resource_id)
        )
        return True
    except KeyVaultError:
        raise
    except Exception as e:
        raise KeyVaultError(
            "Failed to grant Key Vault Secrets Officer role to current user",
            str(e),
        ) from e


def wait_for_secret_access(vault_name: str, reporter: Reporter) -> None:
    """Wait for Key Vault Secrets Officer role to propagate to the data plane.

    Probes the actual data-plane secret listing instead of sleeping a fixed
    duration; ``--query length(@)`` makes the response trivially small.
    Uses subprocess directly (rather than ``execute()``) to avoid noisy
    log.error output on every expected retry while RBAC is propagating.
    """
    probe_cmd = str(
        Cmd(["az", "keyvault", "secret", "list"])
        .param("--vault-name", vault_name)
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
                f"Waiting for Key Vault data access to propagate ({RBAC_PROPAGATION_DELAY}s)..."
            )
            sleep(RBAC_PROPAGATION_DELAY)

    reporter.info(
        "Key Vault role propagation timeout — proceeding (set_secret will retry if needed)"
    )


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


def prepare_key_vault(
    vault_name: str,
    resource_group: str,
    location: str,
    subscription: str,
    reporter: Reporter,
) -> bool:
    """Ensure the Key Vault exists and the current user has Secrets Officer
    on it.

    Splitting this out from ``ensure_api_key_secret`` lets the orchestrator
    run Key Vault preparation in parallel with Storage Account setup and
    share a single RBAC propagation wait. Caller is responsible for waiting
    for the role to propagate when the returned ``role_created`` is ``True``
    before invoking :func:`set_or_update_secret`.

    Returns ``role_created``.
    """
    if not key_vault_exists(vault_name, resource_group):
        reporter.info(f"Creating Key Vault: {vault_name}")
        create_key_vault(vault_name, resource_group, location, subscription)

    reporter.info("Granting secrets access to current user...")
    return grant_current_user_secrets_officer(vault_name, subscription)


def set_or_update_secret(
    config_api_key: str,
    vault_name: str,
    resource_group: str,
    reporter: Reporter,
) -> str:
    """Create or update the API key secret and return the versionless secret
    resource ID.

    Caller must ensure the current user's Secrets Officer role has
    propagated to the data plane (via :func:`wait_for_secret_access` or
    the orchestrator's combined wait); the underlying ``set_secret`` and
    ``get_secret_value`` helpers still retry defensively if propagation
    is incomplete.
    """
    current_value = get_secret_value(vault_name)
    if current_value == config_api_key:
        reporter.success(
            f"API key secret exists (unchanged): {vault_name}/{API_KEY_SECRET_NAME}"
        )
    else:
        if current_value is None:
            reporter.info(f"Storing API key secret: {API_KEY_SECRET_NAME}")
        else:
            reporter.info(f"Updating API key secret in {vault_name}...")
        set_secret(vault_name, config_api_key)
        reporter.success(f"API key secret stored: {vault_name}/{API_KEY_SECRET_NAME}")

    return get_secret_resource_id(vault_name, resource_group)


def ensure_api_key_secret(
    config_api_key: str,
    vault_name: str,
    resource_group: str,
    location: str,
    subscription: str,
    reporter: Reporter,
) -> str:
    """Create or update the API key secret in Key Vault.

    Sequential wrapper around :func:`prepare_key_vault` +
    :func:`wait_for_secret_access` + :func:`set_or_update_secret`.
    Kept for callers that want to provision the Key Vault independently
    of the state Storage Account (the deploy command goes through the
    parallel orchestrator in ``main.py`` instead).
    """
    reporter.start_step("Storing API key in Key Vault", AgentlessStep.STORE_API_KEY)

    role_created = prepare_key_vault(
        vault_name, resource_group, location, subscription, reporter
    )

    if role_created:
        wait_for_secret_access(vault_name, reporter)

    secret_resource_id = set_or_update_secret(
        config_api_key, vault_name, resource_group, reporter
    )
    reporter.finish_step()
    return secret_resource_id
