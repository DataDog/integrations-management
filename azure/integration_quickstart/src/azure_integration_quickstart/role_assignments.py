# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import shlex
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from az_shared.az_cmd import AzCmd, Cmd, execute, execute_json
from azure_integration_quickstart.util import MAX_WORKERS


def add_role_assignments(client_id: str, roles: Iterable[str], scopes: Iterable[str]) -> None:
    """Assign an app registration the necessary permissions for Datadog to function over the given scopes."""
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        for role in roles:
            for scope in scopes:
                executor.submit(
                    execute,
                    AzCmd("role assignment", "create")
                    .param("--assignee", f'"{client_id}"')
                    .param("--role", f'"{role}')
                    .param("--scope", f'"{scope}"'),
                )


MS_GRAPH_API = "00000003-0000-0000-c000-000000000000"


def add_ms_graph_app_role_assignments(client_id: str, roles: Iterable[str]) -> None:
    """Assign an app registration the necessary app roles for Datadog to function.

    See https://learn.microsoft.com/en-us/graph/permissions-reference for more information."""
    execute(
        AzCmd("ad app permission", "add")
        .param("--id", f'"{client_id}"')
        .param("--api", MS_GRAPH_API)
        .param("--api-permissions", " ".join([f"{role}=Role" for role in roles]))
    )
    execute(AzCmd("ad app permission", "admin-consent").param("--id", f'"{client_id}"'))


def get_assigned_entra_role_ids(user_id: str) -> set[str]:
    return set(
        execute_json(
            Cmd(["az", "rest"])
            .param(
                "-u",
                shlex.quote(
                    "https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments"
                    f"?$filter=principalId eq '{user_id}'"
                    "&$select=roleDefinitionId"
                    "&$top=999"
                ),
            )
            .param("--query", shlex.quote("value[].roleDefinitionId"))
        )
    )


APPLICATION_CREATE_ACTION = "microsoft.directory/applications/create"


def get_role_ids_allowing_application_create() -> set[str]:
    """Fetch roles and filter to ones that include the `microsoft.directory/applications/create` action.

    This is based on a query made by the Azure Portal here: https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Roles/appId/{appId}"""
    return set(
        execute_json(
            Cmd(["az", "rest"])
            .param(
                "-u",
                shlex.quote(
                    "https://graph.microsoft.com/v1.0/roleManagement/directory/roleDefinitions"
                    # Must use `startswith` here instead of `eq` since graph does not support `eq` when filtering arrays of primitives.
                    "?$filter=rolePermissions/any(p:p/allowedResourceActions/any(a:startswith(a,%27microsoft.directory/applications/create%27)))"
                    "&$select=id"
                    # TODO: We also can't specify `$top` in conjunction with the above filter. We may need to paginate.
                ),
            )
            .param("--query", shlex.quote("value[].id"))
        )
    )


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
        assigned_role_ids  # The & operator used below does not short-circuit.
        and (
            # Short circuit to "true" if we see any of these built-in roles that allow creation of applications.
            assigned_role_ids & BUILTIN_ROLE_IDS_ALLOWING_APPLICATION_CREATE
            # Otherwise check against all roles including custom roles.
            or assigned_role_ids & get_role_ids_allowing_application_create()
        )
    )


def can_default_user_create_applications() -> bool:
    return execute_json(
        Cmd(["az", "rest"])
        .param("-u", shlex.quote("https://graph.microsoft.com/v1.0/policies/authorizationPolicy"))
        .param("--query", shlex.quote("defaultUserRolePermissions.allowedToCreateApps"))
    )


def can_create_applications(user_id: str) -> bool:
    return can_default_user_create_applications() or can_create_applications_due_to_role(user_id)


def get_current_user_id() -> str:
    return execute_json(Cmd(["az", "ad", "signed-in-user", "show"]).param("--query", shlex.quote("id")))


def can_current_user_create_applications() -> bool:
    return can_create_applications(get_current_user_id())
