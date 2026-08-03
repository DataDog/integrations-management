# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import shlex
from dataclasses import dataclass

from az_shared.errors import ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import LfoControlPlane
from azure_logging_install.constants import (
    DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX,
    DIAGNOSTIC_SETTINGS_TASK_CRON,
    IMAGE_REGISTRY_URL,
    MONITORED_SUBSCRIPTIONS_KEY,
    PII_SCRUBBER_RULES_KEY,
    RESOURCE_TAG_FILTERS_KEY,
    RESOURCES_TASK_CRON,
    SCALING_TASK_CRON,
)
from azure_logging_install.existing_lfo import query_task_env_vars

from .steps import Step

RESOURCES = "resources"
SCALING = "scaling"
DIAGNOSTIC_SETTINGS = "diagnostic_settings"


@dataclass(frozen=True)
class TaskSpec:
    key: str
    old_task_name: str
    new_task_name: str
    image: str
    cron_expression: str
    replica_timeout: int


@dataclass(frozen=True)
class CreatedJob:
    task: TaskSpec
    already_existed: bool


def get_task_specs(control_plane: LfoControlPlane) -> list[TaskSpec]:
    """The Container App Job replacement for each of the 3 Function App tasks.
    Resources and scaling task names are unchanged (the CAJ and Function App resource types
    can share a name within the same resource group); only the diagnostic-settings task gets
    a new name, since it already differs between control plane types.
    """
    return [
        TaskSpec(
            key=RESOURCES,
            old_task_name=control_plane.resources_task_name,
            new_task_name=control_plane.resources_task_name,
            image=f"{IMAGE_REGISTRY_URL}/resources-task:latest", # TODO replace with helper function
            cron_expression=RESOURCES_TASK_CRON,
            replica_timeout=300,
        ),
        TaskSpec(
            key=SCALING,
            old_task_name=control_plane.scaling_task_name,
            new_task_name=control_plane.scaling_task_name,
            image=f"{IMAGE_REGISTRY_URL}/scaling-task:latest",  # TODO replace with helper function
            cron_expression=SCALING_TASK_CRON,
            replica_timeout=600,
        ),
        TaskSpec(
            key=DIAGNOSTIC_SETTINGS,
            old_task_name=control_plane.diagnostic_settings_task_name,
            new_task_name=f"{DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX}{control_plane.id}",  # TODO replace with helper function
            image=f"{IMAGE_REGISTRY_URL}/diagnostic-settings-task:latest",  # TODO replace with helper function
            cron_expression=DIAGNOSTIC_SETTINGS_TASK_CRON,
            replica_timeout=300,
        ),
    ]


def job_exists(name: str, control_plane: LfoControlPlane) -> bool:
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
        )
        return True
    except ResourceNotFoundError:
        return False


def _translate_env_vars(control_plane: LfoControlPlane, task: TaskSpec, old_env_vars: dict[str, str]) -> list[str]:
    common = [
        "AzureWebJobsStorage=secretref:connection-string",
        "DD_API_KEY=secretref:dd-api-key",
        f"SUBSCRIPTION_ID={control_plane.sub_id}",
        f"DD_SITE={old_env_vars.get('DD_SITE', '')}",
        f"DD_TELEMETRY={old_env_vars.get('DD_TELEMETRY', 'false')}",
        f"CONTROL_PLANE_ID={control_plane.id}",
        f"CONTROL_PLANE_REGION={control_plane.region}",
        f"LOG_LEVEL={old_env_vars.get('LOG_LEVEL', 'INFO')}",
    ]

    if task.key == RESOURCES:
        specific = [
            shlex.quote(f"{MONITORED_SUBSCRIPTIONS_KEY}={old_env_vars.get(MONITORED_SUBSCRIPTIONS_KEY, '[]')}"),
            shlex.quote(f"{RESOURCE_TAG_FILTERS_KEY}={old_env_vars.get(RESOURCE_TAG_FILTERS_KEY, '')}"),
        ]
    elif task.key == DIAGNOSTIC_SETTINGS:
        specific = [f"RESOURCE_GROUP={control_plane.resource_group}"]
    else:  # SCALING
        specific = [
            f"RESOURCE_GROUP={control_plane.resource_group}",
            f"FORWARDER_IMAGE={IMAGE_REGISTRY_URL}/forwarder:latest",
            shlex.quote(f"{PII_SCRUBBER_RULES_KEY}={old_env_vars.get(PII_SCRUBBER_RULES_KEY, '')}"),
        ]

    return common + specific


def create_paused_task_job(control_plane: LfoControlPlane, control_plane_env_name: str, task: TaskSpec) -> CreatedJob:
    """Idempotently create a paused (Manual trigger-type) Container App Job for a control plane task,
    with environment variables copied from the corresponding old Function App.
    """
    if job_exists(task.new_task_name, control_plane):
        log.info(f"Container App Job '{task.new_task_name}' already exists - reusing existing job")
        return CreatedJob(task=task, already_existed=True)

    old_env_vars = query_task_env_vars(control_plane, task.old_task_name)

    log.info(f"Creating paused Container App Job '{task.new_task_name}'")
    secrets = [
        shlex.quote(f"connection-string={old_env_vars.get('AzureWebJobsStorage', '')}"),
        shlex.quote(f"dd-api-key={old_env_vars.get('DD_API_KEY', '')}"),
    ]
    execute(
        AzCmd("containerapp", "job create")
        .param("--name", task.new_task_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
        .param("--environment", control_plane_env_name)
        .param("--replica-timeout", str(task.replica_timeout))
        .param("--replica-retry-limit", "0")
        .param("--trigger-type", "Manual")
        .param("--image", task.image)
        .param("--cpu", "0.5")
        .param("--memory", "1Gi")
        .param("--parallelism", "1")
        .param("--replica-completion-count", "1")
        .flag("--mi-system-assigned")
        .param_list("--env-vars", _translate_env_vars(control_plane, task, old_env_vars))
        .param_list("--secrets", secrets)
    )
    return CreatedJob(task=task, already_existed=False)


def delete_task_job(control_plane: LfoControlPlane, created_job: CreatedJob) -> None:
    """Rollback for create_paused_task_job - only deletes jobs this run actually created."""
    if created_job.already_existed:
        log.debug(f"Skipping rollback deletion of pre-existing job '{created_job.task.new_task_name}'")
        return
    log.info(f"Rolling back: deleting Container App Job '{created_job.task.new_task_name}'")
    execute(
        AzCmd("containerapp", "job delete")
        .param("--name", created_job.task.new_task_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
        .flag("--yes")
    )


def build_container_job_steps(
    control_plane: LfoControlPlane, control_plane_env_name: str, created_jobs: dict[str, CreatedJob]
) -> list[Step]:
    """Build the Phase 2 steps: create 3 paused Container App Jobs. `created_jobs` is populated
    (keyed by task key) as each step's action runs, so later phases can inspect what happened.
    """
    steps = []
    for task in get_task_specs(control_plane):

        def action(task=task):
            created_jobs[task.key] = create_paused_task_job(control_plane, control_plane_env_name, task)

        def rollback(task=task):
            created_job = created_jobs.get(task.key)
            if created_job is not None:
                delete_task_job(control_plane, created_job)

        steps.append(Step(name=f"Create {task.key} Container App Job", action=action, rollback=rollback))
    return steps
