# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Phase 1 - Setup. Pure discovery; no side effects, no rollback needed."""

from dataclasses import dataclass
from json import JSONDecodeError, loads

from az_shared.errors import FatalError, ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from ..constants import (
    control_plane_env_name,
    deployer_job_name,
    diagnostic_settings_task_name,
    resources_task_name,
    scaling_task_name,
)
from ..discovery import AzCmd, ControlPlane


@dataclass(frozen=True)
class ControlPlaneContext:
    """Everything Phases 2-5 need about a control plane, captured up front."""

    control_plane: ControlPlane
    deployer_job: str
    env_name: str
    resources_task: str
    scaling_task: str
    diagnostic_settings_task: str
    resources_task_env: dict[str, str]
    scaling_task_env: dict[str, str]
    diagnostic_settings_task_env: dict[str, str]


def build_context(cp: ControlPlane) -> ControlPlaneContext:
    """Phase 1 entry point: locate the deployer + env and snapshot env vars off
    the 3 existing function apps."""
    log.info(f"Phase 1: discovering existing resources for control plane '{cp.control_plane_id}'")

    deployer = deployer_job_name(cp.control_plane_id)
    env = control_plane_env_name(cp.control_plane_id, cp.region)

    verify_deployer_job_exists(cp.sub_id, cp.resource_group, deployer)
    verify_container_app_environment_exists(cp.sub_id, cp.resource_group, env)

    resources = resources_task_name(cp.control_plane_id)
    scaling = scaling_task_name(cp.control_plane_id)
    diag = diagnostic_settings_task_name(cp.control_plane_id)

    return ControlPlaneContext(
        control_plane=cp,
        deployer_job=deployer,
        env_name=env,
        resources_task=resources,
        scaling_task=scaling,
        diagnostic_settings_task=diag,
        resources_task_env=query_function_app_env_vars(cp.sub_id, cp.resource_group, resources),
        scaling_task_env=query_function_app_env_vars(cp.sub_id, cp.resource_group, scaling),
        diagnostic_settings_task_env=query_function_app_env_vars(cp.sub_id, cp.resource_group, diag),
    )


def query_function_app_env_vars(sub_id: str, resource_group: str, function_app: str) -> dict[str, str]:
    """Return every appsetting on a function app as a dict."""
    raw = execute(
        AzCmd("functionapp", "config appsettings list")
        .param("--subscription", sub_id)
        .param("--name", function_app)
        .param("--resource-group", resource_group)
        .param("--output", "json")
    )
    try:
        rows = loads(raw)
        return {row["name"]: row["value"] for row in rows}
    except (JSONDecodeError, KeyError, TypeError) as e:
        raise FatalError(f"Failed to parse appsettings for {function_app}: {e}") from e


def verify_deployer_job_exists(sub_id: str, resource_group: str, job_name: str) -> None:
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--subscription", sub_id)
            .param("--name", job_name)
            .param("--resource-group", resource_group)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Expected deployer Container App Job '{job_name}' was not found in {resource_group} "
            f"({sub_id}). Cannot migrate this control plane."
        ) from e


def verify_container_app_environment_exists(sub_id: str, resource_group: str, env_name: str) -> None:
    try:
        execute(
            AzCmd("containerapp", "env show")
            .param("--subscription", sub_id)
            .param("--name", env_name)
            .param("--resource-group", resource_group)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Expected Container App environment '{env_name}' was not found in {resource_group} "
            f"({sub_id}). Cannot migrate this control plane."
        ) from e

