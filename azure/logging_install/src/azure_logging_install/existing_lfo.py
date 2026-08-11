# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from json import JSONDecodeError, loads
from typing import Optional

from az_shared.execute_cmd import execute
from az_shared.logs import log, log_header

from .az_cmd import AzCmd
from .configuration import Configuration, ControlPlaneType, ControlPlane
from .resource_setup import (
    set_monitored_subscriptions,
    set_pii_scrubber_rules,
    set_resource_tag_filters,
)
from .role_setup import grant_subscriptions_permissions, revoke_subscriptions_permissions
from .constants import MONITORED_SUBSCRIPTIONS_KEY, PII_SCRUBBER_RULES_KEY, RESOURCE_TAG_FILTERS_KEY, RESOURCES_TASK_PREFIX, SCALING_TASK_PREFIX


def get_current_config_for_control_plane(control_plane: ControlPlane) -> Configuration:
    resource_task_env_vars = _query_task_env_vars(control_plane, control_plane.resources_task_name)
    scaling_task_env_vars = _query_task_env_vars(control_plane, control_plane.scaling_task_name)

    monitored_sub_ids_str = resource_task_env_vars.get(MONITORED_SUBSCRIPTIONS_KEY, "")
    try:
        monitored_sub_ids = loads(monitored_sub_ids_str)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON: {monitored_sub_ids_str}")
        log.error(f"Error: {e}")
        raise

    tag_filters = resource_task_env_vars.get(RESOURCE_TAG_FILTERS_KEY, "")
    pii_rules = scaling_task_env_vars.get(PII_SCRUBBER_RULES_KEY, "")

    return Configuration(
        control_plane,
        monitored_subs=','.join(monitored_sub_ids),
        datadog_api_key="",
        resource_tag_filters=tag_filters,
        pii_scrubber_rules=pii_rules,
    )


def find_existing_lfo_control_planes(subscriptions: Optional[set[str]] = None, control_plane_type: Optional[ControlPlaneType] = None) -> list[ControlPlane]:
    """Find existing LFO control planes in the tenant. 
    If `subscriptions` or `control_plane_type` is specified, search is limited to these subscriptions and control plane type, respectively.
    Returns a list of ControlPlanes."""
    if subscriptions is not None:
        if len(subscriptions) == 0:
            return []  # searching empty set of subscriptions
        subscriptions_clause = " and subscriptionId in ({})".format(
            ", ".join(["'{}'".format(subscription_id) for subscription_id in subscriptions])
        )
    else:
        subscriptions_clause = ""

    # make sure azure resource graph extension is installed
    if not execute(AzCmd("extension", "show").param("--name", "resource-graph"), can_fail=True):
        execute(AzCmd("extension", "add").param("--name", "resource-graph").param("--yes", ""))

    function_app_query = f"\"Resources | where type == 'microsoft.web/sites' and kind contains 'functionapp' and name startswith '{RESOURCES_TASK_PREFIX}'{subscriptions_clause} | project name, resourceGroup, subscriptionId, location\""
    caj_query = f"\"Resources | where type == 'microsoft.app/jobs' and name startswith '{RESOURCES_TASK_PREFIX}'{subscriptions_clause} | project name, resourceGroup, subscriptionId, location\""

    function_app_control_planes = []
    caj_control_planes = []

    # query the provided type, or both types if not specified.
    if control_plane_type is None:
        function_app_control_planes = _find_existing_lfo_control_planes_by_type(function_app_query, ControlPlaneType.FunctionApps)
        caj_control_planes = _find_existing_lfo_control_planes_by_type(caj_query, ControlPlaneType.ContainerAppJobs)
    if control_plane_type is ControlPlaneType.FunctionApps:
        function_app_control_planes = _find_existing_lfo_control_planes_by_type(function_app_query, ControlPlaneType.FunctionApps)
    if control_plane_type is ControlPlaneType.ContainerAppJobs:
        caj_control_planes = _find_existing_lfo_control_planes_by_type(caj_query, ControlPlaneType.ContainerAppJobs)

    return function_app_control_planes + caj_control_planes


def _find_existing_lfo_control_planes_by_type(arg_query: str, control_plane_type: ControlPlaneType) -> list[ControlPlane]:
    json = execute(AzCmd("graph", "query").param("-q", arg_query))
    try:
        resp = loads(json)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON: {json}")
        log.error(f"Error: {e}")
        raise

    existing_control_planes: list[ControlPlane] = []
    for app in resp["data"]:
        subscription_id = app["subscriptionId"]
        control_plane_id = app["name"].split("-")[-1]
        existing_control_planes.append(
            ControlPlane(
                id=control_plane_id,
                sub_id=subscription_id,
                resource_group=app["resourceGroup"],
                region=app["location"],
                type=control_plane_type,
            )
        )
    return existing_control_planes


