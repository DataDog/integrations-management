# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from typing import Optional

from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR, ROLE_NAMES
from azure_logging_install.role_setup import (
    SUBSCRIPTION_TASK_ROLE_ASSIGNMENTS,
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
            f"  - '{self.config.deployer_job_name}': {ROLE_NAMES[CONTAINER_APPS_JOBS_CONTRIBUTOR]} on resource group "
            f"'{rg}' in subscription {control_plane.sub_id}",
        ]
        # Control plane subscription first, then the monitored subscriptions
        for sub_id in sorted(self.config.all_subscriptions, key=lambda s: (s != control_plane.sub_id, s)):
            label = " (control plane)" if sub_id == control_plane.sub_id else ""
            try:
                exists = resource_group_exists(rg, sub_id)
                reason = "check that you have access to this subscription"
            except Exception as e:
                exists, reason = None, str(e).splitlines()[0]
            if exists is None:
                # Keep describing the rest of the plan; the real migration would fail at this step and roll back
                rg_status = f"could not be checked ({reason}), so the migration would likely fail here and roll back"
            else:
                rg_status = "exists" if exists else "does not exist, would be created"
            lines.append(f"  - Subscription {sub_id}{label}: resource group '{rg}' {rg_status}")
            for assignment in SUBSCRIPTION_TASK_ROLE_ASSIGNMENTS:
                task_name = getattr(control_plane, f"{assignment.task}_task_name")
                scope = f"resource group '{rg}'" if assignment.resource_group_scoped else "the subscription"
                lines.append(f"      '{task_name}': {ROLE_NAMES[assignment.role_id]} on {scope}")
        return "\n".join(lines)


def resource_group_exists(resource_group: str, subscription_id: str) -> Optional[bool]:
    """Returns whether the resource group exists, or None if the check failed (e.g. no access to the subscription).
    can_fail keeps execute() from logging the failure itself, since describe() reports it in the plan."""
    output = execute(
        AzCmd("group", "exists").param("--name", resource_group).param("--subscription", subscription_id), can_fail=True
    )
    output = output.strip().lower()
    if output not in ("true", "false"):
        return None
    return output == "true"
