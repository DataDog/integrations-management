# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import tempfile
import time
from typing import Iterable

from az_shared.errors import ExistenceCheckError, ResourceNotFoundError, TimeoutError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from .az_cmd import AzCmd, set_subscription
from .configuration import Configuration
from .constants import (
    INITIAL_DEPLOY_IDENTITY_NAME,
    MONITORING_CONTRIBUTOR_ID,
    MONITORING_READER_ID,
    SCALING_CONTRIBUTOR_ID,
    STORAGE_READER_AND_DATA_ACCESS_ID,
    WEBSITE_CONTRIBUTOR_ID,
)


def create_initial_deploy_identity(control_plane_rg: str, control_plane_region: str):
    """Create a managed identity for initial deploy if it does not exist"""
    try:
        log.info("Checking if user-assigned managed identity already exists...")
        execute(
            AzCmd("identity", "show")
            .param("--name", INITIAL_DEPLOY_IDENTITY_NAME)
            .param("--resource-group", control_plane_rg)
        )
        log.info(
            f"User-assigned managed identity '{INITIAL_DEPLOY_IDENTITY_NAME}' already exists - reusing existing identity"
        )
        return
    except ResourceNotFoundError:
        log.info("User-assigned managed identity not found - creating new identity")

    execute(
        AzCmd("identity", "create")
        .param("--name", INITIAL_DEPLOY_IDENTITY_NAME)
        .param("--resource-group", control_plane_rg)
        .param("--location", control_plane_region)
    )


def create_custom_container_app_start_role(role_name: str, role_scope: str):
    """Create a custom role for starting container app jobs if it does not exist"""

    try:
        log.info(f"Checking if custom role definition '{role_name}' already exists...")
        output = execute(
            AzCmd("role", "definition list")
            .param("--name", role_name)
            .param("--scope", role_scope)
            .param("--output", "tsv")
        )
        if output.strip():
            log.info(f"Custom role definition '{role_name}' already exists - reusing existing role")
            return

        # `az role definition list` returns empty string if the role definition doesn't exist
        log.info(f"Custom role definition '{role_name}' not found - creating new role")
    except Exception as e:
        raise ExistenceCheckError(f"Failed to check if custom role definition '{role_name}' exists: {e}") from e

    log.info(f"Creating custom role definition {role_name}")

    role_definition = {
        "Name": role_name,
        "IsCustom": True,
        "Description": "Custom role to start container app jobs",
        "Actions": ["Microsoft.App/jobs/start/action"],
        "NotActions": [],
        "AssignableScopes": [role_scope],
    }

    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as tmpfile:
        json.dump(role_definition, tmpfile)
        tmpfile.flush()
        tmpfile_path = tmpfile.name

    try:
        execute(AzCmd("role", "definition create").param("--role-definition", tmpfile_path))
    except Exception as e:
        raise RuntimeError(f"Failed to create custom role definition '{role_name}': {e}") from e
    finally:
        os.unlink(tmpfile_path)


def role_exists(role_id: str, scope: str, principal_id: str) -> bool:
    """Check if a role assignment exists for a given role, scope, and principal"""

    try:
        output = execute(
            AzCmd("role", "assignment list")
            .param("--assignee", principal_id)
            .param("--role", role_id)
            .param("--scope", scope)
            .param("--query", '"length([])"')
            .param("--output", "tsv")
        )

        return int(output.strip()) > 0
    except (RuntimeError, ValueError) as e:
        log.error(f"Failed to check if role assignment exists: {e}")
        return False


def assign_custom_role_to_identity(
    role_name: str,
    role_id: str,
    control_plane_resource_group: str,
    control_plane_rg_scope: str,
):
    """Assign the custom role to the managed identity if the role assignment does not exist"""
    log.info("Assigning custom role to managed identity")
    identity_id = execute(
        AzCmd("identity", "show")
        .param("--name", INITIAL_DEPLOY_IDENTITY_NAME)
        .param("--resource-group", control_plane_resource_group)
        .param("--query", "principalId")
        .param("--output", "tsv")
    ).strip()

    log.debug(f"Checking if custom role assignment already exists for role {role_name} to identity {identity_id}")
    if role_exists(role_id, control_plane_rg_scope, identity_id):
        log.info(f"Custom role assignment already exists for role {role_name} to managed identity - skipping")
        return
    log.debug("Custom role assignment not found - creating new assignment")

    execute(
        AzCmd("role", "assignment create")
        .param("--role", role_id)
        .param("--assignee-object-id", identity_id)
        .param("--assignee-principal-type", "ServicePrincipal")
        .param("--scope", control_plane_rg_scope)
    )


def wait_for_role_definition_ready(role_name: str, role_scope: str) -> str:
    """Waits for custom role definition to be available in Azure.
    Role definitions are created asynchronously, so we need to wait for them to be available.
    Returns the role ID when the role definition is ready.
    """
    log.info(f"Waiting for role definition {role_name} to be ready...")

    start_time = time.time()
    max_wait_seconds = 120
    poll_interval = 5  # seconds
    while time.time() - start_time < max_wait_seconds:
        try:
            role_id = execute(
                AzCmd("role", "definition list")
                .param("--name", role_name)
                .param("--scope", role_scope)
                .param("--query", '"[0].name"')
                .param("--output", "tsv")
            ).strip()

            if role_id:
                log.info(f"Role definition {role_name} is ready")
                log.debug(f"ID: {role_id}")
                return role_id

        except RuntimeError as e:
            raise ExistenceCheckError(f"Failure to check if role definition {role_name} is ready: {e}") from e

        log.info(f"Role definition {role_name} not yet available, will check again in {poll_interval} seconds")
        time.sleep(poll_interval)

    raise TimeoutError(f"Timeout waiting for role definition {role_name} to be ready after {max_wait_seconds} seconds")


