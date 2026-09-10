# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.errors import ResourceNotFoundError
from az_shared.logs import log
from azure_logging_install.configuration import Configuration
from azure_logging_install.resource_setup import (
    create_diagnostic_settings_task_container_app_job,
    create_resources_task_container_app_job,
    create_scaling_task_container_app_job,
    delete_container_app_job,
    verify_container_app_job_exists,
)

from .steps import Step

# A cron expression that can never fire, used to prevent the new CAJs from executing until
# all resource setup is complete
NEVER_RUN_CRON_EXPRESSION = "0 0 31 2 *"


class CreateContainerAppJob(Step):
    """Creates a Container App Job in the deployer's Container App environment for a control plane task,
    with a system-assigned managed identity. Reuses the same resource_setup helpers that build a fresh
    installation's Container App Jobs, so job configuration (env vars, secrets, image) is derived entirely
    from the given Configuration.
    """

    def __init__(self, config: Configuration, job_name: str):
        super().__init__(f"Create Container App Job '{job_name}'")
        self.config = config
        self.job_name = job_name
        self._created = False

    def execute(self) -> None:
        if self.does_job_exists():
            log.info(f"Container App Job '{self.job_name}' already exists - skipping creation")
            return

        self.create_job()
        self._created = True

    def rollback(self) -> None:
        if not self._created:
            return
        log.info(f"Deleting Container App Job '{self.job_name}'")
        delete_container_app_job(self.job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id)

    def does_job_exists(self) -> bool:
        try:
            verify_container_app_job_exists(self.job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id)
            return True
        except ResourceNotFoundError:
            return False

    def create_job(self) -> None:
        raise NotImplementedError()


class CreateResourcesTaskContainerAppJob(CreateContainerAppJob):
    def __init__(self, config: Configuration):
        super().__init__(config, config.control_plane.resources_task_name)

    def create_job(self) -> None:
        create_resources_task_container_app_job(self.config, NEVER_RUN_CRON_EXPRESSION)

class CreateDiagnosticSettingsTaskContainerAppJob(CreateContainerAppJob):
    def __init__(self, config: Configuration):
        super().__init__(config, config.control_plane.diagnostic_settings_task_name)

    def create_job(self) -> None:
        create_diagnostic_settings_task_container_app_job(self.config, NEVER_RUN_CRON_EXPRESSION)


class CreateScalingTaskContainerAppJob(CreateContainerAppJob):
    def __init__(self, config: Configuration):
        super().__init__(config, config.control_plane.scaling_task_name)

    def create_job(self) -> None:
        create_scaling_task_container_app_job(self.config, NEVER_RUN_CRON_EXPRESSION)
