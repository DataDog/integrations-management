# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict

from az_shared.az_cmd import AzCmd, execute, set_subscription
from az_shared.errors import (
    AccessError,
    AzCliNotAuthenticatedError,
    DatadogAccessValidationError,
    ExistenceCheckError,
    InputParamValidationError,
    ResourceProviderRegistrationValidationError,
)
from az_shared.logs import log

from .configuration import Configuration
from .constants import REQUIRED_RESOURCE_PROVIDERS
from .existing_lfo import check_existing_lfo, LfoMetadata


def is_empty_or_whitespace(s: str) -> bool:
    """Check if a string is empty or contains only whitespace."""

    return not s or s.isspace()


def validate_user_parameters(config: Configuration):
    """Validate user-specified parameters."""

    validate_user_config(config)
    validate_azure_env(config)
    validate_datadog_credentials(config.datadog_api_key, config.datadog_site)


def validate_azure_env(config: Configuration):
    """Validate Azure parameters and environment before creating any resources."""

    validate_control_plane_sub_access(config.control_plane_sub_id)
    validate_monitored_subs_access(config.monitored_subscriptions)
    validate_resource_provider_registrations(config.all_subscriptions)
    validate_resource_names(
        config.control_plane_rg,
        config.control_plane_sub_id,
        config.control_plane_cache_storage_name,
    )


def validate_az_cli():
    """Ensure Azure CLI is installed and user is authenticated."""
    try:
        execute(AzCmd("account", "show"))
        log.debug("Azure CLI authentication verified")
    except Exception as e:
        raise AzCliNotAuthenticatedError(
            "Azure CLI is not authenticated. Please run 'az login' first and retry"
        ) from e


def check_fresh_install(
    config: Configuration, sub_id_to_name: dict[str, str]
) -> dict[str, LfoMetadata]:
    """Validate whether we are doing a fresh log forwarding install."""
    existing_lfos = check_existing_lfo(config.all_subscriptions, sub_id_to_name)
    if existing_lfos:
        log.info("Found existing log forwarding installation(s)")
        serializable_lfos = {k: asdict(v) for k, v in existing_lfos.items()}
        log.debug(json.dumps(serializable_lfos, indent=2))
    return existing_lfos


def validate_singleton_lfo(
    config: Configuration, existing_lfos: dict[str, LfoMetadata]
):
    uninstall_link = "https://docs.datadoghq.com/logs/guide/azure-automated-log-forwarding/#uninstall"
    existing_count = len(existing_lfos)
    if existing_count > 1:
        log.error(
            "Multiple existing log forwarding installations found in this Azure environment. Only one is allowed."
        )
        log.error(
            "Please delete any extraneous log forwarding installations, then edit a single one to have a larger scope."
        )
        log.info(f"Uninstall instructions: {uninstall_link}")
        log.info("Exiting...")
        sys.exit(0)

    existing_lfo_control_plane_id = next(iter(existing_lfos.keys()))

    if (
        existing_count == 1
        and existing_lfo_control_plane_id.casefold()
        != config.control_plane_id.casefold()
    ):
        log.error(
            f"Existing log forwarding installation with differing control plane ID '{existing_lfo_control_plane_id}' found in this Azure environment. New installation ID is '{config.control_plane_id}'."
        )
        log.error(
            "Please delete the existing log forwarding installation before installing a new one or edit the existing one to have a larger scope."
        )
        log.info(f"Uninstall instructions: {uninstall_link}")
        log.info("Exiting...")
        sys.exit(0)


