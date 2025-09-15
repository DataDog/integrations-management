from dataclasses import dataclass
from json import JSONDecodeError, loads
from logging import getLogger
from typing import Final

from .az_cmd import AzCmd, execute
from .configuration import Configuration

log = getLogger("installer")

CONTROL_PLANE_RESOURCES_TASK_PREFIX: Final = "resources-task"


@dataclass(frozen=True)
class LfoMetadata:
    monitored_subs: list[str]
    control_plane_sub_id: str
    control_plane_rg: str


def check_existing_lfo(config: Configuration) -> dict[str, LfoMetadata]:
    """Check if LFO is already installed"""
    log.info(
        "Checking if log forwarding is already installed in this Azure environment..."
    )

    existing_lfos: dict[str, LfoMetadata] = {}  # map control plane ID to metadata

    for sub_id in config.all_subscriptions:
        func_apps_json = execute(
            AzCmd("functionapp", "list")
            .param("--subscription", sub_id)
            .param(
                "--query",
                f"\"[?starts_with(name,'{CONTROL_PLANE_RESOURCES_TASK_PREFIX}')].{{resourceGroup:resourceGroup, name:name}}\"",
            )
            .param("--output", "json")
        )

        try:
            resources_task_json = loads(func_apps_json)
        except JSONDecodeError as e:
            log.error(f"Invalid JSON: {func_apps_json}")
            log.error(f"Error: {e}")
            raise

        if not resources_task_json:
            continue

        for resources_task in resources_task_json:
            name = resources_task["name"]
            rg = resources_task["resourceGroup"]
            control_plane_id = name.split("-")[-1]

            monitored_subs = execute(
                AzCmd("functionapp", "config appsettings list")
                .param("--subscription", sub_id)
                .param("--name", name)
                .param("--resource-group", rg)
                .param("--query", "\"[?name=='MONITORED_SUBSCRIPTIONS'].value\"")
                .param("--output", "tsv")
            )

            if not monitored_subs:
                continue

            try:
                monitored_subs = loads(monitored_subs)
            except JSONDecodeError as e:
                log.error(f"Invalid JSON: {monitored_subs}")
                log.error(f"Error: {e}")
                raise

            existing_lfos[control_plane_id] = LfoMetadata(monitored_subs, sub_id, rg)

    return existing_lfos
