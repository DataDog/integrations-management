# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

from az_shared.execute_cmd import execute, execute_json
from azure_integration_quickstart.permissions import EntraIdPermission
from azure_integration_quickstart.util import MAX_WORKERS
from common.odata import odata_query
from common.shell import Cmd


def add_role_assignments(client_id: str, roles: Iterable[str], scopes: Iterable[str]) -> None:
    """Assign an app registration the necessary permissions for Datadog to function over the given scopes."""
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        for role in roles:
            for scope in scopes:
                executor.submit(
                    execute,
                    Cmd(["az", "role", "assignment", "create"])
                    .param("--role", role)
                    .param("--assignee", client_id)
                    .param("--scope", scope),
                )


MS_GRAPH_API = "00000003-0000-0000-c000-000000000000"


def add_ms_graph_app_role_assignments(client_id: str, roles: Iterable[str]) -> None:
    """Assign an app registration the necessary app roles for Datadog to function.

    See https://learn.microsoft.com/en-us/graph/permissions-reference for more information."""
    execute(
        Cmd(["az", "ad", "app", "permission", "add"])
        .param("--id", client_id)
        .param("--api", MS_GRAPH_API)
        .param_list("--api-permissions", [f"{role}=Role" for role in roles])
    )
    execute(Cmd(["az", "ad", "app", "permission", "admin-consent"]).param("--id", client_id))


def get_assigned_entra_role_ids(user_id: str) -> set[str]:
    return set(
        execute_json(
            Cmd(["az", "rest"])
            .param("--resource", "https://management.core.windows.net/")
            .param(
                "-u",
                "https://api.azrbac.mspim.azure.com/api/v2/privilegedAccess/aadroles/roleAssignments?"
                + odata_query(
                    select="roleDefinitionId",
                    filter=f"subjectId eq '{user_id}' and assignmentState eq 'Active'",
                    top=999,
                ),
            )
            .param("--query", "value[].roleDefinitionId")
        )
    )


def get_role_permissions(role_id: Iterable[str]) -> Iterable[EntraIdPermission]:
    return execute_json(
        Cmd(["az", "rest"])
        .param(
            "-u",
            "https://graph.microsoft.com/v1.0/roleManagement/directory/roleDefinitions?"
            + odata_query(select="rolePermissions", filter=f"id eq '{role_id}'"),
        )
        .param("--query", "value[].rolePermissions")
    )[0]


APPLICATION_CREATE_ACTION = "microsoft.directory/applications/create"
BUILTIN_ROLE_IDS_ALLOWING_APPLICATION_CREATE = {
    "62e90394-69f5-4237-9190-012177145e10",  # Global Administrator
    "9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3",  # Application Administrator
    "158c047a-c907-4556-b7ef-446551a6b5f7",  # Cloud Application Administrator
    "e8611ab8-c189-46e8-94e1-60213ab1f814",  # Privileged Role Administrator
    "8ac3fc64-6eca-42ea-9e69-59f4c7b60eb2",  # Hybrid Identity Administrator
}


def can_create_applications_due_to_role(user_id: str) -> bool:
    assigned_role_ids = get_assigned_entra_role_ids(user_id)
    return bool(
        assigned_role_ids
        and (
            # Short circuit to "true" if we see any of these built-in roles that allow creation of applications.
            assigned_role_ids & BUILTIN_ROLE_IDS_ALLOWING_APPLICATION_CREATE
            # Otherwise check against all roles including custom roles.
            or any(
                p
                # TODO: Consisder parallelizing if slow. But, note that this short-circuits.
                for p in chain.from_iterable(get_role_permissions(role_id) for role_id in assigned_role_ids)
                if APPLICATION_CREATE_ACTION.lower() in (a.lower() for a in p["allowedResourceActions"])
            )
        )
    )


def can_default_user_create_applications() -> bool:
    return execute_json(
        Cmd(["az", "rest"])
        .param("-u", "https://graph.microsoft.com/v1.0/policies/authorizationPolicy")
        .param("--query", "defaultUserRolePermissions.allowedToCreateApps")
    )


def can_create_applications(user_id: str) -> bool:
    return can_default_user_create_applications() or can_create_applications_due_to_role(user_id)


def get_current_user_id() -> str:
    return execute_json(Cmd(["az", "ad", "signed-in-user", "show"]).param("--query", "id"))


def can_current_user_create_applications() -> bool:
    return can_create_applications(get_current_user_id())
