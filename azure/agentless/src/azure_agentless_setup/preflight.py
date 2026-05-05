# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Preflight checks before running Terraform."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from az_shared.auth import check_login
from az_shared.auth import set_subscription as az_set_subscription
from az_shared.execute_cmd import execute, execute_json
from az_shared.regions import get_available_regions
from common.datadog_validation import (
    APIKeyMissingRCScopeError,
    InvalidAPIKeyError,
    InvalidAppKeyError,
    validate_api_key,
    validate_app_key,
)
from common.shell import Cmd

from .config import Config
from .errors import (
    AzureAccessError,
    ConfigurationError,
    DatadogAPIKeyError,
    DatadogAPIKeyMissingRCError,
    DatadogAppKeyError,
    ResourceProviderError,
    SetupError,
)
from .reporter import AgentlessStep, Reporter
from .state_storage import resource_group_exists


MAX_PARALLEL_WORKERS = 10

REQUIRED_RESOURCE_PROVIDERS = [
    "Microsoft.Compute",
    "Microsoft.Network",
    "Microsoft.ManagedIdentity",
    "Microsoft.Storage",
    "Microsoft.KeyVault",
    "Microsoft.Authorization",
]

# Actions required on every subscription (scanner + scan targets) for
# cross-subscription role assignments. Always probed at subscription scope.
REQUIRED_ACTIONS_ALL_SUBSCRIPTIONS = [
    "Microsoft.Authorization/roleAssignments/write",
]

# Resource-creation actions for the scanner subscription. These are probed at
# the *resource-group* scope when the RG already exists, so users with only
# RG-scoped Contributor (a common enterprise pattern when the RG is
# pre-provisioned) pass preflight. Probing at the RG scope still observes
# subscription-level grants because Azure permissions inherit downwards.
REQUIRED_ACTIONS_SCANNER_RG_RESOURCES = [
    "Microsoft.Compute/virtualMachineScaleSets/write",
    "Microsoft.Network/virtualNetworks/write",
    "Microsoft.ManagedIdentity/userAssignedIdentities/write",
    "Microsoft.KeyVault/vaults/write",
    "Microsoft.Storage/storageAccounts/write",
]

# Required at subscription scope only when the script must create the RG itself.
REQUIRED_ACTION_RG_CREATE = "Microsoft.Resources/subscriptions/resourceGroups/write"


def validate_datadog_api_key(reporter: Reporter, api_key: str, site: str) -> None:
    """Validate Datadog API key and check for Remote Configuration scope.

    Raises:
        DatadogAPIKeyError: If the API key or site is invalid.
        DatadogAPIKeyMissingRCError: If the API key doesn't have Remote Configuration scope.
    """
    try:
        validate_api_key(api_key, site, require_rc_scope=True)
    except APIKeyMissingRCScopeError:
        raise DatadogAPIKeyMissingRCError()
    except InvalidAPIKeyError:
        raise DatadogAPIKeyError(site)
    reporter.success("Datadog API key validated (Remote Configuration enabled)")


def validate_datadog_app_key(reporter: Reporter, api_key: str, app_key: str, site: str) -> None:
    """Validate Datadog Application key.

    Raises:
        DatadogAppKeyError: If the Application key is invalid.
    """
    try:
        validate_app_key(api_key, app_key, site)
    except InvalidAppKeyError:
        raise DatadogAppKeyError()
    reporter.success("Datadog Application key validated")


def check_azure_authentication(reporter: Reporter) -> None:
    """Verify Azure CLI authentication.

    Raises:
        SetupError: If not authenticated with Azure.
    """
    try:
        check_login()
    except Exception:
        raise SetupError("Not authenticated with Azure", "Run: az login")
    reporter.success("Azure CLI authentication verified")


def set_subscription(reporter: Reporter, subscription_id: str) -> None:
    """Set the active Azure subscription.

    Raises:
        AzureAccessError: If the subscription cannot be set.
    """
    try:
        az_set_subscription(subscription_id)
    except Exception as e:
        raise AzureAccessError(
            f"Cannot set subscription: {subscription_id}",
            f"Ensure you have access to this subscription.\n{e}",
        )
    reporter.success(f"Active subscription set to {subscription_id}")


