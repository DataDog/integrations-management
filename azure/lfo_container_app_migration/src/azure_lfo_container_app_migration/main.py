# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import argparse
import logging
from logging import basicConfig

from azure_logging_install.validation import validate_az_cli
from az_shared.errors import InputParamValidationError
from az_shared.logs import log

from .migration import run_migration

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
    run_migration(optional_control_plane_ids, args.yes, args.log_level)


if __name__ == "__main__":
    main()
