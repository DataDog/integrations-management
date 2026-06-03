# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Phase 2 - create the 3 paused Container App Jobs (Manual trigger).

The job is created in the deployer's existing Container App environment with
a system-assigned managed identity and env vars copied from the matching
Function App. Sensitive values are moved to --secrets and referenced via
secretref:.
"""

import shlex
from dataclasses import dataclass
from typing import Callable

from az_shared.errors import ResourceNotFoundError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from ..constants import (
    DIAGNOSTIC_SETTINGS_TASK_IMAGE,
    FUNCTION_RUNTIME_ENV_KEYS_TO_DROP,
    JOB_CPU,
    JOB_MEMORY,
    JOB_PARALLELISM,
    JOB_REPLICA_COMPLETION_COUNT,
    JOB_REPLICA_RETRY_LIMIT,
    JOB_REPLICA_TIMEOUT,
    RESOURCES_TASK_IMAGE,
    SCALING_TASK_IMAGE,
    diagnostic_settings_job_name,
    resources_job_name,
    scaling_job_name,
)
from ..discovery import AzCmd
from ..steps import Step
from .setup import ControlPlaneContext

# Env-var keys whose values should be moved to Container App secrets and
# referenced via `secretref:`. The secret name is the dict value.
SECRET_ENV_KEYS: dict[str, str] = {
    "DD_API_KEY": "dd-api-key",
    "AzureWebJobsStorage": "connection-string",
}


@dataclass(frozen=True)
class JobSpec:
    name: str
    image: str
    raw_env: dict[str, str]


def _job_specs(ctx: ControlPlaneContext) -> list[JobSpec]:
    cp_id = ctx.control_plane.control_plane_id
    return [
        JobSpec(resources_job_name(cp_id), RESOURCES_TASK_IMAGE, ctx.resources_task_env),
        JobSpec(scaling_job_name(cp_id), SCALING_TASK_IMAGE, ctx.scaling_task_env),
        JobSpec(
            diagnostic_settings_job_name(cp_id),
            DIAGNOSTIC_SETTINGS_TASK_IMAGE,
            ctx.diagnostic_settings_task_env,
        ),
    ]


def _build_env_and_secrets(raw_env: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (env_var_args, secret_args) for `az containerapp job create`.

    Strips function-runtime-only keys, hoists sensitive values into secrets,
    and rewrites those keys to use `secretref:` syntax.
    """
    env_pairs: list[str] = []
    secret_pairs: list[str] = []

    for key, value in raw_env.items():
        if key in FUNCTION_RUNTIME_ENV_KEYS_TO_DROP and key not in SECRET_ENV_KEYS:
            continue
        if key in SECRET_ENV_KEYS:
            secret_name = SECRET_ENV_KEYS[key]
            secret_pairs.append(shlex.quote(f"{secret_name}={value}"))
            env_pairs.append(f"{key}=secretref:{secret_name}")
            continue
        env_pairs.append(shlex.quote(f"{key}={value}"))

    return env_pairs, secret_pairs


def _job_exists(ctx: ControlPlaneContext, job_name: str) -> bool:
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--subscription", ctx.control_plane.sub_id)
            .param("--name", job_name)
            .param("--resource-group", ctx.control_plane.resource_group)
        )
        return True
    except ResourceNotFoundError:
        return False


def _create_paused_job(ctx: ControlPlaneContext, spec: JobSpec) -> None:
    if _job_exists(ctx, spec.name):
        log.info(f"Container App Job '{spec.name}' already exists - skipping create")
        return

    env_args, secret_args = _build_env_and_secrets(spec.raw_env)

    cmd = (
        AzCmd("containerapp", "job create")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", spec.name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .param("--environment", ctx.env_name)
        .param("--trigger-type", "Manual")
        .param("--replica-timeout", JOB_REPLICA_TIMEOUT)
        .param("--replica-retry-limit", JOB_REPLICA_RETRY_LIMIT)
        .param("--parallelism", JOB_PARALLELISM)
        .param("--replica-completion-count", JOB_REPLICA_COMPLETION_COUNT)
        .param("--image", spec.image)
        .param("--cpu", JOB_CPU)
        .param("--memory", JOB_MEMORY)
        .flag("--mi-system-assigned")
    )
    if env_args:
        cmd = cmd.param_list("--env-vars", env_args, quote=False)
    if secret_args:
        cmd = cmd.param_list("--secrets", secret_args, quote=False)

    execute(cmd)
    log.info(f"Created paused Container App Job '{spec.name}'")


def _delete_job(ctx: ControlPlaneContext, job_name: str) -> None:
    if not _job_exists(ctx, job_name):
        return
    log.info(f"Rollback: deleting Container App Job '{job_name}'")
    execute(
        AzCmd("containerapp", "job delete")
        .param("--subscription", ctx.control_plane.sub_id)
        .param("--name", job_name)
        .param("--resource-group", ctx.control_plane.resource_group)
        .flag("--yes")
    )


def create_paused_jobs_steps(ctx: ControlPlaneContext) -> list[Step]:
    """One Step per job so partial failures roll back only what was actually created."""
    steps: list[Step] = []
    for spec in _job_specs(ctx):
        do: Callable[[], None] = lambda s=spec: _create_paused_job(ctx, s)
        undo: Callable[[], None] = lambda s=spec: _delete_job(ctx, s.name)
        steps.append(Step(name=f"Create paused Container App Job '{spec.name}'", do=do, undo=undo))
    return steps