def _get_granted_actions_at_scope(scope: str) -> list[str]:
    """Fetch the actions granted to the current user that apply at ``scope``.

    Azure's ``Microsoft.Authorization/permissions`` API at a given scope
    returns the *effective* set of actions including those inherited from
    higher scopes, so probing at the resource-group scope captures both
    RG-level and subscription-level grants.
    """
    url = f"https://management.azure.com{scope}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
    try:
        result = execute_json(Cmd(["az", "rest", "-u", url, "--query", "value"]))
    except Exception:
        return []

    actions: list[str] = []
    for perm in (result or []):
        actions.extend(perm.get("actions", []))
    return actions


def _action_matches(required: str, granted_patterns: list[str]) -> bool:
    """Check if a required action is covered by any granted wildcard pattern.

    E.g. "Microsoft.Compute/*" covers "Microsoft.Compute/virtualMachineScaleSets/write",
    and "*" covers everything.
    """
    required_lower = required.lower()
    for pattern in granted_patterns:
        pattern_lower = pattern.lower()
        if pattern_lower == "*":
            return True
        if pattern_lower == required_lower:
            return True
        if pattern_lower.endswith("/*"):
            prefix = pattern_lower[:-1]
            if required_lower.startswith(prefix):
                return True
    return False


def _missing_actions(scope: str, required: list[str]) -> list[str]:
    """Return the actions in ``required`` that are not granted at ``scope``."""
    granted = _get_granted_actions_at_scope(scope)
    if not granted:
        return list(required)
    return [a for a in required if not _action_matches(a, granted)]


def _check_scanner_subscription(
    scanner_subscription: str,
    resource_group: str,
    rg_exists: bool,
) -> list[str]:
    """Return the missing actions for the scanner subscription.

    When ``rg_exists`` is True, the resource-creation actions are probed at
    the RG scope (so users with RG-only Contributor pass) and
    ``resourceGroups/write`` is dropped from the requirements. Otherwise
    everything is probed at the subscription scope, which is what's needed
    to create the RG and the resources within it.
    """
    sub_scope = f"/subscriptions/{scanner_subscription}"

    if rg_exists:
        rg_scope = f"{sub_scope}/resourceGroups/{resource_group}"
        return (
            _missing_actions(sub_scope, REQUIRED_ACTIONS_ALL_SUBSCRIPTIONS)
            + _missing_actions(rg_scope, REQUIRED_ACTIONS_SCANNER_RG_RESOURCES)
        )

    return _missing_actions(
        sub_scope,
        REQUIRED_ACTIONS_ALL_SUBSCRIPTIONS
        + [REQUIRED_ACTION_RG_CREATE]
        + REQUIRED_ACTIONS_SCANNER_RG_RESOURCES,
    )


def _check_scan_subscription(scan_subscription: str) -> list[str]:
    """Return the missing actions for a non-scanner scan subscription."""
    return _missing_actions(
        f"/subscriptions/{scan_subscription}", REQUIRED_ACTIONS_ALL_SUBSCRIPTIONS
    )


def check_subscriptions_permissions_parallel(
    reporter: Reporter,
    scanner_subscription: str,
    all_subscriptions: list[str],
    resource_group: str,
    scanner_rg_exists: bool,
) -> list[str]:
    """Check permissions on all subscriptions in parallel.

    Scanner subscription: see :func:`_check_scanner_subscription` — probed at
    RG scope when the RG already exists, subscription scope otherwise.
    Scan-only subscriptions: probed at subscription scope for the
    cross-subscription role-assignment write.

    Returns the list of subscription IDs that failed permission checks.
    """
    failed = []

    def _check(sub_id: str) -> tuple[str, list[str]]:
        if sub_id == scanner_subscription:
            return sub_id, _check_scanner_subscription(
                sub_id, resource_group, scanner_rg_exists
            )
        return sub_id, _check_scan_subscription(sub_id)

    with ThreadPoolExecutor(max_workers=min(len(all_subscriptions), MAX_PARALLEL_WORKERS)) as executor:
        futures = {executor.submit(_check, s): s for s in all_subscriptions}

        for future in as_completed(futures):
            sub_id, missing = future.result()
            if missing:
                detail = "\n".join(f"    - {a}" for a in missing)
                reporter.error(f"Missing permissions on subscription: {sub_id}", f"Required actions:\n{detail}")
                failed.append(sub_id)

    return failed


