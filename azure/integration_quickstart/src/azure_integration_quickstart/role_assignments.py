# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from az_shared.az_cmd import AzCmd, execute
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
