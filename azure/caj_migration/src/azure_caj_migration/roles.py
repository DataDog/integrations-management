# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Iterable

from azure_logging_install.configuration import ControlPlaneType, LfoControlPlane
from azure_logging_install.constants import (
    CONTAINER_APPS_JOBS_CONTRIBUTOR_ID,
    MONITORING_CONTRIBUTOR_ID,
    MONITORING_READER_ID,
    SCALING_CONTRIBUTOR_ID,
    STORAGE_READER_AND_DATA_ACCESS_ID,
)
from azure_logging_install.role_setup import (
    assign_role,
    get_container_app_job_principal_id,
    grant_subscriptions_permissions,
    remove_role,
)

from .steps import Step


def as_container_app_job_control_plane(control_plane: LfoControlPlane) -> LfoControlPlane:
    """A synthetic view of the control plane as if it were already Container-App-Job-based, so the
    existing `azure_logging_install` role helpers (which key task names off `control_plane.type`)
    resolve the *new* CAJ task names instead of the old Function App ones.
    """
    return LfoControlPlane(
        id=control_plane.id,
        sub_id=control_plane.sub_id,
        sub_name=control_plane.sub_name,
        resource_group=control_plane.resource_group,
        region=control_plane.region,
        type=ControlPlaneType.ContainerAppJobs,
    )


def _revoke_subscriptions_role_assignments(caj_control_plane: LfoControlPlane, sub_ids: Iterable[str]) -> None:
    """Rollback for grant_subscriptions_permissions - removes only the 4 role assignments per
    subscription. Deliberately does NOT reuse `revoke_subscriptions_permissions`, which also
    deletes the monitored subscription's forwarder resource group; that resource group pre-exists
    the migration and must not be touched.
    """
    resource_principal_id = get_container_app_job_principal_id(
        caj_control_plane.resource_group, caj_control_plane.sub_id, caj_control_plane.resources_task_name
    )
    scaling_principal_id = get_container_app_job_principal_id(
        caj_control_plane.resource_group, caj_control_plane.sub_id, caj_control_plane.scaling_task_name
    )
    diagnostic_principal_id = get_container_app_job_principal_id(
        caj_control_plane.resource_group, caj_control_plane.sub_id, caj_control_plane.diagnostic_settings_task_name
    )

    for sub_id in sub_ids:
        subscription_scope = f"/subscriptions/{sub_id}"
        resource_group_scope = f"{subscription_scope}/resourceGroups/{caj_control_plane.resource_group}"
        for scope, principal_id, role_id in [
            (subscription_scope, resource_principal_id, MONITORING_READER_ID),
            (resource_group_scope, scaling_principal_id, SCALING_CONTRIBUTOR_ID),
            (subscription_scope, diagnostic_principal_id, MONITORING_CONTRIBUTOR_ID),
            (resource_group_scope, diagnostic_principal_id, STORAGE_READER_AND_DATA_ACCESS_ID),
        ]:
            remove_role(scope, principal_id, role_id)


def build_role_steps(
    control_plane: LfoControlPlane, deployer_job_name: str, monitored_sub_ids: Iterable[str]
) -> list[Step]:
    """Build the Phase 3 steps: grant the new Container App Job tasks the same per-subscription
    permissions the old Function Apps had, and grant the deployer Container Apps Jobs Contributor
    (the CAJ replacement for Website Contributor) on the control plane resource group.
    """
    caj_control_plane = as_container_app_job_control_plane(control_plane)
    monitored_sub_ids = list(monitored_sub_ids)
    control_plane_rg_scope = f"/subscriptions/{control_plane.sub_id}/resourceGroups/{control_plane.resource_group}"

    def grant_monitored_subscriptions_action():
        grant_subscriptions_permissions(caj_control_plane, monitored_sub_ids)

    def grant_monitored_subscriptions_rollback():
        _revoke_subscriptions_role_assignments(caj_control_plane, monitored_sub_ids)

    def grant_deployer_role_action():
        deployer_principal_id = get_container_app_job_principal_id(
            control_plane.resource_group, control_plane.sub_id, deployer_job_name
        )
        assign_role(control_plane_rg_scope, deployer_principal_id, CONTAINER_APPS_JOBS_CONTRIBUTOR_ID, control_plane.id)

    def grant_deployer_role_rollback():
        deployer_principal_id = get_container_app_job_principal_id(
            control_plane.resource_group, control_plane.sub_id, deployer_job_name
        )
        remove_role(control_plane_rg_scope, deployer_principal_id, CONTAINER_APPS_JOBS_CONTRIBUTOR_ID)

    return [
        Step(
            name="Grant new Container App Job tasks permissions on monitored subscriptions",
            action=grant_monitored_subscriptions_action,
            rollback=grant_monitored_subscriptions_rollback,
        ),
        Step(
            name="Grant deployer Container Apps Jobs Contributor role",
            action=grant_deployer_role_action,
            rollback=grant_deployer_role_rollback,
        ),
    ]
