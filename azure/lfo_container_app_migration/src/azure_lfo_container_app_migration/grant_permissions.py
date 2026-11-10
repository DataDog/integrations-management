# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR
from azure_logging_install.role_setup import (
    get_container_app_job_principal_id,
    grant_permissions,
    remove_role,
    revoke_subscriptions_role_assignments,
)

from .steps import Step


class GrantContainerAppJobPermissionsStep(Step):
    """Creates the role assignments the 3 task Jobs and the deployer needs."""

    def __init__(self, config: Configuration):
        super().__init__("Grant role assignments to Container App Job identities")
        self.config = config

    def execute(self) -> None:
        grant_permissions(self.config)

    def rollback(self) -> None:
        log.info("Revoking role assignments granted to Container App Job identities")
        deployer_principal_id = get_container_app_job_principal_id(
            self.config.control_plane.resource_group, self.config.control_plane.sub_id, self.config.deployer_job_name
        )
        remove_role(self.config.control_plane_rg_scope, deployer_principal_id, CONTAINER_APPS_JOBS_CONTRIBUTOR)
        revoke_subscriptions_role_assignments(self.config.control_plane, self.config.all_subscriptions)

    def describe(self) -> str:
        """Lists the role assignments grant_permissions would create, and the resource groups it would create."""
        control_plane = self.config.control_plane
        rg = control_plane.resource_group
        lines = [
            self.name,
            f"  - '{self.config.deployer_job_name}': Container Apps Jobs Contributor on resource group '{rg}' "
            f"in subscription {control_plane.sub_id}",
        ]
        for sub_id in sorted(self.config.all_subscriptions):
            label = " (control plane)" if sub_id == control_plane.sub_id else ""
            try:
                rg_status = "exists" if resource_group_exists(rg, sub_id) else "does not exist, would be created"
            except Exception as e:
                # Keep describing the rest of the plan; the real migration would fail at this step and roll back
                rg_status = f"could not be checked, so the migration would likely fail here and roll back ({e})"
            lines += [
                f"  - Subscription {sub_id}{label}: resource group '{rg}' {rg_status}",
                f"      '{control_plane.resources_task_name}': Monitoring Reader on the subscription",
                f"      '{control_plane.scaling_task_name}': Contributor on resource group '{rg}'",
                f"      '{control_plane.diagnostic_settings_task_name}': Monitoring Contributor on the subscription, "
                f"Reader and Data Access on resource group '{rg}'",
            ]
        return "\n".join(lines)


def resource_group_exists(resource_group: str, subscription_id: str) -> bool:
    output = execute(AzCmd("group", "exists").param("--name", resource_group).param("--subscription", subscription_id))
    return output.strip().lower() == "true"