def validate_locations(reporter: Reporter, locations: list[str]) -> None:
    """Validate that location names are valid Azure regions.

    Fetches all available regions in a single API call via ``az_shared.regions``
    and checks that every requested location is in the returned list.

    Raises:
        ConfigurationError: If any location is invalid.
    """
    try:
        available = get_available_regions()
    except Exception:
        available = []

    if not available:
        raise ConfigurationError(
            "Could not fetch available Azure regions",
            "Ensure you are authenticated and your subscription is active.\n"
            "Run 'az account list-locations --query \"[].name\"' to verify.",
        )

    available_set = set(available)
    invalid = [loc for loc in locations if loc not in available_set]

    if invalid:
        raise ConfigurationError(
            f"Invalid Azure location(s): {', '.join(invalid)}",
            "These locations do not exist or are not accessible.\n"
            "Run 'az account list-locations --query \"[].name\"' to see available locations.",
        )
    reporter.success(f"Location(s) validated: {', '.join(locations)}")


def _check_resource_provider(provider: str, subscription_id: str) -> tuple[str, str]:
    """Check registration state of a resource provider. Returns (provider, state)."""
    try:
        result = execute(
            Cmd(["az", "provider", "show", "--namespace", provider,
                 "--subscription", subscription_id,
                 "--query", "registrationState", "--output", "json"])
        )
        state = result.strip().strip('"')
        return provider, state
    except Exception:
        return provider, "Unknown"


def _register_resource_provider(provider: str, subscription_id: str) -> tuple[str, bool, Optional[str]]:
    """Register a resource provider. Returns (provider, success, error)."""
    try:
        execute(Cmd(["az", "provider", "register", "--namespace", provider, "--subscription", subscription_id]))
        return provider, True, None
    except Exception as e:
        return provider, False, str(e)


def check_and_register_resource_providers(
    reporter: Reporter,
    subscription_id: str,
) -> None:
    """Check and register required Azure resource providers.

    Raises:
        ResourceProviderError: If providers cannot be registered.
    """
    # Check all providers in parallel
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(_check_resource_provider, p, subscription_id): p
            for p in REQUIRED_RESOURCE_PROVIDERS
        }
        unregistered = []
        for future in as_completed(futures):
            provider, state = future.result()
            if state not in ("Registered", "Registering"):
                unregistered.append(provider)

    if not unregistered:
        reporter.success("All required resource providers registered")
        return

    # Register missing providers in parallel
    reporter.info(f"Registering {len(unregistered)} resource provider(s)...")
    errors = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(_register_resource_provider, p, subscription_id): p
            for p in unregistered
        }
        for future in as_completed(futures):
            provider, success, error = future.result()
            if not success:
                errors.append((provider, error))

    if errors:
        error_details = "\n".join(f"  - {p}: {e}" for p, e in errors)
        raise ResourceProviderError(
            f"Failed to register {len(errors)} resource provider(s)",
            error_details,
        )

    reporter.success(f"Registered resource provider(s): {', '.join(unregistered)}")


def run_preflight_checks(config: Config, reporter: Reporter) -> None:
    """Run all preflight checks.

    Raises:
        AzureAuthenticationError: If not authenticated with Azure.
        AzureAccessError: If subscriptions cannot be accessed.
        ConfigurationError: If locations are invalid.
        ResourceProviderError: If resource providers cannot be registered.
    """
    reporter.start_step("Validating prerequisites", AgentlessStep.PREFLIGHT_CHECKS)

    check_azure_authentication(reporter)

    set_subscription(reporter, config.scanner_subscription)

    validate_locations(reporter, config.locations)

    # Determine whether the scanner RG exists so we can probe permissions at
    # the RG scope (vs subscription scope) when it does, and drop the
    # resourceGroups/write requirement that would otherwise block users with
    # RG-scoped Contributor on a pre-provisioned resource group.
    scanner_rg_exists = resource_group_exists(
        config.resource_group, config.scanner_subscription
    )

    reporter.info(f"Checking permissions on {len(config.all_subscriptions)} subscription(s)...")
    failed = check_subscriptions_permissions_parallel(
        reporter,
        config.scanner_subscription,
        config.all_subscriptions,
        config.resource_group,
        scanner_rg_exists,
    )

    if failed:
        raise AzureAccessError(
            f"Insufficient permissions on {len(failed)} subscription(s)",
            "Ensure you have the required role assignments on:\n"
            + "\n".join(f"  - {s}" for s in failed),
        )

    reporter.success(f"Permissions verified for {len(config.all_subscriptions)} subscription(s)")

    reporter.info(f"Checking resource providers in scanner subscription ({config.scanner_subscription})...")
    check_and_register_resource_providers(reporter, config.scanner_subscription)

    reporter.finish_step()
