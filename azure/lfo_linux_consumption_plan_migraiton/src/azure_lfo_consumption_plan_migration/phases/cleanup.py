# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Phase 5 - cleanup. Errors are collected as 'manual action required'
messages rather than triggering rollback (per the instructions)."""

from typing import Optional

from az_shared.errors import ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from ..constants import (
    CONTROL_PLANE_CACHE_FILE_SHARE,
    WEBSITE_CONTRIBUTOR_ID,
)
from ..discovery import AzCmd
from ..steps import Step
from .setup import ControlPlaneContext


def _control_plane_cache_storage_name(control_plane_id: str) -> str:
    """Mirrors azure_logging_install.configuration.Configuration."""
    return f"lfostorage{control_plane_id}"


def _get_function_app_plan_id(ctx: ControlPlaneContext, function_app: str) -> Optional[str]:
    try:
        output = execute(
            AzCmd("functionapp", "show")
            .param("--subscription", ctx.control_plane.sub_id)
            .param("--name", function_app)
            .param("--resource-group", ctx.control_plane.resource_group)
            .param("--query", "appServicePlanId")
            .param("--output", "tsv")
        )
        return output.strip() or None
    except ResourceNotFoundError:
        return None


def _delete_function_app(ctx: ControlPlaneContext, function_app: str) -> None:
    try:
        execute(
            AzCmd("functionapp", "delete")
            .param("--subscription", ctx.control_plane.sub_id)
            .param("--name", function_app)
            .param("--resource-group", ctx.control_plane.resource_group)
        )
        log.info(f"Deleted function app '{function_app}'")
    except ResourceNotFoundError:
        log.info(f"Function app '{function_app}' already deleted")


def _delete_plan(plan_id: str) -> None:
    execute(
        AzCmd("appservice", "plan delete")
        .param("--ids", plan_id)
        .flag("--yes")
    )
    log.info(f"Deleted app service plan '{plan_id}'")


def _delete_file_share(ctx: ControlPlaneContext) -> None:
    storage = _control_plane_cache_storage_name(ctx.control_plane.control_plane_id)
    try:
        execute(
            AzCmd("storage", "share-rm delete")
            .param("--storage-account", storage)
            .param("--name", CONTROL_PLANE_CACHE_FILE_SHARE)
            .param("--resource-group", ctx.control_plane.resource_group)
            .flag("--yes")
        )
        log.info(f"Deleted file share '{CONTROL_PLANE_CACHE_FILE_SHARE}' on '{storage}'")
    except ResourceNotFoundError:
        log.info(f"File share '{CONTROL_PLANE_CACHE_FILE_SHARE}' on '{storage}' already deleted")


def _remove_deployer_website_contributor(ctx: ControlPlaneContext) -> None:
    cp = ctx.control_plane
    scope = f"/subscriptions/{cp.sub_id}/resourceGroups/{cp.resource_group}"
    principal_id = execute(
        AzCmd("containerapp", "job show")
        .param("--subscription", cp.sub_id)
        .param("--name", ctx.deployer_job)
        .param("--resource-group", cp.resource_group)
        .param("--query", "identity.principalId")
        .param("--output", "tsv")
    ).strip()
    if not principal_id:
        log.info("Deployer has no managed identity; nothing to remove")
        return

    output = execute(
        AzCmd("role", "assignment list")
        .param("--scope", scope)
        .param("--assignee", principal_id)
        .param("--role", WEBSITE_CONTRIBUTOR_ID)
        .param("--query", "[].id")
        .param("--output", "tsv")
    )
    assignment_ids = [aid.strip() for aid in output.strip().split() if aid.strip()]
    if not assignment_ids:
        log.info("Deployer Website Contributor assignment not found - already removed")
        return
    execute(AzCmd("role", "assignment delete").param("--ids", assignment_ids[0]))
    log.info("Removed deployer Website Contributor role assignment")


def cleanup_steps(ctx: ControlPlaneContext) -> list[tuple[Step, str]]:
    """Return (step, manual_action_hint) pairs. The runner will call
    run_best_effort, recording the hint on any failure."""
    function_apps = [ctx.resources_task, ctx.scaling_task, ctx.diagnostic_settings_task]
    # Capture plan IDs before we delete the function apps - once they're gone
    # we can't query their plan reference.
    plan_ids: set[str] = set()
    for fa in function_apps:
        plan_id = _get_function_app_plan_id(ctx, fa)
        if plan_id:
            plan_ids.add(plan_id)

    out: list[tuple[Step, str]] = []
    for fa in function_apps:
        out.append(
            (
                Step(name=f"Delete function app '{fa}'", do=lambda x=fa: _delete_function_app(ctx, x)),
                f"Run: az functionapp delete --subscription {ctx.control_plane.sub_id} "
                f"--resource-group {ctx.control_plane.resource_group} --name {fa}",
            )
        )
    for pid in plan_ids:
        out.append(
            (
                Step(name=f"Delete app service plan '{pid}'", do=lambda p=pid: _delete_plan(p)),
                f"Run: az appservice plan delete --ids {pid} --yes",
            )
        )
    storage = _control_plane_cache_storage_name(ctx.control_plane.control_plane_id)
    out.append(
        (
            Step(name=f"Delete file share '{CONTROL_PLANE_CACHE_FILE_SHARE}' on '{storage}'", do=lambda: _delete_file_share(ctx)),
            f"Run: az storage share-rm delete --storage-account {storage} "
            f"--name {CONTROL_PLANE_CACHE_FILE_SHARE} --resource-group {ctx.control_plane.resource_group} --yes",
        )
    )
    out.append(
        (
            Step(
                name=f"Remove deployer Website Contributor role on '{ctx.control_plane.resource_group}'",
                do=lambda: _remove_deployer_website_contributor(ctx),
            ),
            "Manually remove the Website Contributor role assignment on the deployer's "
            "managed identity over the control plane resource group via the Azure portal.",
        )
    )
    return out
