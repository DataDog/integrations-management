# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Preflight checks before running Terraform."""

import urllib.request
import urllib.error
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .config import Config
from .errors import (
    AzureAccessError,
    AzureAuthenticationError,
    ConfigurationError,
    DatadogAPIKeyError,
    DatadogAPIKeyMissingRCError,
    DatadogAppKeyError,
    ResourceProviderError,
)
from .reporter import Reporter, AgentlessStep
from .shell import az_cli


MAX_PARALLEL_WORKERS = 10

REQUIRED_RESOURCE_PROVIDERS = [
    "Microsoft.Compute",
    "Microsoft.Network",
    "Microsoft.ManagedIdentity",
    "Microsoft.Storage",
    "Microsoft.KeyVault",
    "Microsoft.Authorization",
]


def validate_datadog_api_key(reporter: Reporter, api_key: str, site: str) -> None:
    """Validate Datadog API key and check for Remote Configuration scope.

    Raises:
        DatadogAPIKeyError: If the API key or site is invalid.
        DatadogAPIKeyMissingRCError: If the API key doesn't have Remote Configuration scope.
    """
    url = f"https://api.{site}/api/v2/validate"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "DD-API-KEY": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                scopes = data.get("data", {}).get("attributes", {}).get("api_key_scopes", [])
                if "remote_config_read" not in scopes:
                    raise DatadogAPIKeyMissingRCError()
                reporter.success("Datadog API key validated (Remote Configuration enabled)")
            else:
                raise DatadogAPIKeyError(site)
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise DatadogAPIKeyError(site)


def validate_datadog_app_key(reporter: Reporter, api_key: str, app_key: str, site: str) -> None:
    """Validate Datadog Application key.

    Raises:
        DatadogAppKeyError: If the Application key is invalid.
    """
    url = f"https://api.{site}/api/v2/validate_keys"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                reporter.success("Datadog Application key validated")
                return
            else:
                raise DatadogAppKeyError()
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise DatadogAppKeyError()


def check_azure_authentication(reporter: Reporter) -> None:
    """Verify Azure CLI authentication.

    Raises:
        AzureAuthenticationError: If not authenticated with Azure.
    """
    success, result = az_cli(["account", "show"])
    if not success:
        raise AzureAuthenticationError()
    reporter.success("Azure CLI authentication verified")


def set_subscription(reporter: Reporter, subscription_id: str) -> None:
    """Set the active Azure subscription.

    Raises:
        AzureAccessError: If the subscription cannot be set.
    """
    success, result = az_cli(["account", "set", "--subscription", subscription_id], output_json=False)
    if not success:
        raise AzureAccessError(
            f"Cannot set subscription: {subscription_id}",
            f"Ensure you have access to this subscription.\n{result}",
        )
    reporter.success(f"Active subscription set to {subscription_id}")


def check_subscription_access(subscription_id: str) -> tuple[str, bool, Optional[str]]:
    """Check if we have access to a subscription.

    Returns:
        Tuple of (subscription_id, success, error_message)
    """
    success, result = az_cli(["account", "show", "--subscription", subscription_id])
    if not success:
        return subscription_id, False, str(result)
    return subscription_id, True, None


def check_subscriptions_access_parallel(reporter: Reporter, subscriptions: list[str]) -> list[str]:
    """Check access to multiple subscriptions in parallel.

    Returns:
        List of subscriptions that failed access check.
    """
    failed = []

    with ThreadPoolExecutor(max_workers=min(len(subscriptions), MAX_PARALLEL_WORKERS)) as executor:
        futures = {executor.submit(check_subscription_access, s): s for s in subscriptions}

        for future in as_completed(futures):
            sub_id, success, error = future.result()
            if not success:
                reporter.error(f"Cannot access subscription: {sub_id}", error)
                failed.append(sub_id)

    return failed


def _check_location(location: str, subscription_id: str) -> tuple[str, bool]:
    """Check a single location against the Azure API. Returns (location, is_valid)."""
    success, result = az_cli([
        "account", "list-locations",
        "--query", f"[?name=='{location}']",
    ])
    if not success:
        return location, False
    # result is a list; non-empty means valid
    return location, isinstance(result, list) and len(result) > 0


def validate_locations(reporter: Reporter, locations: list[str], subscription_id: str) -> None:
    """Validate that location names are valid Azure regions.

    Raises:
        ConfigurationError: If any location is invalid.
    """
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(_check_location, loc, subscription_id): loc
            for loc in locations
        }
        invalid = []
        for future in as_completed(futures):
            location, is_valid = future.result()
            if not is_valid:
                invalid.append(location)

    if invalid:
        raise ConfigurationError(
            f"Invalid Azure location(s): {', '.join(invalid)}",
            "These locations do not exist or are not accessible.\n"
            "Run 'az account list-locations --query \"[].name\"' to see available locations.",
        )
    reporter.success(f"Location(s) validated: {', '.join(locations)}")


def _check_resource_provider(provider: str, subscription_id: str) -> tuple[str, str]:
    """Check registration state of a resource provider. Returns (provider, state)."""
    success, result = az_cli([
        "provider", "show",
        "--namespace", provider,
        "--subscription", subscription_id,
        "--query", "registrationState",
    ])
    if not success:
        return provider, "Unknown"
    # result is a quoted string like "Registered"
    state = result.strip('"') if isinstance(result, str) else str(result)
    return provider, state


def _register_resource_provider(provider: str, subscription_id: str) -> tuple[str, bool, Optional[str]]:
    """Register a resource provider. Returns (provider, success, error)."""
    success, result = az_cli([
        "provider", "register",
        "--namespace", provider,
        "--subscription", subscription_id,
    ], output_json=False)
    if not success:
        return provider, False, str(result)
    return provider, True, None


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

    validate_locations(reporter, config.locations, config.scanner_subscription)

    reporter.info(f"Checking access to {len(config.all_subscriptions)} subscription(s)...")
    failed = check_subscriptions_access_parallel(reporter, config.all_subscriptions)

    if failed:
        raise AzureAccessError(
            f"Cannot access {len(failed)} subscription(s)",
            "Ensure you have 'Reader' role or equivalent on:\n"
            + "\n".join(f"  - {s}" for s in failed),
        )

    reporter.success(f"Access verified for {len(config.all_subscriptions)} subscription(s)")

    reporter.info(f"Checking resource providers in scanner subscription ({config.scanner_subscription})...")
    check_and_register_resource_providers(reporter, config.scanner_subscription)

    reporter.finish_step()
