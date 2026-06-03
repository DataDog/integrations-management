# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Phase 4 - enablement.

1. Pause deployer (stop running execution + flip trigger to Manual).
2. Stop the 3 function apps.
3. Manually trigger each new job and wait for success. Failure here aborts
   the migration (the prior steps roll back, leaving the customer on the
   original function-app architecture).
4. Convert the 3 new jobs from Manual to Schedule.
5. Update deployer image to the new container-app-jobs-aware image.
6. Resume deployer (flip trigger back to Schedule with original cron).
"""

import json
import shlex
import time
from typing import Callable

from az_shared.errors import FatalError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from ..constants import (
    DIAGNOSTIC_SETTINGS_TASK_CRON,
    JOB_EXECUTION_POLL_INTERVAL_SECONDS,
    JOB_EXECUTION_TIMEOUT_SECONDS,
    NEW_DEPLOYER_IMAGE,
    RESOURCES_TASK_CRON,
    SCALING_TASK_CRON,
    diagnostic_settings_job_name,
    resources_job_name,
    scaling_job_name,
)
from ..discovery import AzCmd
from ..steps import Step
from .setup import ControlPlaneContext


# ---------------------------------------------------------------------------
# Deployer state captured pre-migration so rollback can restore it.
# Mutable so each step's `undo` closure can read what an earlier step saved.
# ---------------------------------------------------------------------------


class DeployerState:
    original_cron: str = ""
    original_image: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_show(ctx: ControlPlaneContext, job_name: str) -> dict:
    raw = execute(
        AzCmd("containerapp", "job show")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--output", "json")
    )
    return json.loads(raw)


def _job_stop(ctx: ControlPlaneContext, job_name: str) -> None:
    """Stop any currently-running execution. Tolerates 'no execution running'."""
    try:
        execute(
            AzCmd("containerapp", "job stop")
            .param("--subscription", ctx.control_plane.sub_id)
            .param("--name", job_name)
            .param("--resource-group", ctx.control_plane.resource_group)
        )
    except RuntimeError as e:
        # No running execution is not a failure for us.
        log.debug(f"job stop on '{job_name}' returned: {e}")


def _set_job_trigger(
    ctx: ControlPlaneContext,
    job_name: str,
    trigger_type: str,
    cron_expression: str = "",
) -> None:
    cmd = (
        AzCmd("containerapp", "job update")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--trigger-type", trigger_type)
    )
    if trigger_type == "Schedule":
        if not cron_expression:
            raise FatalError(f"Cron expression required to set Schedule trigger on '{job_name}'")
        cmd = cmd.param("--cron-expression", shlex.quote(cron_expression), quote=False)
    execute(cmd)


def _set_job_image(ctx: ControlPlaneContext, job_name: str, image: str) -> None:
    execute(
        AzCmd("containerapp", "job update")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--image", image)
    )


def _functionapp_state_cmd(ctx: ControlPlaneContext, function_app: str, action: str) -> None:
    execute(
        AzCmd("functionapp", action)
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", function_app)
        .param("--resource-group", ctx.control_plane.resource_group)
    )


def _trigger_job_and_wait(ctx: ControlPlaneContext, job_name: str) -> None:
    """Start a single execution of a Manual-trigger job and poll until terminal."""
    raw = execute(
        AzCmd("containerapp", "job start")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--output", "json")
    )
    try:
        execution_name = json.loads(raw)["name"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise FatalError(f"Could not parse execution name from job start of '{job_name}': {raw}") from e

    log.info(f"Started execution '{execution_name}' of job '{job_name}'; waiting for completion...")

    deadline = time.time() + JOB_EXECUTION_TIMEOUT_SECONDS
    while time.time() < deadline:
        raw_exec = execute(
            AzCmd("containerapp", "job execution show")
            .param("--subscription", ctx.control_plane.sub_id)
            .param("--name", job_name)
            .param("--resource-group", ctx.control_plane.resource_group)
            .param("--job-execution-name", execution_name)
            .param("--output", "json")
        )
        try:
            status = json.loads(raw_exec).get("properties", {}).get("status", "")
        except json.JSONDecodeError as e:
            raise FatalError(f"Invalid JSON from job execution show: {raw_exec}") from e

        log.debug(f"Execution '{execution_name}' status: {status}")

        if status == "Succeeded":
            log.info(f"Execution '{execution_name}' succeeded")
            return
        if status in ("Failed", "Degraded", "Stopped"):
            raise FatalError(
                f"Execution '{execution_name}' of job '{job_name}' ended in status '{status}'. "
                "This usually indicates an existing problem with the control plane that must be "
                "fixed before migrating - aborting and rolling back."
            )
        time.sleep(JOB_EXECUTION_POLL_INTERVAL_SECONDS)

    raise FatalError(
        f"Timed out after {JOB_EXECUTION_TIMEOUT_SECONDS}s waiting for execution "
        f"'{execution_name}' of job '{job_name}'"
    )


# ---------------------------------------------------------------------------
# Step builders
# ---------------------------------------------------------------------------


def _pause_deployer_steps(ctx: ControlPlaneContext, state: DeployerState) -> Step:
    """Snapshot the deployer's cron, switch trigger to Manual, stop any running execution."""

    def do() -> None:
        data = _job_show(ctx, ctx.deployer_job)
        config = data.get("properties", {}).get("configuration", {})
        trigger_config = config.get("triggerType")
        schedule = config.get("scheduleTriggerConfig", {}) or {}
        state.original_cron = schedule.get("cronExpression", "")
        log.info(
            f"Captured deployer state: triggerType={trigger_config}, cron='{state.original_cron}'"
        )
        # Flip to Manual so cron can't fire during migration, then stop any running execution.
        _set_job_trigger(ctx, ctx.deployer_job, "Manual")
        _job_stop(ctx, ctx.deployer_job)

    def undo() -> None:
        if state.original_cron:
            _set_job_trigger(ctx, ctx.deployer_job, "Schedule", state.original_cron)
        else:
            log.warning(
                "No original cron captured for deployer; leaving trigger as Manual. "
                "Manual intervention may be needed to restore the schedule."
            )

    return Step(name=f"Pause deployer job '{ctx.deployer_job}'", do=do, undo=undo)


