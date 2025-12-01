import json
from os import environ

from az_shared.az_cmd import execute, execute_json
from common.shell import Cmd


def list_extension_versions(location: str) -> list[str]:
    return execute_json(
        Cmd(["az", "vm", "extension", "image", "list-versions"])
        .param("-l", location)
        .param("-p", "Datadog.Agent")
        .param("-n", "DatadogWindowsAgent")
        .param("--query", "[].name")
    )


def set_extension(resource_ids: list[str], version: str) -> None:
    execute(
        Cmd(["az", "vm", "extension", "set"])
        .param_list("--ids", resource_ids)
        .param("--version", version)
        .param("--settings", json.dumps({"site": environ["DD_SITE"], "agentVersion": "latest"}))
        .param("--protected-settings", json.dumps({"api_key": environ["DD_API_KEY"]}))
        .param("-p", "Datadog.Agent")
        .param("-n", "DatadogWindowsAgent")
        .param("--no-auto-upgrade-minor-version", "true")
    )
