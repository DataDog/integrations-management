# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.logs import log
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import DEPLOYER_TASK_CRON, DIAGNOSTIC_SETTINGS_TASK_CRON, RESOURCES_TASK_CRON, SCALING_TASK_CRON
from azure_logging_install.resource_setup import (
    start_function_app,
    stop_function_app,
    update_container_app_job_cron_expression,
    update_container_app_job_image,
)

from .create_container_app_job import NEVER_RUN_CRON_EXPRESSION
from .steps import Step

# Real schedule for each task Job, keyed by the ControlPlane attribute holding its name.
_TASK_CRON_EXPRESSIONS = {
    "resources_task_name": RESOURCES_TASK_CRON,
    "diagnostic_settings_task_name": DIAGNOSTIC_SETTINGS_TASK_CRON,
    "scaling_task_name": SCALING_TASK_CRON,
}


class PauseDeployer(Step):
    """Disables the deployer Container App Job's schedule so it isn't running while the old Function Apps
    are paused and the new task Jobs are enabled. Uses a never-run cron rather than `job stop`/`job start`,
    since stopping a Schedule-triggered Job's executions can leave the Job in a Suspended state that
    `job start` cannot recover from."""

    def __init__(self, config: Configuration):
        super().__init__(f"Pause deployer '{config.deployer_job_name}'")
        self.config = config

    def execute(self) -> None:
        update_container_app_job_cron_expression(
            self.config.deployer_job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, NEVER_RUN_CRON_EXPRESSION
        )

    def rollback(self) -> None:
        log.info(f"Resuming deployer '{self.config.deployer_job_name}'")
        update_container_app_job_cron_expression(
            self.config.deployer_job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, DEPLOYER_TASK_CRON
        )


class PauseOldFunctionApps(Step):
    """Stops the 3 Function Apps that ran the control plane tasks before the migration."""

    def __init__(self, function_app_config: Configuration):
        super().__init__("Pause old Function App tasks")
        self.function_app_config = function_app_config

    def execute(self) -> None:
        for name in self.function_app_config.control_plane.task_names:
            stop_function_app(name, self.function_app_config.control_plane.resource_group, self.function_app_config.control_plane.sub_id)

    def rollback(self) -> None:
        log.info("Resuming old Function App tasks")
        for name in self.function_app_config.control_plane.task_names:
            start_function_app(name, self.function_app_config.control_plane.resource_group, self.function_app_config.control_plane.sub_id)


class UnpauseNewContainerAppJobs(Step):
    """Enables the 3 new task Container App Jobs by restoring their real schedule, replacing the
    never-run placeholder cron they were created with."""

    def __init__(self, config: Configuration):
        super().__init__("Enable new task Container App Jobs")
        self.config = config

    def execute(self) -> None:
        for attr, cron in _TASK_CRON_EXPRESSIONS.items():
            name = getattr(self.config.control_plane, attr)
            update_container_app_job_cron_expression(name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, cron)

    def rollback(self) -> None:
        log.info("Reverting new task Container App Jobs to paused schedule")
        for attr in _TASK_CRON_EXPRESSIONS:
            name = getattr(self.config.control_plane, attr)
            update_container_app_job_cron_expression(
                name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, NEVER_RUN_CRON_EXPRESSION
            )


class UpdateDeployerImage(Step):
    """Updates the deployer Job's image to the one that supports Container App Jobs."""

    def __init__(self, caj_config: Configuration, function_app_config: Configuration):
        super().__init__(f"Update deployer image to '{caj_config.deployer_image_url}'")
        self.caj_config = caj_config
        self.function_app_config = function_app_config

    def execute(self) -> None:
        update_container_app_job_image(
            self.caj_config.deployer_job_name,
            self.caj_config.control_plane.resource_group,
            self.caj_config.control_plane.sub_id,
            self.caj_config.deployer_image_url,
        )

    def rollback(self) -> None:
        log.info(f"Reverting deployer image to '{self.function_app_config.deployer_image_url}'")
        update_container_app_job_image(
            self.caj_config.deployer_job_name,
            self.caj_config.control_plane.resource_group,
            self.caj_config.control_plane.sub_id,
            self.function_app_config.deployer_image_url,
        )


class UnpauseDeployer(Step):
    """Restores the deployer Container App Job's real schedule now that it is running the Container App
    Job-compatible image."""

    def __init__(self, config: Configuration):
        super().__init__(f"Unpause deployer '{config.deployer_job_name}'")
        self.config = config

    def execute(self) -> None:
        update_container_app_job_cron_expression(
            self.config.deployer_job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, DEPLOYER_TASK_CRON
        )

    def rollback(self) -> None:
        log.info(f"Pausing deployer '{self.config.deployer_job_name}'")
        update_container_app_job_cron_expression(
            self.config.deployer_job_name, self.config.control_plane.resource_group, self.config.control_plane.sub_id, NEVER_RUN_CRON_EXPRESSION
        )
