# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import argparse
import logging
from logging import basicConfig

from az_shared.errors import InputParamValidationError
from .migration import run_migration

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


def main():
    """Main migration flow that orchestrates all steps."""
    try:
        args = parse_arguments()
        basicConfig(level=getattr(logging, args.log_level))
        optional_control_plane_ids = {cp_id.strip() for cp_id in args.control_plane_ids.split(",") if cp_id.strip()}
    except Exception as e:
        log.error(f"Failed to parse arguments: {e}")
        raise InputParamValidationError(f"Failed to initialize: {e}")

    run_migration(optional_control_plane_ids, args.yes)


if __name__ == "__main__":
    main()
