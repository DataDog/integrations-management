# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass
from json import JSONDecodeError, loads
from typing import Final, Optional

from az_shared.az_cmd import AzCmd, execute
from az_shared.logs import log, log_header

from .configuration import Configuration
from .resource_setup import set_function_app_env_vars
from .role_setup import grant_subscriptions_permissions

RESOURCES_TASK_PREFIX: Final = "resources-task-"
SCALING_TASK_PREFIX: Final = "scaling-task-"
MONITORED_SUBSCRIPTIONS_KEY: Final = "MONITORED_SUBSCRIPTIONS"
RESOURCE_TAG_FILTERS_KEY: Final = "RESOURCE_TAG_FILTERS"
PII_SCRUBBER_RULES_KEY: Final = "PII_SCRUBBER_RULES"

UNKNOWN_SUB_NAME_MESSAGE: Final = "Unknown (insufficient Azure permission)"


@dataclass(frozen=True)
class LfoControlPlane:
    sub_id: str
    sub_name: str
    resource_group: str
    region: str


@dataclass(frozen=True)
class LfoMetadata:
    control_plane: LfoControlPlane
    monitored_subs: dict[str, str]
    tag_filter: str
    pii_rules: str


def find_existing_lfo_control_planes(
    sub_id_to_name: dict[str, str], subscriptions: Optional[set[str]] = None
) -> dict[str, LfoControlPlane]:
    """Find existing LFO control planes in the tenant. If `subscriptions` is specified, search is limited to these subscriptions.
    Returns a dict mapping control plane ID to control plane data."""
    if subscriptions is not None:
        if len(subscriptions) == 0:
            return {}  # searching empty set of subscriptions
        subscriptions_clause = " and subscriptionId in ({})".format(
            ", ".join(["'{}'".format(subscription_id) for subscription_id in subscriptions])
        )
    else:
        subscriptions_clause = ""

    # make sure azure resource graph extension is installed
    if not execute(AzCmd("extension", "show").param("--name", "resource-graph"), can_fail=True):
        execute(AzCmd("extension", "add").param("--name", "resource-graph").param("--yes", ""))

    func_apps_json = execute(
        AzCmd("graph", "query").param(
            "-q",
            f"\"Resources | where type == 'microsoft.web/sites' and kind contains 'functionapp' and name startswith '{RESOURCES_TASK_PREFIX}'{subscriptions_clause} | project name, resourceGroup, subscriptionId, location, properties.state\"",
        )
    )
    try:
        func_apps_response = loads(func_apps_json)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON: {func_apps_json}")
        log.error(f"Error: {e}")
        raise

    existing_control_planes: dict[str, LfoControlPlane] = {}
    for resources_func_app in func_apps_response["data"]:
        subscription_id = resources_func_app["subscriptionId"]
        control_plane_id = resources_func_app["name"].split("-")[-1]
        existing_control_planes[control_plane_id] = LfoControlPlane(
            subscription_id,
            sub_id_to_name[subscription_id],
            resources_func_app["resourceGroup"],
            resources_func_app["location"],
        )
    return existing_control_planes


def query_function_app_env_vars(control_plane: LfoControlPlane, resource_task_name: str) -> dict[str, str]:
    """Query all environment variables for a function app and return as a dictionary."""
    env_vars_list = execute(
        AzCmd("functionapp", "config appsettings list")
        .param("--subscription", control_plane.sub_id)
        .param("--name", resource_task_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--output", "json")
    )

    try:
        env_vars = loads(env_vars_list)
        return {env_var["name"]: env_var["value"] for env_var in env_vars}
    except (JSONDecodeError, KeyError, TypeError) as e:
        log.error(f"Failed to parse environment variables: {env_vars_list}")
        log.error(f"Error: {e}")
        raise


def check_existing_lfo(subscriptions: set[str], sub_id_to_name: dict[str, str]) -> dict[str, LfoMetadata]:
    """Check if LFO is already installed on any of the given subscriptions. Returns a dict mapping control plane ID to LFO metadata."""
    log.info("Checking if log forwarding is already installed in this Azure environment...")

    control_planes = find_existing_lfo_control_planes(sub_id_to_name, subscriptions).items()

    # if there is more than one, just return some LFO stubs since we won't be modifying them
    if len(control_planes) > 1:
        return {
            control_plane_id: LfoMetadata(control_plane, {}, "", "")
            for control_plane_id, control_plane in control_planes
        }
    if len(control_planes) <= 0:
        return {}

    control_plane_id, control_plane = next(iter(control_planes))
    resource_task_name = f"{RESOURCES_TASK_PREFIX}{control_plane_id}"
    scaling_task_name = f"{SCALING_TASK_PREFIX}{control_plane_id}"

    resource_task_env_vars = query_function_app_env_vars(control_plane, resource_task_name)
    scaling_task_env_vars = query_function_app_env_vars(control_plane, scaling_task_name)

    monitored_sub_ids_str = resource_task_env_vars.get(MONITORED_SUBSCRIPTIONS_KEY, "")
    if not monitored_sub_ids_str:
        return {}

    try:
        monitored_sub_ids = loads(monitored_sub_ids_str)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON: {monitored_sub_ids_str}")
        log.error(f"Error: {e}")
        raise

    tag_filters = resource_task_env_vars.get(RESOURCE_TAG_FILTERS_KEY, "")
    pii_rules = scaling_task_env_vars.get(PII_SCRUBBER_RULES_KEY, "")

    return {
        control_plane_id: LfoMetadata(
            control_plane,
            monitored_subs={
                sub_id: sub_id_to_name[sub_id] if sub_id in sub_id_to_name else UNKNOWN_SUB_NAME_MESSAGE
                for sub_id in monitored_sub_ids
            },
            tag_filter=tag_filters,
            pii_rules=pii_rules,
        )
    }


def update_existing_lfo(config: Configuration, existing_lfo: LfoMetadata):
    """Update an existing LFO for the given configuration"""

    log_header("STEP 2: Grant permissions to any new scopes added for log forwarding")
    existing_monitored_sub_ids = set(existing_lfo.monitored_subs.keys())
    new_monitored_sub_ids = set(config.monitored_subscriptions)
    sub_ids_that_need_permissions = new_monitored_sub_ids - existing_monitored_sub_ids

    if sub_ids_that_need_permissions:
        grant_subscriptions_permissions(config, sub_ids_that_need_permissions)
    else:
        log.info("No new subscriptions added - skipping permission grant")

    log_header("STEP 3: Updating settings for control plane tasks")
    existing_tag_filters = existing_lfo.tag_filter
    existing_pii_rules = existing_lfo.pii_rules
    new_tag_filters = config.resource_tag_filters
    new_pii_rules = config.pii_scrubber_rules

    if existing_tag_filters == new_tag_filters and existing_pii_rules == new_pii_rules:
        log.info("No changes to settings detected - skipping update")
        return

    for function_app_name in config.control_plane_function_app_names:
        # Updating env vars will overwrite values for monitored subs, tag filters, and PII rules
        # LFO will auto-adjust behavior based on these settings
        # If the user is removing a sub from the existing monitored subs, LFO will automatically cease log forwarding for the removed sub
        log.info(f"Updating settings for function app {function_app_name}")
        set_function_app_env_vars(config, function_app_name)

    log_header("Success! Azure Automated Log Forwarding installation updated!")