def _query_task_env_vars(control_plane: ControlPlane, task_name: str) -> dict[str, str]:
    """
    Query all environment variables for a task, either Function App or Container App Jobs, and return as a dictionary.
    NOTE For Container App Jobs, environment variables that are secretrefs, like DD_API_KEY, are returned with an empty value
    """
    env_vars_list = []
    if control_plane.type == ControlPlaneType.FunctionApps:
        env_vars_list = execute(
            AzCmd("functionapp", "config appsettings list")
            .param("--subscription", control_plane.sub_id)
            .param("--name", task_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--output", "json")
        )
    if control_plane.type == ControlPlaneType.ContainerAppJobs:
        env_vars_list = execute(
            AzCmd("containerapp", "job show")
            .param("--subscription", control_plane.sub_id)
            .param("--name", task_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--query", "properties.template.containers[].env[]")
            .param("--output", "json")
        )

    try:
        env_vars = loads(env_vars_list)
        return {env_var["name"]: env_var.get("value", "") for env_var in env_vars}
    except (JSONDecodeError, KeyError, TypeError) as e:
        log.error(f"Failed to parse environment variables: {env_vars_list}")
        log.error(f"Error: {e}")
        raise


def check_existing_lfo(subscriptions: set[str]) -> list[Configuration]:
    """Check if LFO is already installed on any of the given subscriptions. Returns a dict mapping control plane ID to LFO metadata."""
    log.info("Checking if log forwarding is already installed in this Azure environment...")

    control_planes = find_existing_lfo_control_planes(subscriptions)

    # if there is more than one, just return some LFO stubs since we won't be modifying them
    if len(control_planes) > 1:
        return [
            Configuration(control_plane=control_plane, monitored_subs="", datadog_api_key="")
            for control_plane in control_planes
        ]

    # TODO this used to check len(monitored_subscriptions) > 0. Why?
    if len(control_planes) == 0:
        return []

    return [get_current_config_for_control_plane(control_planes[0])]


def update_existing_lfo(new_config: Configuration, existing_lfo: Configuration):
    """Update an existing LFO for the given configuration"""

    existing_monitored_sub_ids = set(existing_lfo.monitored_subscriptions)
    new_monitored_sub_ids = set(new_config.monitored_subscriptions)
    sub_ids_that_need_permissions = new_monitored_sub_ids - existing_monitored_sub_ids
    sub_ids_to_remove = existing_monitored_sub_ids - new_monitored_sub_ids

    if sub_ids_that_need_permissions and sub_ids_to_remove:
        log_header("STEP 2: Grant and revoke permissions for log forwarding scopes")
    elif sub_ids_that_need_permissions:
        log_header("STEP 2: Grant permissions to any new scopes added for log forwarding")
    elif sub_ids_to_remove:
        log_header("STEP 2: Revoke permissions for removed log forwarding scopes")
    else:
        log_header("STEP 2: Skipping permission changes for log forwarding scopes")

    if sub_ids_that_need_permissions:
        grant_subscriptions_permissions(existing_lfo.control_plane, sub_ids_that_need_permissions)

    if sub_ids_to_remove:
        revoke_subscriptions_permissions(existing_lfo.control_plane, sub_ids_to_remove)

    if not sub_ids_that_need_permissions and not sub_ids_to_remove:
        log.info("No modified subscription selections - skipping permission updates")

    log_header("STEP 3: Updating settings for control plane tasks")
    existing_tag_filters = existing_lfo.resource_tag_filters
    existing_pii_rules = existing_lfo.pii_scrubber_rules
    new_tag_filters = new_config.resource_tag_filters
    new_pii_rules = new_config.pii_scrubber_rules

    tag_filter_changed = existing_tag_filters != new_tag_filters
    pii_rules_changed = existing_pii_rules != new_pii_rules
    monitored_subs_changed = existing_monitored_sub_ids != new_monitored_sub_ids
    change_count = sum((tag_filter_changed, pii_rules_changed, monitored_subs_changed))

    if tag_filter_changed:
        set_resource_tag_filters(existing_lfo.control_plane, new_tag_filters)
    if pii_rules_changed:
        set_pii_scrubber_rules(existing_lfo.control_plane, new_pii_rules)
    if monitored_subs_changed:
        set_monitored_subscriptions(existing_lfo.control_plane, new_config.monitored_subscriptions)
    if change_count == 0:
        log.info("No changes to settings detected - skipping update")
        return

    log_header("Success! Azure Automated Log Forwarding installation updated!")
