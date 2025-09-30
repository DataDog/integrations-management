from dataclasses import dataclass
from json import JSONDecodeError, loads
from logging import getLogger
from typing import Final, Optional

from .az_cmd import AzCmd, execute

log = getLogger("installer")

CONTROL_PLANE_RESOURCES_TASK_PREFIX: Final = "resources-task"
MONITORED_SUBSCRIPTIONS_KEY: Final = "MONITORED_SUBSCRIPTIONS"
RESOURCE_TAG_FILTERS_KEY: Final = "RESOURCE_TAG_FILTERS"
PII_SCRUBBER_RULES_KEY: Final = "PII_SCRUBBER_RULES"


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
    """Find existing lfo control planes in the tenant. If `subscriptions` is specified, search is limited to these subscriptions."""
    if subscriptions is not None:
        if len(subscriptions) == 0:
            return {}  # searching empty set of subscriptions
        subscriptions_clause = " and subscriptionId in ({})".format(
            ", ".join(
                ["'{}'".format(subscription_id) for subscription_id in subscriptions]
            )
        )
    else:
        subscriptions_clause = ""

    # make sure azure resource graph extension is installed
    if not execute(
        AzCmd("extension", "show").param("--name", "resource-graph"), can_fail=True
    ):
        execute(
            AzCmd("extension", "add")
            .param("--name", "resource-graph")
            .param("--yes", "")
        )

    func_apps_json = execute(
        AzCmd("graph", "query").param(
            "-q",
            f"\"Resources | where type == 'microsoft.web/sites' and kind contains 'functionapp' and name startswith '{CONTROL_PLANE_RESOURCES_TASK_PREFIX}'{subscriptions_clause} | project name, resourceGroup, subscriptionId, location, properties.state\"",
        )
    )
    try:
        func_apps_response = loads(func_apps_json)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON: {func_apps_json}")
        log.error(f"Error: {e}")
        raise

    existing_control_planes: dict[str, LfoControlPlane] = {}
    for func_app in func_apps_response["data"]:
        subscription_id = func_app["subscriptionId"]
        existing_control_planes[func_app["name"]] = LfoControlPlane(
            subscription_id,
            sub_id_to_name[subscription_id],
            func_app["resourceGroup"],
            func_app["location"],
        )
    return existing_control_planes


def query_function_app_env_vars(
    control_plane: LfoControlPlane, resource_task_name: str
) -> dict[str, str]:
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


def check_existing_lfo(
    subscriptions: set[str], sub_id_to_name: dict[str, str]
) -> dict[str, LfoMetadata]:
    """Check if LFO is already installed on any of the given subscriptions"""
    log.info(
        "Checking if log forwarding is already installed in this Azure environment..."
    )

    control_planes = find_existing_lfo_control_planes(sub_id_to_name, subscriptions)
    existing_lfos: dict[str, LfoMetadata] = {}  # map control plane ID to metadata

    for resource_task_name, control_plane in control_planes.items():
        control_plane_id = resource_task_name.split("-")[-1]

        lfo_env_vars = query_function_app_env_vars(control_plane, resource_task_name)

        monitored_sub_ids_str = lfo_env_vars.get(MONITORED_SUBSCRIPTIONS_KEY, "")
        if not monitored_sub_ids_str:
            continue

        try:
            monitored_sub_ids = loads(monitored_sub_ids_str)
        except JSONDecodeError as e:
            log.error(f"Invalid JSON: {monitored_sub_ids_str}")
            log.error(f"Error: {e}")
            raise

        tag_filters = lfo_env_vars.get(RESOURCE_TAG_FILTERS_KEY, "")
        pii_rules = lfo_env_vars.get(PII_SCRUBBER_RULES_KEY, "")

        existing_lfos[control_plane_id] = LfoMetadata(
            control_plane,
            monitored_subs={
                sub_id: sub_id_to_name[sub_id] for sub_id in monitored_sub_ids
            },
            tag_filter=tag_filters,
            pii_rules=pii_rules,
        )

    return existing_lfos
