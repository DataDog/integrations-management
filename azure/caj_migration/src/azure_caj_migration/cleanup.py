# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.execute_cmd import execute
from az_shared.logs import log
from azure_logging_install.az_cmd import AzCmd
from azure_logging_install.configuration import (
    LfoControlPlane,
    get_control_plane_cache_storage_name,
)
from azure_logging_install.constants import CONTROL_PLANE_CACHE, WEBSITE_CONTRIBUTOR_ID
from azure_logging_install.role_setup import (
    get_container_app_job_principal_id,
    remove_role,
)


def get_function_app_service_plan_id(function_app_name: str, control_plane: LfoControlPlane) -> str | None:
    try:
        output = execute(
            AzCmd("functionapp", "show")
            .param("--name", function_app_name)
            .param("--resource-group", control_plane.resource_group)
            .param("--subscription", control_plane.sub_id)
            .param("--query", "appServicePlanId")
            .param("--output", "tsv")
        )
        return output.strip() or None
    except Exception as e:
        log.error(f"Could not determine App Service Plan for Function App '{function_app_name}': {e}")
        return None


def delete_function_app(function_app_name: str, control_plane: LfoControlPlane) -> None:
    log.info(f"Deleting Function App '{function_app_name}'")
    execute(
        AzCmd("functionapp", "delete")
        .param("--name", function_app_name)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
    )


def delete_app_service_plan(plan_id: str) -> None:
    log.info(f"Deleting App Service Plan '{plan_id}'")
    execute(AzCmd("appservice", "plan delete").param("--ids", plan_id).flag("--yes"))


def delete_control_plane_cache_file_share(storage_account_name: str, control_plane: LfoControlPlane) -> None:
    log.info(f"Deleting file share '{CONTROL_PLANE_CACHE}' on storage account '{storage_account_name}'")
    execute(
        AzCmd("storage", "share-rm delete")
        .param("--storage-account", storage_account_name)
        .param("--name", CONTROL_PLANE_CACHE)
        .param("--resource-group", control_plane.resource_group)
        .param("--subscription", control_plane.sub_id)
        .flag("--yes")
    )


def remove_deployer_website_contributor_role(deployer_job_name: str, control_plane: LfoControlPlane) -> None:
    control_plane_rg_scope = f"/subscriptions/{control_plane.sub_id}/resourceGroups/{control_plane.resource_group}"
    deployer_principal_id = get_container_app_job_principal_id(
        control_plane.resource_group, control_plane.sub_id, deployer_job_name
    )
    remove_role(control_plane_rg_scope, deployer_principal_id, WEBSITE_CONTRIBUTOR_ID)


def cleanup_old_resources(control_plane: LfoControlPlane, deployer_job_name: str) -> list[str]:
    """Best-effort cleanup of resources made obsolete by the migration. Every step is independent
    and wrapped in its own try/except - failures are logged and returned as a list of messages
    describing what needs manual cleanup. Per instructions.md, Phase 5 has no rollback: errors
    here are surfaced to the customer rather than unwinding the (already successful) migration.
    """
    manual_cleanup_needed: list[str] = []

    old_function_app_names = [
        control_plane.resources_task_name,
        control_plane.scaling_task_name,
        control_plane.diagnostic_settings_task_name,
    ]

    plan_ids: set[str] = set()
    for function_app_name in old_function_app_names:
        plan_id = get_function_app_service_plan_id(function_app_name, control_plane)
        if plan_id:
            plan_ids.add(plan_id)
        try:
            delete_function_app(function_app_name, control_plane)
        except Exception as e:
            log.error(f"Failed to delete Function App '{function_app_name}': {e}")
            manual_cleanup_needed.append(f"Delete Function App '{function_app_name}' manually: {e}")

    for plan_id in plan_ids:
        try:
            delete_app_service_plan(plan_id)
        except Exception as e:
            log.error(f"Failed to delete App Service Plan '{plan_id}': {e}")
            manual_cleanup_needed.append(f"Delete App Service Plan '{plan_id}' manually: {e}")

    control_plane_cache_storage_name = get_control_plane_cache_storage_name(control_plane.id)
    try:
        delete_control_plane_cache_file_share(control_plane_cache_storage_name, control_plane)
    except Exception as e:
        log.error(f"Failed to delete file share on storage account '{control_plane_cache_storage_name}': {e}")
        manual_cleanup_needed.append(
            f"Delete file share '{CONTROL_PLANE_CACHE}' on storage account "
            f"'{control_plane_cache_storage_name}' manually: {e}"
        )

    try:
        remove_deployer_website_contributor_role(deployer_job_name, control_plane)
    except Exception as e:
        log.error(f"Failed to remove deployer's Website Contributor role assignment: {e}")
        manual_cleanup_needed.append(f"Remove deployer's Website Contributor role assignment manually: {e}")

    return manual_cleanup_needed