def check_providers_per_subscription(sub_ids: set[str]) -> dict[str, list[str]]:
    """Check resource providers per subscription and return a dict of subscription IDs to unregistered providers."""

    sub_to_unregistered_provider_list = {}

    for sub_id in sub_ids:
        try:
            log.debug(f"Checking resource providers in subscription: {sub_id}")

            # Get all resource providers and their registration state
            output = execute(
                AzCmd("provider", "list")
                .param("--subscription", sub_id)
                .param(
                    "--query",
                    '"[].{namespace:namespace, registrationState:registrationState}"',
                )
                .param("--output", "json")
            )
            providers_status = json.loads(output)

            # Create a lookup dict
            provider_states = {
                p["namespace"]: p["registrationState"] for p in providers_status
            }

            unregistered_providers = []
            for provider in REQUIRED_RESOURCE_PROVIDERS:
                state = provider_states.get(provider, "NotFound")
                if state != "Registered":
                    unregistered_providers.append(provider)
                    log.debug(
                        f"Subscription {sub_id}: Resource provider {provider} is {state}"
                    )

            sub_to_unregistered_provider_list[sub_id] = unregistered_providers
        except Exception as e:
            log.error(
                f"Failed to validate resource providers in subscription {sub_id}: {e}"
            )
            raise ResourceProviderRegistrationValidationError(
                f"Resource provider validation failed for subscription {sub_id}: {e}"
            ) from e

    return sub_to_unregistered_provider_list


def validate_resource_provider_registrations(sub_ids: set[str]):
    """Ensure the required Azure resource providers are registered across all subscriptions."""

    log.info(
        f"Checking required resource providers across {len(sub_ids)} subscription(s)..."
    )
    sub_to_unregistered_provider_list = check_providers_per_subscription(sub_ids)

    success = True
    for sub_id, unregistered_providers in sub_to_unregistered_provider_list.items():
        if unregistered_providers:
            success = False
            log.error(
                f"Subscription {sub_id}: Detected unregistered resource providers: {', '.join(unregistered_providers)}"
            )
            log.error(
                "Please run the following commands to register the missing resource providers:"
            )
            log.error(f"az account set --subscription {sub_id}")
            for provider in unregistered_providers:
                log.error(f"az provider register --namespace {provider}")
        else:
            log.debug(
                f"Subscription {sub_id}: All required resource providers are registered"
            )

    if not success:
        raise ResourceProviderRegistrationValidationError(
            "Resource provider validation failed. Check logs for more details."
        )

    log.info("Resource provider validation successful across all subscriptions")


def validate_control_plane_sub_access(control_plane_sub_id: str):
    """Verify access to the control plane subscription."""
    try:
        set_subscription(control_plane_sub_id)
        log.debug(f"Control plane subscription access verified: {control_plane_sub_id}")
    except Exception as e:
        raise AccessError(
            f"Cannot access control plane subscription {control_plane_sub_id}: {e}"
        ) from e


def validate_resource_names(
    control_plane_rg: str,
    control_plane_sub_id: str,
    control_plane_cache_storage_name: str,
):
    """Check if resource names are available and valid."""
    log.info("Validating resource name availability...")

    # Check if resource group already exists
    try:
        output = execute(
            AzCmd("group", "exists")
            .param("--name", control_plane_rg)
            .param("--subscription", control_plane_sub_id)
        )
        if output.strip().lower() == "true":
            log.warning(
                f"Resource group {control_plane_rg} already exists - will use existing"
            )
        else:
            log.debug(f"Resource group name available: {control_plane_rg}")
    except Exception as e:
        raise ExistenceCheckError(
            f"Cannot check resource group availability: {e}"
        ) from e

    # Check storage account name availability
    try:
        result_json = execute(
            AzCmd("storage", "account check-name").param(
                "--name", control_plane_cache_storage_name
            )
        )
        result = json.loads(result_json)
        if not result.get("nameAvailable", False):
            log.info(
                f"Storage account name '{control_plane_cache_storage_name}' exists - will use existing"
            )
        log.debug(f"Storage account name available: {control_plane_cache_storage_name}")
    except json.JSONDecodeError as e:
        raise ExistenceCheckError(
            "Failed to parse storage account name availability check"
        ) from e


