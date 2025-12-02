import json
from itertools import groupby
from operator import itemgetter
from os import environ
from typing import TypedDict, cast

from az_shared.az_cmd import execute, execute_json
from azure_integration_quickstart.extension.common import set_dynamic_install_without_prompt
from common.shell import Cmd


class Vm(TypedDict):
    id: str
    location: str
    subscription_id: str


def list_vms_for_subscription(subscription: str) -> list[Vm]:
    return [
        cast(Vm, {**vm, "subscription_id": subscription})
        for vm in execute_json(
            Cmd(["az", "vm", "list"])
            .param("--subscription", subscription)
            .param("--query", "[].{id:id, location:location}")
        )
    ]
"""az vm list --subscription '0b62a232-b8db-4380-9da6-640f7272ed6d' --query '[].id' -o tsv"""

def list_vms_for_subscriptions(subscriptions: list[str]) -> list[Vm]:
    return [vm for s in subscriptions for vm in list_vms_for_subscription(s)]


def list_extension_versions(location: str) -> list[str]:
    return execute_json(
        Cmd(["az", "vm", "extension", "image", "list-versions"])
        .param("-l", location)
        .param("-p", "Datadog.Agent")
        .param("-n", "DatadogWindowsAgent")
        .param("--query", "[].name")
    )


def set_extension(vm_ids: list[str], version: str) -> None:
    execute(
        Cmd(["az", "vm", "extension", "set"])
        .param_list("--ids", vm_ids)
        .param("--version", version)
        .param("--settings", json.dumps({"site": environ["DD_SITE"], "agentVersion": "latest"}))
        .param("--protected-settings", json.dumps({"api_key": environ["DD_API_KEY"]}))
        .param("--publisher", "Datadog.Agent")
        .param("-n", "DatadogWindowsAgent")
        .param("--no-auto-upgrade-minor-version", "true")
    )


def set_extension_latest(vms: list[Vm]) -> None:
    set_dynamic_install_without_prompt()
    get_location = itemgetter("location")
    for location, vms_in_location in groupby(sorted(vms, key=get_location), key=get_location):
        if extension_versions := list_extension_versions(location):
            set_extension([vm["id"] for vm in vms_in_location], sorted(extension_versions)[-1])
