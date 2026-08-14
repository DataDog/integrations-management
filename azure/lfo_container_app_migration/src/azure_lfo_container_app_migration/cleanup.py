# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import WEBSITE_CONTRIBUTOR_ID
from azure_logging_install.resource_setup import (
    delete_empty_function_app_plans,
    delete_file_share,
    delete_function_app,
)
from azure_logging_install.role_setup import get_container_app_job_principal_id, remove_role

from .steps import CleanupStep


class DeleteOldFunctionApps(CleanupStep):
    """Deletes the 3 legacy Function Apps and any Consumption plan left with no apps hosted on it."""

    def __init__(self, function_app_config: Configuration):
        super().__init__("Delete old Function Apps")
        self.function_app_config = function_app_config

    def execute(self) -> None:
        control_plane = self.function_app_config.control_plane
        for name in control_plane.task_names:
            delete_function_app(name, control_plane.resource_group, control_plane.sub_id)
        delete_empty_function_app_plans(control_plane.resource_group, control_plane.sub_id)


class DeleteControlPlaneCacheFileShare(CleanupStep):
    """Deletes the storage File Share the old Function Apps used for their content share."""

    def __init__(self, config: Configuration):
        super().__init__("Delete control plane cache File Share")
        self.config = config

    def execute(self) -> None:
        delete_file_share(
            self.config.control_plane_cache_storage_name,
            self.config.control_plane.resource_group,
            self.config.control_plane.sub_id,
        )


class RevokeDeployerWebsiteContributorRole(CleanupStep):
    """Revokes the deployer's Website Contributor role assignment, which was only needed to manage the
    old Function Apps."""

    def __init__(self, config: Configuration):
        super().__init__("Revoke deployer's Website Contributor role assignment")
        self.config = config

    def execute(self) -> None:
        deployer_principal_id = get_container_app_job_principal_id(
            self.config.control_plane.resource_group, self.config.control_plane.sub_id, self.config.deployer_job_name
        )
        remove_role(self.config.control_plane_rg_scope, deployer_principal_id, WEBSITE_CONTRIBUTOR_ID)
