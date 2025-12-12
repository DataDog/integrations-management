# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from collections.abc import Iterable
from itertools import groupby
from os import environ
from typing import Optional, TypedDict, cast

from az_shared.execute_cmd import execute, execute_json
from azure_integration_quickstart.extension.common import set_dynamic_install_without_prompt
from common.shell import Cmd


class Vm(TypedDict):
    id: str
    location: str
    os_type: str
    subscription_id: str


def list_vms_for_subscription(subscription: str) -> list[Vm]:
    return [
        cast(Vm, {**vm, "subscription_id": subscription})
        for vm in execute_json(
            Cmd(["az", "vm", "list"])
            .param("--subscription", subscription)
            .param("--query", "[].{id:id,location:location,os_type:storageProfile.osDisk.osType}")
        )
    ]


def list_vms_for_subscriptions(subscriptions: Iterable[str]) -> list[Vm]:
    return [vm for s in subscriptions for vm in list_vms_for_subscription(s)]


def list_extension_image_versions(extension_name: str, location: str) -> list[str]:
    """List the available extension image versions published by Datadog in the given location."""
    return execute_json(
        Cmd(["az", "vm", "extension", "image", "list-versions"])
        .param("-p", "Datadog.Agent")
        .param("-n", extension_name)
        .param("-l", location)
        .param("--query", "[].name")
    )


def set_extension(extension_name: str, vm_ids: list[str], version: str) -> None:
    execute(
        Cmd(["az", "vm", "extension", "set"])
        .param_list("--ids", vm_ids)
        .param("--publisher", "Datadog.Agent")
        .param("-n", extension_name)
        .param("--version", version)
        .param("--settings", json.dumps({"site": environ["DD_SITE"], "agentVersion": "latest"}))
        .param("--protected-settings", json.dumps({"api_key": environ["DD_API_KEY"]}))
        .param("--no-auto-upgrade-minor-version", "true")
        .flag("--no-wait")
    )


def get_extension_name_for_os_type(os_type: str) -> Optional[str]:
    return (
        "DatadogLinuxAgent"
        if os_type.lower() == "linux"
        else "DatadogWindowsAgent"
        if os_type.lower() == "windows"
        else None
    )


def set_extension_latest(vms: Iterable[Vm]) -> None:
    set_dynamic_install_without_prompt()

    def get_os_type(vm: Vm) -> str:
        return vm["os_type"]

    def get_location(vm: Vm) -> str:
        return vm["location"]

    for os_type, vms_with_os_type in groupby(sorted(vms, key=get_os_type), key=get_os_type):
        if extension_name := get_extension_name_for_os_type(os_type):
            for location, vms_in_location in groupby(sorted(vms_with_os_type, key=get_location), key=get_location):
                if extension_versions := list_extension_image_versions(extension_name, location):
                    set_extension(extension_name, [vm["id"] for vm in vms_in_location], sorted(extension_versions)[-1])
