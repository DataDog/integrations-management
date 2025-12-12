# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from collections.abc import Iterable

from az_shared.execute_cmd import execute
from az_shared.logs import log
from common.shell import Cmd


class AzCmd(Cmd):
    """Builder for Azure CLI commands."""

    def __init__(self, service: str, action: str):
        """Initialize with service and action (e.g., 'functionapp', 'create')."""
        super().__init__([service] + action.split())

    def __str__(self) -> str:
        return "az " + super().__str__()

    def param(self, key: str, value: str, quote: bool = False) -> "Cmd":
        """Adds a key-value pair parameter"""
        return super().param(key, value, quote=quote)

    def param_list(self, key: str, values: Iterable[str], quote: bool = False) -> "Cmd":
        """Adds a list of parameters with the same key"""
        return super().param_list(key, values, quote=quote)


def list_users_subscriptions() -> dict[str, str]:
    user_subs = execute(AzCmd("account", "list").param("--output", "json"))
    subs_json = json.loads(user_subs)
    return {sub["id"]: sub["name"] for sub in subs_json}


def set_subscription(sub_id: str):
    """Set the active Azure subscription."""
    log.debug(f"Setting active subscription to {sub_id}")
    execute(AzCmd("account", "set").param("--subscription", sub_id))
