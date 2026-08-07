# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import shlex
from json import loads
from time import sleep, time

from az_shared.errors import FatalError, TimeoutError
from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import ControlPlane
from azure_logging_install.constants import (
    DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS,
    DEPLOYER_IMAGE_FOR_FUNCTION_APPS,
    IMAGE_REGISTRY_URL,
)

from .container_jobs import TaskSpec
from .steps import Step

JOB_EXECUTION_POLL_INTERVAL_SECONDS = 15
JOB_EXECUTION_TIMEOUT_SECONDS = 600

FAILED_EXECUTION_STATUSES = {"Failed", "Stopped"}


def stop_container_app_job(job_name: str, control_plane: ControlPlane) -> None:
    log.info(f"Stopping Container App Job '{job_name}'")
    execute(
        AzCmd("containerapp", "job stop")
        .param("--name", job_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
    )


def start_container_app_job(job_name: str, control_plane: ControlPlane) -> None:
    log.info(f"Starting Container App Job '{job_name}'")
    execute(
        AzCmd("containerapp", "job start")
        .param("--name", job_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
    )


def stop_function_app(function_app_name: str, control_plane: ControlPlane) -> None:
    log.info(f"Stopping Function App '{function_app_name}'")
    execute(
        AzCmd("functionapp", "stop")
        .param("--name", function_app_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
    )


def start_function_app(function_app_name: str, control_plane: ControlPlane) -> None:
    log.info(f"Starting Function App '{function_app_name}'")
    execute(
        AzCmd("functionapp", "start")
        .param("--name", function_app_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
    )


def set_job_trigger_type(job_name: str, control_plane: ControlPlane, trigger_type: str, cron_expression: str | None) -> None:
    log.info(f"Setting Container App Job '{job_name}' trigger type to {trigger_type}")
    cmd = (
        AzCmd("containerapp", "job update")
        .param("--name", job_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
        .param("--trigger-type", trigger_type)
    )
    if cron_expression:
        cmd = cmd.param("--cron-expression", shlex.quote(cron_expression))
    execute(cmd)


def update_container_app_job_image(job_name: str, control_plane: ControlPlane, image: str) -> None:
    log.info(f"Updating Container App Job '{job_name}' image to {image}")
    execute(
        AzCmd("containerapp", "job update")
        .param("--name", job_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
        .param("--image", image)
    )


def trigger_and_wait_for_job(job_name: str, control_plane: ControlPlane) -> None:
    """Manually trigger a Container App Job execution and poll until it reaches a terminal status."""
    start_container_app_job(job_name, control_plane)

    start_time = time()
    while time() - start_time < JOB_EXECUTION_TIMEOUT_SECONDS:
        output = execute(
            AzCmd("containerapp", "job execution list")
            .param("--name", job_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
            .param("--query", "sort_by(@, &properties.startTime)[-1]")
            .param("--output", "json")
        )
        execution = loads(output) if output.strip() else None
        status = (execution or {}).get("properties", {}).get("status")
        log.debug(f"Job '{job_name}' execution status: {status}")

        if status == "Succeeded":
            log.info(f"Job '{job_name}' execution succeeded")
            return
        if status in FAILED_EXECUTION_STATUSES:
            raise FatalError(f"Job '{job_name}' execution finished with status '{status}'")

        sleep(JOB_EXECUTION_POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Timed out waiting for job '{job_name}' execution to complete after {JOB_EXECUTION_TIMEOUT_SECONDS} seconds"
    )


def build_enablement_steps(
    control_plane: ControlPlane, deployer_job_name: str, task_specs: list[TaskSpec]
) -> list[Step]:
    """Build the Phase 4 steps: pause the deployer and old functions, trigger and verify the new
    jobs, unpause the new jobs, cut the deployer over to the CAJ-aware image, then unpause it.
    """
    steps = [
        Step(
            name="Pause deployer",
            action=lambda: stop_container_app_job(deployer_job_name, control_plane),
            rollback=lambda: start_container_app_job(deployer_job_name, control_plane),
        )
    ]

    old_function_app_names = [
        control_plane.resources_task_name,
        control_plane.scaling_task_name,
        control_plane.diagnostic_settings_task_name,
    ]
    for function_app_name in old_function_app_names:
        steps.append(
            Step(
                name=f"Pause old Function App '{function_app_name}'",
                action=lambda name=function_app_name: stop_function_app(name, control_plane),
                rollback=lambda name=function_app_name: start_function_app(name, control_plane),
            )
        )

    for task in task_specs:
        steps.append(
            Step(
                name=f"Trigger and verify new {task.key} Container App Job",
                action=lambda task=task: trigger_and_wait_for_job(task.new_task_name, control_plane),
            )
        )

    for task in task_specs:
        steps.append(
            Step(
                name=f"Unpause new {task.key} Container App Job",
                action=lambda task=task: set_job_trigger_type(
                    task.new_task_name, control_plane, "Schedule", task.cron_expression
                ),
                rollback=lambda task=task: set_job_trigger_type(task.new_task_name, control_plane, "Manual", None),
            )
        )

    new_deployer_image = f"{IMAGE_REGISTRY_URL}/{DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS}"
    old_deployer_image = f"{IMAGE_REGISTRY_URL}/{DEPLOYER_IMAGE_FOR_FUNCTION_APPS}"
    steps.append(
        Step(
            name="Update deployer image to Container App Job-aware image",
            action=lambda: update_container_app_job_image(deployer_job_name, control_plane, new_deployer_image),
            rollback=lambda: update_container_app_job_image(deployer_job_name, control_plane, old_deployer_image),
        )
    )

    steps.append(
        Step(
            name="Unpause deployer",
            action=lambda: start_container_app_job(deployer_job_name, control_plane),
            rollback=lambda: stop_container_app_job(deployer_job_name, control_plane),
        )
    )

    return steps
