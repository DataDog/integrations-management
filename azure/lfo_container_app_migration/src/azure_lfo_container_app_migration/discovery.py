# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass
from json import JSONDecodeError, loads

from az_shared.errors import FatalError, ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import (
    ControlPlane,
    ControlPlaneType,
    get_control_plane_env_name,
    get_deployer_job_name,
)
from azure_logging_install.constants import MONITORED_SUBSCRIPTIONS_KEY
from azure_logging_install.existing_lfo import find_existing_lfo_control_planes, query_task_env_vars



def _verify_deployer(control_plane: ControlPlane) -> None:
    """Verify the deployer's Container App Job and Container App Environment exist."""
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", control_plane.deployer_job_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Could not find deployer Container App Job '{control_plane.deployer_job_name}' for control plane {control_plane.id}: {e}"
        ) from e

    try:
        execute(
            AzCmd("containerapp", "env show")
            .param("--name", control_plane.container_app_env_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
        )
    except ResourceNotFoundError as e:
        raise FatalError(
            f"Could not find Container App environment '{control_plane.container_app_env_name}' for control plane {control_plane.id}: {e}"
        ) from e

    return None