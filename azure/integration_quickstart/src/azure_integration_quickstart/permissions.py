# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from collections.abc import Container, Iterable
from dataclasses import dataclass
from typing import TypedDict

from azure_integration_quickstart.actions import Action, ActionContainer
from azure_integration_quickstart.util import UnionContainer, request


class Permission(TypedDict, total=False):
    """An Azure permission.

    See https://learn.microsoft.com/en-us/rest/api/authorization/permissions/list-for-resource-group#permission."""

    actions: list[Action]
    notActions: list[Action]
    dataActions: list[Action]
    notDataActions: list[Action]


def get_permissions(auth_token: str, scope: str) -> list[Permission]:
    """Fetch the permissions granted over a given scope."""
    response, _ = request(
        "GET",
        f"https://management.azure.com{scope}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
        headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
    )
    return json.loads(response)["value"]


@dataclass
class FlatPermission:
    """A consolidated permission used to determine whether actions are supported.

    See https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/control-plane-and-data-plane.
    """

    actions: Container[Action]
    data_actions: Container[Action]


def flatten_permissions(permissions: Iterable[Permission]) -> FlatPermission:
    """Create a single permission used to determine whether actions are supported by any of the given permissions."""
    return FlatPermission(
        UnionContainer([ActionContainer(p.get("actions") or [], p.get("notActions") or []) for p in permissions]),
        UnionContainer(
            [ActionContainer(p.get("dataActions") or [], p.get("notDataActions") or []) for p in permissions]
        ),
    )


def get_flat_permission(auth_token: str, scope: str) -> FlatPermission:
    """Fetch the consolidated permission granted over a given scope."""
    return flatten_permissions(get_permissions(auth_token, scope))