def _stop_function_app_step(ctx: ControlPlaneContext, function_app: str) -> Step:
    return Step(
        name=f"Stop function app '{function_app}'",
        do=lambda: _functionapp_state_cmd(ctx, function_app, "stop"),
        undo=lambda: _functionapp_state_cmd(ctx, function_app, "start"),
    )


def _trigger_and_wait_step(ctx: ControlPlaneContext, job_name: str) -> Step:
    # No meaningful undo for "ran a job once" - the side effects are in storage.
    # Rollback of earlier steps will restart the function apps; any data drift
    # introduced by the run is flagged in the rollback log.
    return Step(
        name=f"Trigger and wait for new job '{job_name}'",
        do=lambda: _trigger_job_and_wait(ctx, job_name),
        undo=lambda: log.warning(
            f"Note: job '{job_name}' was executed once during migration. "
            "Any state it wrote to control-plane cache cannot be cleanly reverted."
        ),
    )


def _unpause_new_job_step(ctx: ControlPlaneContext, job_name: str, cron: str) -> Step:
    return Step(
        name=f"Switch new job '{job_name}' to Schedule trigger ({cron})",
        do=lambda: _set_job_trigger(ctx, job_name, "Schedule", cron),
        undo=lambda: _set_job_trigger(ctx, job_name, "Manual"),
    )


def _bump_deployer_image_step(ctx: ControlPlaneContext, state: DeployerState) -> Step:
    def do() -> None:
        data = _job_show(ctx, ctx.deployer_job)
        containers = (
            data.get("properties", {})
            .get("template", {})
            .get("containers", [])
        )
        if not containers:
            raise FatalError(f"Deployer job '{ctx.deployer_job}' has no containers in template")
        state.original_image = containers[0].get("image", "")
        log.info(f"Captured deployer image '{state.original_image}'; bumping to '{NEW_DEPLOYER_IMAGE}'")
        _set_job_image(ctx, ctx.deployer_job, NEW_DEPLOYER_IMAGE)

    def undo() -> None:
        if state.original_image:
            log.warning(
                f"Restoring deployer image to '{state.original_image}'. "
                "If the new image already wrote control-plane state, manual data fixup may be required."
            )
            _set_job_image(ctx, ctx.deployer_job, state.original_image)

    return Step(name=f"Update deployer image on '{ctx.deployer_job}'", do=do, undo=undo)


def _resume_deployer_step(ctx: ControlPlaneContext, state: DeployerState) -> Step:
    def do() -> None:
        if not state.original_cron:
            raise FatalError(
                "Cannot resume deployer: original cron was not captured during pause step."
            )
        _set_job_trigger(ctx, ctx.deployer_job, "Schedule", state.original_cron)

    def undo() -> None:
        _set_job_trigger(ctx, ctx.deployer_job, "Manual")
        _job_stop(ctx, ctx.deployer_job)

    return Step(name=f"Resume deployer job '{ctx.deployer_job}'", do=do, undo=undo)


def enablement_steps(ctx: ControlPlaneContext) -> list[Step]:
    state = DeployerState()
    cp_id = ctx.control_plane.control_plane_id

    new_jobs_and_crons: list[tuple[Callable[[str], str], str]] = [
        (resources_job_name, RESOURCES_TASK_CRON),
        (scaling_job_name, SCALING_TASK_CRON),
        (diagnostic_settings_job_name, DIAGNOSTIC_SETTINGS_TASK_CRON),
    ]

    steps: list[Step] = []
    steps.append(_pause_deployer_steps(ctx, state))
    for fn_app in (ctx.resources_task, ctx.scaling_task, ctx.diagnostic_settings_task):
        steps.append(_stop_function_app_step(ctx, fn_app))
    for namer, _ in new_jobs_and_crons:
        steps.append(_trigger_and_wait_step(ctx, namer(cp_id)))
    for namer, cron in new_jobs_and_crons:
        steps.append(_unpause_new_job_step(ctx, namer(cp_id), cron))
    steps.append(_bump_deployer_image_step(ctx, state))
    steps.append(_resume_deployer_step(ctx, state))
    return steps
