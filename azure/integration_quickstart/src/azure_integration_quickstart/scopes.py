# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from abc import ABC, abstractmethod
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Literal

from az_shared.errors import AccessError
from az_shared.execute_cmd import execute_json
from azure_integration_quickstart.permissions import FlatPermission, get_flat_permission
from azure_integration_quickstart.util import MAX_WORKERS
from common.shell import Cmd

ScopeType = Literal["subscription", "management_group"]


@dataclass
class Scope(ABC):
    """An Azure scope."""

    id: str
    name: str

    @property
    @abstractmethod
    def scope_type(self) -> ScopeType:
        pass

    @property
    @abstractmethod
    def scope(self) -> str:
        pass

    def __hash__(self) -> int:
        return hash(self.id)


class Subscription(Scope):
    """An Azure subscription."""

    @property
    def scope_type(self) -> ScopeType:
        return "subscription"

    @property
    def scope(self) -> str:
        return f"/subscriptions/{self.id}"


@dataclass
class ManagementGroup(Scope):
    """An Azure management group."""

    subscriptions: list[Subscription]

    @property
    def scope_type(self) -> ScopeType:
        return "management_group"

    @property
    def scope(self) -> str:
        return self.id

    @staticmethod
    def from_dict(d: dict) -> "ManagementGroup":
        return ManagementGroup(d["id"], d["name"], [Subscription(**s) for s in d["subscriptions"]])


@dataclass
class ManagementGroupListResult:
    id: str
    name: str
    az_name: str


ASSIGN_ROLES_ACTION = "Microsoft.Authorization/roleAssignments/write"


def filter_scopes_by_permission(scopes: Sequence[Scope]) -> list[Scope]:
    """Filter scopes based on whether the user can assign roles to them.

    Return a list of bools representing whether the scope at each corresponding index should be included."""
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures: list[Future[FlatPermission]] = [executor.submit(get_flat_permission, scope.scope) for scope in scopes]
    return [
        scope
        for i, scope in enumerate(scopes)
        if not futures[i].exception() and ASSIGN_ROLES_ACTION in futures[i].result().actions
    ]


def get_subscription_scopes(tenant_id: str) -> list[Subscription]:
    return [
        Subscription(**s)
        for s in execute_json(
            Cmd(["az", "account", "list"])
            .param("--query", "[?tenantId=='%s'].{id:id, name:name}" % tenant_id)
            .param("-o", "json")
        )
    ]


def get_management_group_from_list_result(list_result: ManagementGroupListResult) -> ManagementGroup:
    subscriptions_az_response = execute_json(
        Cmd(["az", "account", "management-group", "show"])
        .param("--name", list_result.az_name)
        .flag("-e")
        .flag("-r")
        .param("--query", "children[].{id:id, name:name}")
        .param("-o", "json")
    )

    if subscriptions_az_response:
        subscriptions = [Subscription(**s) for s in subscriptions_az_response if s["id"].startswith("/subscriptions/")]
    else:
        subscriptions = []
    return ManagementGroup(list_result.id, list_result.name, subscriptions)


def get_management_group_scopes(tenant_id: str) -> list[ManagementGroup]:
    try:
        mgroup_list_results = [
            ManagementGroupListResult(**lr)
            for lr in execute_json(
                Cmd(["az", "account", "management-group", "list"])
                .param("--query", "[?tenantId=='%s'].{id:id, az_name:name, name:displayName}" % tenant_id)
                .param("-o", "json")
            )
        ]
    except AccessError:
        # Expected, this means the user doesn't have permissions for any management groups but not necessarily blocking
        return []

    # enrich each result with all of its children subscriptions (at any depth)
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        management_groups = executor.map(get_management_group_from_list_result, mgroup_list_results)
    return list(management_groups)


def get_available_regions() -> list[str]:
    """Get the list of Azure regions (by name) that the user's tenant has access to."""
    regions = execute_json(Cmd(["az", "account", "list-locations"]).param("--query", "[].name").param("-o", "json"))
    print("Available regions:", regions)
    return regions


def flatten_scopes(scopes: Sequence[Scope]) -> set[Subscription]:
    """Convert a list of scopes into a set of subscriptions, with management groups represented as their constituent subscriptions"""
    return set(
        [s for s in scopes if isinstance(s, Subscription)]
        + [s for subs in [m.subscriptions for m in scopes if isinstance(m, ManagementGroup)] for s in subs]
    )


def report_available_scopes(step_metadata: dict) -> tuple[list[Scope], list[Scope]]:
    """Send Datadog the subscriptions and management groups that the user has permission to grant access to."""
    tenant_id = execute_json(Cmd(["az", "account", "show"]).param("--query", "tenantId"))
    subscriptions = filter_scopes_by_permission(get_subscription_scopes(tenant_id))
    management_groups = filter_scopes_by_permission(get_management_group_scopes(tenant_id))
    regions = get_available_regions()
    step_metadata["subscriptions"] = [asdict(s) for s in subscriptions]
    step_metadata["management_groups"] = [asdict(m) for m in management_groups]
    step_metadata["regions"] = regions
    return subscriptions, management_groups
