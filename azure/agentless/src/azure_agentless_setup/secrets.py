# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure Key Vault management for storing the Datadog API key.

Creates a Key Vault and stores the API key as a secret. The Terraform
module's `roles` sub-module grants the managed identity "Key Vault
Secrets User" access so scanner VMs can retrieve the key at runtime.
"""

import json
import subprocess
from time import sleep
from typing import Optional

from az_shared.errors import ResourceGroupNotFoundError, ResourceNotFoundError
from az_shared.execute_cmd import execute, execute_json
from common.shell import Cmd

from .errors import KeyVaultError, wrap_az_errors
from .rbac import grant_role_to_current_user
from .reporter import Reporter


API_KEY_SECRET_NAME = "datadog-api-key"

RBAC_PROPAGATION_RETRIES = 6
RBAC_PROPAGATION_DELAY = 10  # seconds

# How long to poll for the vault to appear after ``az keyvault create``
# reports ``ResourceNotFound``. The az CLI issues the PUT, then a GET to
# return the new resource - if ARM has not propagated the resource yet
# (very common right after a purge of the same name), the GET 404s and
# the CLI surfaces ``ResourceNotFound`` even though the create succeeded.
# 12 * 5s = 60s; in practice the resource appears within 10-20s.
POST_CREATE_VISIBILITY_RETRIES = 12
POST_CREATE_VISIBILITY_DELAY = 5  # seconds


def get_key_vault_name(install_id: str) -> str:
    """Build the Key Vault name from a per-install identifier.

    Azure constraints:
      - 3–24 characters, alphanumeric and hyphens only
      - Must start with a letter
      - Must be globally unique across all of Azure

    Mirrors :func:`state_storage.get_storage_account_name`: 12-char
    install_id prefixed with ``datadog-`` (8 chars) lands at 20 chars,
    well inside the 24-char limit, and the install_id changing with
    the resource group keeps multi-install per scanner subscription
    free of name collisions.
    """
    return f"datadog-{install_id}"


def key_vault_exists(
    vault_name: str,
    resource_group: str,
    subscription: Optional[str] = None,
) -> bool:
    """Check if a Key Vault exists in the resource group.

    Pass ``subscription`` so the check uses the correct subscription when
    the Azure CLI default account differs (e.g. Cloud Shell). The destroy
    flow does not run ``set_subscription`` and therefore must always pass
    it; the deploy flow already pinned the default in preflight, so the
    parameter is optional for backward compatibility.

    Only the two ``*NotFound`` errors are treated as "missing"; auth /
    throttling / network failures propagate so callers cannot silently
    miss an existing vault and either try to recreate it (yielding
    ``VaultAlreadyExists``) or skip cleanup on destroy.
    """
    cmd = (
        Cmd(["az", "keyvault", "show"])
        .param("--name", vault_name)
        .param("--resource-group", resource_group)
    )
    if subscription:
        cmd = cmd.param("--subscription", subscription)
    try:
        result = execute(cmd, can_fail=True)
    except (ResourceNotFoundError, ResourceGroupNotFoundError):
        return False
    return bool(result)


def _get_soft_deleted_vault(vault_name: str, subscription: str) -> Optional[dict]:
    """Return the soft-deleted vault descriptor, or None if not soft-deleted.

    Uses ``az keyvault list-deleted`` filtered by name (rather than the
    location-scoped ``show-deleted``) so the lookup is robust against:

      * the Cloud Shell user's default subscription differing from
        ``SCANNER_SUBSCRIPTION`` — ``show-deleted`` does not accept
        ``--subscription`` in older az CLI builds, which silently sent
        the query to the wrong subscription and returned "not found";
      * a previous deploy targeting a different location than the
        current run — ``show-deleted --location`` only matches the
        location the vault was originally parked in.

    The descriptor exposes ``properties.vaultId`` (resource group) and
    ``properties.location`` (recovery / purge location).
    """
    try:
        raw = execute(
            Cmd(["az", "keyvault", "list-deleted"])
            .param("--subscription", subscription)
            .param("--resource-type", "vault")
            .param("--query", f"[?name=='{vault_name}'] | [0]"),
            can_fail=True,
        )
    except Exception:
        return None
    if not raw or raw.strip() in ("", "null"):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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
    subscription: str,
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
        f"  - Purge it (irreversible, deletes the secret) and let this run\n"
        f"    create a new vault:\n"
        f"      az keyvault purge --name {vault_name} --location {location} \\\n"
        f"        --subscription {subscription}"
    )


def _vault_already_exists_detail(
    *, vault_name: str, location: str, subscription: str
) -> str:
    """Actionable message for the ``VaultAlreadyExists`` fallback.

    Triggered when ``_get_soft_deleted_vault`` returned nothing (typically
    because the current user lacks ``Microsoft.KeyVault/deletedVaults/read``
    on the subscription) but ``az keyvault create`` immediately rejected
    the name because Azure does have a soft-deleted vault with it.
    """
    return (
        f"A Key Vault named '{vault_name}' is already taken in subscription\n"
        f"{subscription}. The most common cause is a previous Datadog\n"
        f"Agentless Scanner deploy that was destroyed: Azure keeps the vault\n"
        f"in a soft-deleted state for the retention period.\n"
        f"\n"
        f"The setup script could not detect it automatically (usually a\n"
        f"missing 'Microsoft.KeyVault/deletedVaults/read' permission for\n"
        f"the current user on this subscription).\n"
        f"\n"
        f"To unblock, run one of:\n"
        f"  - az keyvault recover --name {vault_name} \\\n"
        f"      --subscription {subscription}\n"
        f"  - az keyvault purge --name {vault_name} --location {location} \\\n"
        f"      --subscription {subscription}\n"
        f"\n"
        f"Then re-run deploy. Alternatively, set SCANNER_RESOURCE_GROUP to a\n"
        f"different value to derive a fresh vault name."
    )


@wrap_az_errors(KeyVaultError, "Failed to recover soft-deleted Key Vault: {vault_name}")
def _recover_soft_deleted(vault_name: str, subscription: str) -> None:
    """Recover a soft-deleted Key Vault in ``subscription``.

    Passes ``--subscription`` so recovery runs against the scanner
    subscription even when the Cloud Shell user's default subscription
    differs.
    """
    execute(
        Cmd(["az", "keyvault", "recover"])
        .param("--name", vault_name)
        .param("--subscription", subscription)
    )


def soft_deleted_key_vault_exists(vault_name: str, subscription: str) -> bool:
    """Return whether a soft-deleted vault with this name exists.

    Thin presence-check wrapper over :func:`_get_soft_deleted_vault`
    for callers (currently destroy) that only need a boolean. Used to
    keep the retry path free of ``VaultAlreadyExists``: when a previous
    destroy ran ``az keyvault delete`` but failed at ``purge``, the
    live ``key_vault_exists`` lookup returns False while the name is
    still reserved by Azure as a soft-deleted vault.
    """
    return _get_soft_deleted_vault(vault_name, subscription) is not None


def purge_key_vault(vault_name: str, subscription: str) -> bool:
    """Permanently delete and purge a Key Vault in one step.

    Performs the full ``soft-delete -> purge`` sequence so the vault
    name is freed for immediate reuse. Without the purge step Azure
    keeps the vault reserved for its retention window (7 days for
    wizard-created vaults), which is the recurring root cause of
    ``VaultAlreadyExists`` on re-deploy.

    Idempotent on retry: if the vault is already soft-deleted (a
    previous destroy ran the delete step but failed at purge), the
    soft-delete call is skipped. ``az keyvault delete`` would
    otherwise raise ``ResourceNotFound`` and short-circuit the function
    before the purge step ever ran, leaving the name reserved
    indefinitely.

    The soft-delete step blocks until completion (no ``--no-wait``) so
    the purge call sees the vault in the soft-deleted state. The purge
    step discovers the original location via
    :func:`_get_soft_deleted_vault` (subscription-scoped,
    location-agnostic) and passes it explicitly because
    ``az keyvault purge`` is location-scoped.

    Returns ``False`` on any failure in either step. Callers in the
    destroy flow rely on this never raising so the wizard's last
    cleanup step does not crash a destroy that otherwise succeeded.
    """
    deleted = _get_soft_deleted_vault(vault_name, subscription)
    if deleted is None:
        try:
            execute(
                Cmd(["az", "keyvault", "delete"])
                .param("--name", vault_name)
                .param("--subscription", subscription)
            )
        except Exception:
            return False
        deleted = _get_soft_deleted_vault(vault_name, subscription)
        if deleted is None:
            return False

    location = (deleted.get("properties") or {}).get("location")
    if not location:
        return False

    try:
        execute(
            Cmd(["az", "keyvault", "purge"])
            .param("--name", vault_name)
            .param("--location", location)
            .param("--subscription", subscription)
        )
        return True
    except Exception:
        return False


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
    deleted = _get_soft_deleted_vault(vault_name, subscription)
    if deleted is not None:
        properties = deleted.get("properties") or {}
        original_vault_id = properties.get("vaultId") or ""
        original_rg = _resource_group_from_arm_id(original_vault_id)
        # Recovery / purge advice should point at the location the
        # soft-deleted vault is parked in, not the new deploy location.
        original_location = properties.get("location") or location
        if original_rg and original_rg != resource_group:
            raise KeyVaultError(
                "Soft-deleted Key Vault belongs to a different resource group",
                _soft_delete_rg_mismatch_detail(
                    vault_name=vault_name,
                    location=original_location,
                    subscription=subscription,
                    original_rg=original_rg,
                    requested_rg=resource_group,
                ),
            )
        _recover_soft_deleted(vault_name, subscription)
        return

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
    except ResourceNotFoundError as e:
        # The PUT issued by ``az keyvault create`` has succeeded, but
        # the CLI's follow-up GET 404'd because ARM has not propagated
        # the new resource yet. This is overwhelmingly the case when
        # re-creating a vault whose name was just purged in a prior
        # destroy. Poll for the resource to appear before declaring
        # failure - the create itself almost always landed.
        if _wait_for_vault_visible(vault_name, resource_group, subscription):
            return
        raise KeyVaultError(
            f"Failed to create Key Vault: {vault_name}",
            f"{str(e)}\n\n"
            f"Azure reported the resource is not visible after create.\n"
            f"This can happen when the vault name was recently purged.\n"
            f"Wait a couple of minutes and re-run, or verify manually:\n"
            f"  az keyvault show --name {vault_name} \\\n"
            f"    --resource-group {resource_group} --subscription {subscription}",
        ) from e
    except Exception as e:
        # Fallback for cases where ``_get_soft_deleted_vault`` returned
        # nothing (typically because the current user lacks
        # ``Microsoft.KeyVault/deletedVaults/read``) yet Azure refuses the
        # create because the vault name is occupied by a soft-deleted
        # vault. Match on the error code so we survive az CLI localisation.
        if "VaultAlreadyExists" in str(e):
            raise KeyVaultError(
                f"Key Vault name '{vault_name}' is already in use",
                _vault_already_exists_detail(
                    vault_name=vault_name,
                    location=location,
                    subscription=subscription,
                ),
            ) from e
        raise KeyVaultError(
            f"Failed to create Key Vault: {vault_name}",
            str(e),
        ) from e


def _wait_for_vault_visible(
    vault_name: str, resource_group: str, subscription: str
) -> bool:
    """Poll for ``vault_name`` to become visible after a create.

    Used only on the ``ResourceNotFound`` recovery path in
    :func:`create_key_vault` (see comment there). Returns ``True`` as
    soon as ``az keyvault show`` succeeds, or ``False`` after the full
    :data:`POST_CREATE_VISIBILITY_RETRIES` window elapses without the
    resource appearing.
    """
    print(
        f"Vault not yet visible to ARM, waiting up to "
        f"{POST_CREATE_VISIBILITY_RETRIES * POST_CREATE_VISIBILITY_DELAY}s "
        f"for the create to propagate..."
    )
    for _ in range(POST_CREATE_VISIBILITY_RETRIES):
        if key_vault_exists(vault_name, resource_group, subscription):
            return True
        sleep(POST_CREATE_VISIBILITY_DELAY)
    return False


def grant_current_user_secrets_officer(vault_name: str, subscription: str) -> bool:
    """Grant the current user 'Key Vault Secrets Officer' on the vault.

    With RBAC-enabled Key Vaults, the creator doesn't automatically get
    data-plane access. We need this role to set/get secrets.

    ``subscription`` must be the scanner subscription. Without
    ``--subscription`` on the inner ``az keyvault show`` /
    ``az role assignment`` calls, the Cloud Shell user's default sub
    would be used - which on the destroy path (no preflight
    ``set_subscription``) is frequently wrong, surfacing as a confusing
    ``ResourceNotFound``. Mirrors the same fix applied to the
    Storage Blob Data Contributor grant.

    Returns:
        True if a new role assignment was created (caller should wait
        for RBAC propagation), False if the role already existed.

    Raises:
        KeyVaultError: If the role assignment fails.
    """

    def lookup_vault_id() -> str:
        info = execute_json(
            Cmd(["az", "keyvault", "show"])
            .param("--name", vault_name)
            .param("--subscription", subscription)
        )
        return info["id"]

    return grant_role_to_current_user(
        role="Key Vault Secrets Officer",
        resource_id_lookup=lookup_vault_id,
        subscription=subscription,
        error_cls=KeyVaultError,
        error_message="Failed to grant Key Vault Secrets Officer role to current user",
    )


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
    """Return the current value of the API key secret, or ``None`` if it
    does not exist.

    Single-shot: callers must have already waited for Secrets Officer RBAC
    propagation (via :func:`wait_for_secret_access`) when the role was
    newly created. When the role pre-existed, propagation is implicit (the
    role has been live for the full propagation window already), so this
    avoids burning the old defensive 60s retry budget on every re-deploy.
    """
    try:
        raw = execute(
            Cmd(["az", "keyvault", "secret", "show"])
            .param("--vault-name", vault_name)
            .param("--name", API_KEY_SECRET_NAME),
            can_fail=True,
        )
    except Exception:
        return None
    if not raw:
        return None
    return json.loads(raw).get("value")


@wrap_az_errors(KeyVaultError, "Failed to store API key in Key Vault: {vault_name}")
def set_secret(vault_name: str, api_key: str) -> str:
    """Create or update the API key secret in Key Vault and return the
    secret's data-plane URL.

    Single-shot: see :func:`get_secret_value` for the propagation
    contract. If RBAC has somehow not propagated yet, the underlying
    ``az keyvault secret set`` raises a clear AuthorizationPermissionMismatch
    rather than this function silently sleeping for a minute.
    """
    raw = execute(
        Cmd(["az", "keyvault", "secret", "set"])
        .param("--vault-name", vault_name)
        .param("--name", API_KEY_SECRET_NAME)
        .param("--value", api_key)
    )
    return json.loads(raw)["id"]


@wrap_az_errors(KeyVaultError, "Failed to get Key Vault resource ID: {vault_name}")
def get_secret_resource_id(
    vault_name: str, resource_group: str, subscription: str
) -> str:
    """Get the ARM resource ID for the API key secret (versionless).

    The roles module expects a resource ID like:
    /subscriptions/.../resourceGroups/.../providers/Microsoft.KeyVault/vaults/<vault>/secrets/<name>

    Raises:
        KeyVaultError: If the vault info cannot be retrieved.
    """
    vault_info = execute_json(
        Cmd(["az", "keyvault", "show"])
        .param("--name", vault_name)
        .param("--resource-group", resource_group)
        .param("--subscription", subscription)
    )
    vault_id = vault_info["id"]
    return f"{vault_id}/secrets/{API_KEY_SECRET_NAME}"


def prepare_key_vault(
    vault_name: str,
    resource_group: str,
    location: str,
    subscription: str,
    reporter: Reporter,
) -> bool:
    """Ensure the Key Vault exists and the current user has Secrets Officer
    on it.

    Control-plane work only, so the orchestrator can run it in parallel
    with Storage Account preparation and share a single RBAC propagation
    wait. Caller is responsible for waiting for the role to propagate when
    the returned ``role_created`` is ``True`` before invoking
    :func:`set_or_update_secret`.

    Returns ``role_created``.
    """
    if not key_vault_exists(vault_name, resource_group, subscription):
        reporter.info(f"Creating Key Vault: {vault_name}")
        create_key_vault(vault_name, resource_group, location, subscription)

    reporter.info("Granting secrets access to current user...")
    return grant_current_user_secrets_officer(vault_name, subscription)


def set_or_update_secret(
    config_api_key: str,
    vault_name: str,
    resource_group: str,
    subscription: str,
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

    return get_secret_resource_id(vault_name, resource_group, subscription)
