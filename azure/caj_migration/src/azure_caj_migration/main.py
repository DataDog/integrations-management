# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import argparse
import logging
from logging import basicConfig

from az_shared.errors import InputParamValidationError
from az_shared.logs import log, log_header
from azure_logging_install.configuration import ControlPlane
from azure_logging_install.validation import validate_az_cli

from .cleanup import cleanup_old_resources
from .container_jobs import build_container_job_steps, get_task_specs
from .discovery import (
    find_migration_candidates,
    get_monitored_subscription_ids,
    locate_deployer,
)
from .enablement import build_enablement_steps
from .prompts import confirm_yes_no
from .roles import build_role_steps
from .steps import run_steps


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate an Azure Log Forwarding Orchestration control plane from Function Apps to Container App Jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--control-plane-ids",
        type=str,
        default=None,
        help=(
            "Comma-separated list of specific control plane IDs to migrate. "
            "Default: auto-discover every eligible Function-App-based installation in the tenant."
        ),
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Don't prompt for confirmation before migrating each discovered installation",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the log level (default: INFO)",
    )

    return parser.parse_args()


def migrate_one_installation(control_plane: ControlPlane) -> None:
    """Run all migration phases for a single control plane, with automatic rollback on failure."""
    log_header(
        f"Migrating control plane {control_plane.id} "
        f"({control_plane.sub_id} / {control_plane.resource_group})"
    )

    deployer = locate_deployer(control_plane)
    monitored_sub_ids = get_monitored_subscription_ids(control_plane)
    task_specs = get_task_specs(control_plane)

    created_jobs = {}
    steps = [
        *build_container_job_steps(control_plane, deployer.env_name, created_jobs),
        *build_role_steps(control_plane, deployer.job_name, monitored_sub_ids),
        *build_enablement_steps(control_plane, deployer.job_name, task_specs),
    ]

    run_steps(steps)

    log_header(f"Control plane {control_plane.id} migrated - cleaning up old resources")
    manual_cleanup_needed = cleanup_old_resources(control_plane, deployer.job_name)
    if manual_cleanup_needed:
        log.warning("Some cleanup steps could not be completed automatically. Manual action required:")
        for item in manual_cleanup_needed:
            log.warning(f"  - {item}")
    else:
        log.info("Cleanup completed")

    log_header(f"Success! Control plane {control_plane.id} is now running on Container App Jobs")


def run_migration(control_plane_ids: str | None, skip_confirmation: bool) -> None:
    validate_az_cli()

    explicit_ids = None
    if control_plane_ids:
        explicit_ids = {cp_id.strip() for cp_id in control_plane_ids.split(",") if cp_id.strip()}

    candidates = find_migration_candidates(explicit_ids)
    if not candidates:
        log.info("No eligible Function-App-based LFO installations found to migrate")
        return

    skip_confirmation = skip_confirmation or explicit_ids is not None

    for control_plane_id, control_plane in candidates.items():
        if not (skip_confirmation or confirm_yes_no(
            f"Migrate control plane '{control_plane_id}' in subscription "
            f"'{control_plane.sub_id}', resource group "
            f"'{control_plane.resource_group}' to Container App Jobs?"
        )):
            log.info(f"Skipping migration for control plane {control_plane_id}")
            continue

        try:
            migrate_one_installation(control_plane)
        except Exception as e:
            log.error(f"Migration failed for control plane {control_plane_id}: {e}")
            log.error("Changes for this installation were rolled back. Continuing to the next installation, if any.")


def main():
    """Main migration flow that orchestrates all steps."""
    try:
        args = parse_arguments()
        basicConfig(level=getattr(logging, args.log_level))
    except Exception as e:
        log.error(f"Failed to parse arguments: {e}")
        raise InputParamValidationError(f"Failed to initialize: {e}")

    run_migration(args.control_plane_ids, args.yes)


if __name__ == "__main__":
    main()
