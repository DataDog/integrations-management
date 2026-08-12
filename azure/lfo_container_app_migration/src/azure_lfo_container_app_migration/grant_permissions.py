# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.logs import log
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR
from azure_logging_install.role_setup import (
    get_container_app_job_principal_id,
    grant_permissions,
    remove_role,
    revoke_subscriptions_permissions,
)

from .steps import Step


class GrantContainerAppJobPermissionsStep(Step):
    """Grants the role assignments the new Container App Job identities need: Reader and Data
    Access + Monitoring Contributor for the diagnostic settings job, Contributor for the scaling
    job, Monitoring Reader for the resources job (all per monitored subscription), and Container
    Apps Jobs Contributor for the deployer on the control plane resource group. Reuses the same
    grant_permissions() used by a fresh Container App Job installation.
    """

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
        revoke_subscriptions_permissions(self.config.control_plane, self.config.all_subscriptions)
