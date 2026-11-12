# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import argparse
import logging
from logging import basicConfig

from azure_logging_install.validation import validate_az_cli
from az_shared.errors import InputParamValidationError
from az_shared.logs import log

from .migration import run_migration

def _parse_bool(value: str) -> bool:
    """Parses --dry-run's value. Rejects anything unrecognized, so a typo can't turn the dry run off."""
    normalized = value.strip().lower()
    if normalized in ("true", "yes", "1"):
        return True
    if normalized in ("false", "no", "0"):
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got '{value}'")


def parse_arguments():
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
        help="With --dry-run=false, don't prompt for confirmation before migrating each discovered installation",
    )

    parser.add_argument(
        "--dry-run",
        nargs="?",
        const=True,
        default=True,
        type=_parse_bool,
        metavar="true|false",
        help=(
            "Dry run (the default): show the settings that would be copied and every step the migration would "
            "run, without changing any Azure resources. Does not check that you have the permissions the "
            "migration needs. The Azure CLI 'resource-graph' extension is still installed if missing. "
            "Pass --dry-run=false (or --no-dry-run) to perform the migration."
        ),
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Perform the migration. Same as --dry-run=false",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the log level (default: INFO)",
    )

    return parser.parse_args()


def main():
    try:
        args = parse_arguments()
        basicConfig(level=getattr(logging, args.log_level))
    except Exception as e:
        log.error(f"Failed to parse arguments: {e}")
        raise InputParamValidationError(f"Failed to initialize: {e}")

    if args.control_plane_ids is None:
        optional_control_plane_ids = set()
    else:
        try:
            optional_control_plane_ids = {cp_id.strip() for cp_id in args.control_plane_ids.split(",") if cp_id.strip()}
        except Exception:
            log.error("Failed to parse --control-plane-ids. Value must be a comma separated list of strings.")
            raise InputParamValidationError("Failed parse --control-plane-ids")

    validate_az_cli()
    # TODO add other user validation?
    if args.dry_run:
        log.info("Dry run (the default), no Azure resources will be changed. Pass --dry-run=false to migrate.")
    run_migration(optional_control_plane_ids, args.yes, args.dry_run)


if __name__ == "__main__":
    main()
