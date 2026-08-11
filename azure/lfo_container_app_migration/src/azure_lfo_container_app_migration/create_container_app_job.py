# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import shlex

from az_shared.errors import ResourceNotFoundError
from az_shared.logs import log
from azure_logging_install.configuration import Configuration, ControlPlane
from azure_logging_install.existing_lfo import query_task_env_vars
from azure_logging_install.resource_setup import (
    create_container_app_job,
    delete_container_app_job,
    verify_container_app_job_exists,
)

from .steps import Step

# A cron expression that can never fire, used to prevent the new CAJs from executing until 
# all resource setup is complete
NEVER_RUN_CRON_EXPRESSION = "0 0 31 2 *"


class CreateContainerAppJob(Step):
    """Creates a Container App Job in the deployer's Container App environment that mirrors the
    configuration of an existing Function App task.
    """

    def __init__(self, config: Configuration, function_app_name: str, job_name: str, job_image: str, job_timeout: str):
        super().__init__(f"Create Container App Job '{job_name}'")
        self.config = config
        self.function_app_name = function_app_name
        self.job_name = job_name
        self.job_image = job_image
        self.job_timeout = job_timeout
        self._created = False

    def execute(self) -> None:
        control_plane: ControlPlane = self.config.control_plane

        try:
            verify_container_app_job_exists(self.job_name, control_plane.resource_group, control_plane.sub_id)
            log.info(f"Container App Job '{self.job_name}' already exists - skipping creation")
            return
        except ResourceNotFoundError:
            pass

        existing_env_vars = query_task_env_vars(control_plane, self.function_app_name)
        env_vars = [f"{name}={shlex.quote(value)}" for name, value in existing_env_vars.items()]

        create_container_app_job(
            job_name=self.job_name,
            resource_group=control_plane.resource_group,
            subscription_id=control_plane.sub_id,
            environment_name=self.config.control_plane_env_name,
            image=self.image,
            env_vars=env_vars,
            secrets=[],
            cron_expression=NEVER_RUN_CRON_EXPRESSION,
            timeout=self.timeout,
            retry_limit="0",
        )
        self._created = True

    def rollback(self) -> None:
        if not self._created:
            return
        control_plane = self.config.control_plane
        delete_container_app_job(self.job_name, control_plane.resource_group, control_plane.sub_id)


def CreateScalingTaskCAJ(CreateContainerAppJob):
    def __init__(self, config: Configuration):
        super().__init__(f"Create Container App Job '{job_name}'")
        self.config = config
        self.job_name = job_name
        self.image = image
        self.timeout = timeout
        self._created = False