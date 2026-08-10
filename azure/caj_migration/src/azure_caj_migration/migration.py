# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.
from az_shared.logs import log, log_header
from azure_logging_install.configuration import ControlPlane, ControlPlaneType, Configuration
from azure_logging_install.validation import validate_az_cli
from azure_logging_install.existing_lfo import find_existing_lfo_control_planes, get_current_config_for_control_plane
from az_shared.logs import log, log_header

from .prompts import confirm_yes
from .steps import run_steps, Step



def run_migration(optional_control_plane_ids: set[str], skip_confirmation: bool) -> None:
    # TODO move to main.py?
    # TODO any other validation to add?
    validate_az_cli()
    
    control_planes: list[ControlPlane] = find_existing_lfo_control_planes(subscriptions=None, control_plane_type=ControlPlaneType.FunctionApps)
    if len(optional_control_plane_ids) > 0:
        control_planes = filter(lambda c: c.id in optional_control_plane_ids, control_planes)

    if len(control_planes) == 0:
        log.info("No eligible Function-App-based LFO installations found to migrate")
        return

    for control_plane in control_planes:
        if not (skip_confirmation or confirm_yes(
            f"Migrate control plane '{control_plane.id}' in subscription "
            f"'{control_plane.sub_id}', resource group "
            f"'{control_plane.resource_group}' to Container App Jobs?"
        )):
            log.info(f"Skipping migration for control plane {control_plane.id}")
            continue

        try:
            migrate_control_plane(control_plane)
        except Exception as e:
            log.error(f"Migration failed for control plane {control_plane.id}: {e}")
            log.error("Changes for this installation were rolled back.")
            break
        else: 
            log_header(f"Success! Control plane {control_plane.id} migrated.")


def migrate_control_plane(control_plane: ControlPlane) -> None:
    """Run all migration phases for a single control plane, with automatic rollback on failure."""
    log_header(
        f"Migrating control plane {control_plane.id} "
        f"({control_plane.sub_id} / {control_plane.resource_group})"
    )

    # TODO validation for control plane?

    configuration = get_current_config_for_control_plane(control_plane)
    run_steps(_build_migration_steps(configuration))


def _build_migration_steps(config: Configuration) -> list[Step]:
    return []