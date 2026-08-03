# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass
from json import JSONDecodeError, loads

from az_shared.errors import FatalError, ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import (
    ControlPlaneType,
    LfoControlPlane,
    get_control_plane_env_name,
    get_deployer_job_name,
)
from azure_logging_install.constants import MONITORED_SUBSCRIPTIONS_KEY
from azure_logging_install.existing_lfo import (
    find_existing_lfo_control_planes,
    query_task_env_vars,
)


@dataclass(frozen=True)
class Deployer:
    job_name: str
    env_name: str


def find_migration_candidates(
    sub_id_to_name: dict[str, str], explicit_control_plane_ids: set[str] | None = None
) -> dict[str, LfoControlPlane]:
    """Find Function-App-type LFO control planes eligible for migration to Container App Jobs.
    If `explicit_control_plane_ids` is given, only those control planes are returned (if found and eligible).
    """
    all_control_planes = find_existing_lfo_control_planes(sub_id_to_name)
    candidates = {
        control_plane_id: control_plane
        for control_plane_id, control_plane in all_control_planes.items()
        if control_plane.type == ControlPlaneType.FunctionApps
    }

    if explicit_control_plane_ids is None:
        return candidates

    missing = explicit_control_plane_ids - candidates.keys()
    if missing:
        log.warning(
            f"Requested control plane ID(s) not found or not eligible for migration: {', '.join(sorted(missing))}"
        )

    return {
        control_plane_id: control_plane
        for control_plane_id, control_plane in candidates.items()
        if control_plane_id in explicit_control_plane_ids
    }


def locate_deployer(control_plane: LfoControlPlane) -> Deployer:
    """Find and verify the deployer's Container App Job and Container App Environment for a control plane."""
    job_name = get_deployer_job_name(control_plane.id)
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", job_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Could not find deployer Container App Job '{job_name}' for control plane {control_plane.id}: {e}"
        ) from e

    env_name = get_control_plane_env_name(control_plane.id, control_plane.region)
    try:
        execute(
            AzCmd("containerapp", "env show")
            .param("--name", env_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Could not find Container App environment '{env_name}' for control plane {control_plane.id}: {e}"
        ) from e

    return Deployer(job_name=job_name, env_name=env_name)


def get_monitored_subscription_ids(control_plane: LfoControlPlane) -> list[str]:
    """Get the list of monitored subscription IDs from the old resources-task's environment variables."""
    env_vars = query_task_env_vars(control_plane, control_plane.resources_task_name)
    monitored_subs_str = env_vars.get(MONITORED_SUBSCRIPTIONS_KEY, "")
    if not monitored_subs_str:
        raise FatalError(
            f"Could not determine monitored subscriptions for control plane {control_plane.id}: "
            f"{MONITORED_SUBSCRIPTIONS_KEY} not set on {control_plane.resources_task_name}"
        )
    try:
        return loads(monitored_subs_str)
    except JSONDecodeError as e:
        raise FatalError(
            f"Invalid {MONITORED_SUBSCRIPTIONS_KEY} value for control plane {control_plane.id}: {monitored_subs_str}"
        ) from e