def create_initial_deploy_role(config: Configuration):
    log.info("Creating identity for initial deployment...")
    create_initial_deploy_identity(config.control_plane_rg, config.control_plane_region)

    log.info("Defining custom ContainerAppStart role...")
    role_scope = config.control_plane_rg_scope
    create_custom_container_app_start_role(config.container_app_start_role_name, role_scope)

    role_id = wait_for_role_definition_ready(config.container_app_start_role_name, role_scope)

    log.info("Assigning custom role to identity...")
    assign_custom_role_to_identity(
        config.container_app_start_role_name,
        role_id,
        config.control_plane_rg,
        role_scope,
    )


def get_function_app_principal_id(
    control_plane_resource_group: str, control_plane_sub_id: str, function_app_name: str
) -> str:
    """Get the principal ID of a Function App's managed identity."""
    log.debug(f"Getting principal ID for Function App {function_app_name}")
    output = execute(
        AzCmd("functionapp", "identity show")
        .param("--subscription", control_plane_sub_id)
        .param("--name", function_app_name)
        .param("--resource-group", control_plane_resource_group)
        .param("--query", "principalId")
        .param("--output", "tsv")
    )
    return output.strip()


def get_container_app_job_principal_id(control_plane_resource_group: str, job_name: str) -> str:
    """Get the principal ID of a Container App Job's managed identity."""
    log.debug(f"Getting principal ID for Container App Job {job_name}")
    output = execute(
        AzCmd("containerapp", "job show")
        .param("--name", job_name)
        .param("--resource-group", control_plane_resource_group)
        .param("--query", "identity.principalId")
        .param("--output", "tsv")
    )
    return output.strip()


def assign_role(scope: str, principal_id: str, role_id: str, control_plane_id: str):
    """Assign a role to a principal at a given scope."""

    log.debug(
        f"Checking if role assignment already exists for role {role_id} to principal {principal_id} at scope {scope}"
    )

    if role_exists(role_id, scope, principal_id):
        log.debug(
            f"Role assignment already exists for role {role_id} to principal {principal_id} at scope {scope} - skipping"
        )
        return
    log.debug("Role assignment not found - creating new assignment")

    log.debug(f"Assigning role {role_id} to principal {principal_id} at scope {scope}")
    execute(
        AzCmd("role", "assignment create")
        .param("--assignee-object-id", principal_id)
        .param("--assignee-principal-type", "ServicePrincipal")
        .param("--role", role_id)
        .param("--scope", scope)
        .param("--description", f"ddlfo{control_plane_id}")
    )


def grant_subscriptions_permissions(config: Configuration, sub_ids: Iterable[str]):
    """Grant permissions to a set of subscriptions."""

    resource_principal_id = get_function_app_principal_id(
        config.control_plane_rg, config.control_plane_sub_id, config.resources_task_name
    )
    scaling_principal_id = get_function_app_principal_id(
        config.control_plane_rg, config.control_plane_sub_id, config.scaling_task_name
    )
    diagnostic_principal_id = get_function_app_principal_id(
        config.control_plane_rg,
        config.control_plane_sub_id,
        config.diagnostic_settings_task_name,
    )

    for sub_id in sub_ids:
        log.info(f"Create resource group in subscription: {sub_id}")
        set_subscription(sub_id)
        execute(
            AzCmd("group", "create")
            .param("--name", config.control_plane_rg)
            .param("--location", config.control_plane_region)
        )

        subscription_scope = f"/subscriptions/{sub_id}"
        resource_group_scope = f"{subscription_scope}/resourceGroups/{config.control_plane_rg}"

        log.info(f"Assigning permissions in subscription: {sub_id}")
        assign_role(
            subscription_scope,
            resource_principal_id,
            MONITORING_READER_ID,
            config.control_plane_id,
        )
        assign_role(
            resource_group_scope,
            scaling_principal_id,
            SCALING_CONTRIBUTOR_ID,
            config.control_plane_id,
        )
        assign_role(
            subscription_scope,
            diagnostic_principal_id,
            MONITORING_CONTRIBUTOR_ID,
            config.control_plane_id,
        )
        assign_role(
            resource_group_scope,
            diagnostic_principal_id,
            STORAGE_READER_AND_DATA_ACCESS_ID,
            config.control_plane_id,
        )

    set_subscription(config.control_plane_sub_id)
    log.info("Subscriptions permission setup complete")


def grant_permissions(config: Configuration):
    """Grant permissions for control plane and monitored subscriptions"""
    log.info("Setting up permissions for control plane and monitored subscriptions...")

    log.info("Assigning Website Contributor role to deployer container app job...")
    deployer_principal_id = get_container_app_job_principal_id(config.control_plane_rg, config.deployer_job_name)
    assign_role(
        config.control_plane_rg_scope,
        deployer_principal_id,
        WEBSITE_CONTRIBUTOR_ID,
        config.control_plane_id,
    )

    grant_subscriptions_permissions(config, config.all_subscriptions)
