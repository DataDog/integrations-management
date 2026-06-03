# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Phase 3 - role assignments for the 3 new jobs (per monitored subscription)
plus the deployer (Container Apps Jobs Contributor in the control plane RG)."""

from dataclasses import dataclass
from json import JSONDecodeError, loads
from typing import Callable

from az_shared.constants import GRAPH_ASSIGNEE_NOT_IN_DIRECTORY
from az_shared.errors import FatalError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from ..constants import (
    CONTAINER_APPS_JOBS_CONTRIBUTOR_ID,
    MONITORED_SUBSCRIPTIONS_KEY,
    MONITORING_CONTRIBUTOR_ID,
    MONITORING_READER_ID,
    SCALING_CONTRIBUTOR_ID,
    STORAGE_READER_AND_DATA_ACCESS_ID,
    diagnostic_settings_job_name,
    resources_job_name,
    scaling_job_name,
)
from ..discovery import AzCmd
from ..steps import Step
from .setup import ControlPlaneContext


@dataclass(frozen=True)
class RoleAssignment:
    principal_id: str
    role_id: str
    scope: str
    description: str  # used for the assignment description tag + log lines


def _get_job_principal_id(ctx: ControlPlaneContext, job_name: str) -> str:
    output = execute(
        AzCmd("containerapp", "job show")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--query", "identity.principalId")
        .param("--output", "tsv")
    )
    principal_id = output.strip()
    if not principal_id:
        raise FatalError(f"Container App Job '{job_name}' has no system-assigned identity principalId")
    return principal_id


def _role_assignment_exists(role_id: str, scope: str, principal_id: str) -> bool:
    try:
        output = execute(
            AzCmd("role", "assignment list")
            .param("--assignee", principal_id)
            .param("--role", role_id)
            .param("--scope", scope)
            .param("--query", '"length([])"')
            .param("--output", "tsv")
        )
        return int(output.strip()) > 0
    except (RuntimeError, ValueError) as e:
        if not (GRAPH_ASSIGNEE_NOT_IN_DIRECTORY in str(e) and principal_id in str(e)):
            log.warning(f"Failed to check role assignment existence: {e}")
        return False


def _assign_role(assignment: RoleAssignment) -> None:
    if _role_assignment_exists(assignment.role_id, assignment.scope, assignment.principal_id):
        log.debug(
            f"Role {assignment.role_id} already assigned to {assignment.principal_id} at {assignment.scope}"
        )
        return
    execute(
        AzCmd("role", "assignment create")
        .param("--assignee-object-id", assignment.principal_id)
        .param("--assignee-principal-type", "ServicePrincipal")
        .param("--role", assignment.role_id)
        .param("--scope", assignment.scope)
        .param("--description", assignment.description)
    )


def _unassign_role(assignment: RoleAssignment) -> None:
    output = execute(
        AzCmd("role", "assignment list")
        .param("--scope", assignment.scope)
        .param("--assignee", assignment.principal_id)
        .param("--role", assignment.role_id)
        .param("--query", "[].id")
        .param("--output", "tsv")
    )
    assignment_ids = [aid.strip() for aid in output.strip().split() if aid.strip()]
    if assignment_ids:
        execute(AzCmd("role", "assignment delete").param("--ids", assignment_ids[0]))


def _get_deployer_principal_id(ctx: ControlPlaneContext) -> str:
    return _get_job_principal_id(ctx, ctx.deployer_job)


def _parse_monitored_subscriptions(ctx: ControlPlaneContext) -> list[str]:
    raw = ctx.resources_task_env.get(MONITORED_SUBSCRIPTIONS_KEY, "")
    if not raw:
        raise FatalError(
            f"resources-task for control plane '{ctx.control_plane.control_plane_id}' is missing "
            f"{MONITORED_SUBSCRIPTIONS_KEY}; cannot determine which subscriptions to assign roles in."
        )
    try:
        subs = loads(raw)
    except JSONDecodeError as e:
        raise FatalError(f"Invalid JSON in {MONITORED_SUBSCRIPTIONS_KEY}: {raw}") from e
    if not isinstance(subs, list):
        raise FatalError(f"{MONITORED_SUBSCRIPTIONS_KEY} is not a list: {raw}")
    return [str(s) for s in subs]


def _build_assignments(ctx: ControlPlaneContext) -> list[RoleAssignment]:
    cp = ctx.control_plane
    cp_id = cp.control_plane_id

    resources_pid = _get_job_principal_id(ctx, resources_job_name(cp_id))
    scaling_pid = _get_job_principal_id(ctx, scaling_job_name(cp_id))
    diag_pid = _get_job_principal_id(ctx, diagnostic_settings_job_name(cp_id))
    deployer_pid = _get_deployer_principal_id(ctx)

    monitored_subs = _parse_monitored_subscriptions(ctx)

    assignments: list[RoleAssignment] = []
    description_tag = f"ddlfo{cp_id}"

    for sub_id in monitored_subs:
        sub_scope = f"/subscriptions/{sub_id}"
        rg_scope = f"{sub_scope}/resourceGroups/{cp.resource_group}"

        # diagnostic-settings job: Reader and Data Access on forwarder RG +
        # Monitoring Contributor on subscription
        assignments.append(
            RoleAssignment(diag_pid, STORAGE_READER_AND_DATA_ACCESS_ID, rg_scope, description_tag)
        )
        assignments.append(
            RoleAssignment(diag_pid, MONITORING_CONTRIBUTOR_ID, sub_scope, description_tag)
        )

        # scaling job: Contributor on forwarder RG
        assignments.append(
            RoleAssignment(scaling_pid, SCALING_CONTRIBUTOR_ID, rg_scope, description_tag)
        )

        # resources job: Monitoring Reader on subscription
        assignments.append(
            RoleAssignment(resources_pid, MONITORING_READER_ID, sub_scope, description_tag)
        )

    # Deployer: Container Apps Jobs Contributor on the control plane RG
    # (replaces the v1 Website Contributor assignment).
    control_plane_rg_scope = f"/subscriptions/{cp.sub_id}/resourceGroups/{cp.resource_group}"
    assignments.append(
        RoleAssignment(deployer_pid, CONTAINER_APPS_JOBS_CONTRIBUTOR_ID, control_plane_rg_scope, description_tag)
    )

    return assignments


def assign_roles_steps(ctx: ControlPlaneContext) -> list[Step]:
    """One Step per role assignment so failures undo only what was created."""
    assignments = _build_assignments(ctx)
    steps: list[Step] = []
    for a in assignments:
        do: Callable[[], None] = lambda x=a: _assign_role(x)
        undo: Callable[[], None] = lambda x=a: _unassign_role(x)
        steps.append(
            Step(
                name=f"Assign role {a.role_id} to principal {a.principal_id} at {a.scope}",
                do=do,
                undo=undo,
            )
        )
    return steps
