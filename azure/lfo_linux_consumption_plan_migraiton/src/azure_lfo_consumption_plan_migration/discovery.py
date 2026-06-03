# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass
from json import JSONDecodeError, loads
from typing import Optional

from az_shared.execute_cmd import execute
from az_shared.logs import log
from common.shell import Cmd

from .constants import RESOURCES_TASK_PREFIX


class AzCmd(Cmd):
    """Builder for Azure CLI commands. Mirrors azure_logging_install.az_cmd.AzCmd."""

    def __init__(self, service: str, action: str):
        super().__init__([service] + action.split())

    def __str__(self) -> str:
        return "az " + super().__str__()


@dataclass(frozen=True)
class ControlPlane:
    control_plane_id: str
    sub_id: str
    resource_group: str
    region: str


def ensure_resource_graph_extension() -> None:
    """Install the resource-graph CLI extension if not already present."""
    if not execute(AzCmd("extension", "show").param("--name", "resource-graph"), can_fail=True):
        execute(AzCmd("extension", "add").param("--name", "resource-graph").flag("--yes"))


def discover_control_planes(
    subscription_filter: Optional[str] = None,
    control_plane_id_filter: Optional[str] = None,
) -> list[ControlPlane]:
    """Use Azure Resource Graph to find every LFO control plane the current
    user can see. Optionally narrow by subscription or by 12-char control
    plane ID suffix.
    """
    ensure_resource_graph_extension()

    where_clauses = [
        "type == 'microsoft.web/sites'",
        "kind contains 'functionapp'",
        f"name startswith '{RESOURCES_TASK_PREFIX}'",
    ]
    if subscription_filter:
        where_clauses.append(f"subscriptionId == '{subscription_filter}'")
    if control_plane_id_filter:
        where_clauses.append(f"name endswith '{control_plane_id_filter}'")

    query = (
        "Resources | where "
        + " and ".join(where_clauses)
        + " | project name, resourceGroup, subscriptionId, location"
    )

    raw = execute(AzCmd("graph", "query").param("-q", query))
    try:
        response = loads(raw)
    except JSONDecodeError as e:
        log.error(f"Invalid JSON from az graph query: {raw}")
        raise RuntimeError(f"Failed to parse ARG response: {e}") from e

    control_planes: list[ControlPlane] = []
    for row in response.get("data", []):
        name = row["name"]
        # name == "resources-task-<12-char-id>"; the last "-" segment is the id.
        control_plane_id = name[len(RESOURCES_TASK_PREFIX):]
        control_planes.append(
            ControlPlane(
                control_plane_id=control_plane_id,
                sub_id=row["subscriptionId"],
                resource_group=row["resourceGroup"],
                region=row["location"],
            )
        )
    return control_planes