def validate_datadog_credentials(datadog_api_key: str, datadog_site: str):
    """Validate Datadog API credentials without making changes."""
    log.info("Validating Datadog API credentials...")

    if not datadog_api_key:
        raise InputParamValidationError("Datadog API key not configured")

    try:
        url = f"https://api.{datadog_site}/api/v1/validate"
        headers = {"Accept": "application/json", "DD-API-KEY": datadog_api_key}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            response_json = json.loads(response.read())
            if not response_json.get("valid", False):
                raise DatadogAccessValidationError(
                    f"Datadog API Key validation with {datadog_site} failed"
                )

        log.debug("Datadog API credentials validated")
    except urllib.error.HTTPError as e:
        raise DatadogAccessValidationError(
            f"Failed to validate Datadog credentials: HTTP {e.code} {e.reason}"
        ) from e
    except urllib.error.URLError as e:
        raise DatadogAccessValidationError(
            f"Failed to validate Datadog credentials: {e.reason}"
        ) from e
    except json.JSONDecodeError as e:
        raise DatadogAccessValidationError(
            f"Failed to parse Datadog validation response: {e}"
        ) from e


def validate_user_config(config: Configuration):
    """Validate user-specified configuration parameters."""
    log.info("Validating configuration parameters...")

    if is_empty_or_whitespace(config.control_plane_sub_id):
        raise InputParamValidationError("Control plane subscription cannot be empty")

    if not _is_valid_azure_subscription_id(config.control_plane_sub_id):
        raise InputParamValidationError(
            "Control plane subscription ID is not a valid Azure subscription ID (must be a valid UUID)"
        )

    if is_empty_or_whitespace(config.control_plane_rg):
        raise InputParamValidationError("Control plane resource group cannot be empty")

    if is_empty_or_whitespace(config.control_plane_region):
        raise InputParamValidationError("Control plane location cannot be empty")

    _validate_monitored_subscriptions(config.monitored_subs)

    if config.resource_tag_filters:
        _validate_tag_filters(config.resource_tag_filters)

    if config.pii_scrubber_rules:
        _validate_pii_scrubber_rules(config.pii_scrubber_rules)

    if config.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        config.log_level = "INFO"

    log.debug("Configuration validation completed")


def validate_monitored_subs_access(monitored_subs: list[str]):
    """Verify access to all monitored subscriptions."""
    log.info("Validating access to monitored subscriptions...")

    for sub_id in monitored_subs:
        try:
            set_subscription(sub_id)
            log.debug(f"Monitored subscription access verified: {sub_id}")
        except Exception as e:
            raise AccessError(
                f"Cannot access monitored subscription {sub_id}: {e}"
            ) from e


def _is_valid_azure_subscription_id(subscription_id: str) -> bool:
    """Validate that a subscription ID is a valid UUID format."""
    try:
        uuid.UUID(subscription_id.strip())
        return True
    except ValueError:
        return False


def _validate_monitored_subscriptions(monitored_subs: str):
    """Validate that monitored subscriptions is a comma separated list of valid subscription IDs."""
    if is_empty_or_whitespace(monitored_subs):
        raise InputParamValidationError("Monitored subscriptions cannot be empty")

    subscription_ids = [sub.strip() for sub in monitored_subs.split(",") if sub.strip()]

    if not subscription_ids:
        raise InputParamValidationError(
            "Monitored subscriptions list contains no valid entries"
        )

    for sub_id in subscription_ids:
        if not _is_valid_azure_subscription_id(sub_id):
            raise InputParamValidationError(
                f"Monitored subscription ID '{sub_id}' is not a valid Azure subscription ID (must be a valid UUID)"
            )


def _validate_tag_filters(tag_filters: str):
    """Validate that tag_filters is a comma separated list of values."""
    if is_empty_or_whitespace(tag_filters):
        return

    filter_values = [tag.strip() for tag in tag_filters.split(",") if tag.strip()]

    for tag_filter in filter_values:
        if is_empty_or_whitespace(tag_filter):
            raise InputParamValidationError("Tag filters cannot contain empty values")

        # Validate tag starts with a letter
        if not tag_filter[0].isalpha():
            raise InputParamValidationError(
                f"Tag '{tag_filter}' must start with a letter"
            )


def _validate_pii_scrubber_rules(pii_scrubber_rules: str):
    """Validate a basic YAML format"""
    if is_empty_or_whitespace(pii_scrubber_rules):
        return

    for line in pii_scrubber_rules.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            raise InputParamValidationError("PII scrubber rules contain invalid YAML")
