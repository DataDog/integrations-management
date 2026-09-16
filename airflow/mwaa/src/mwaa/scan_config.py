# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the `scan` command."""

import argparse
import os
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import ConfigError


@dataclass(frozen=True)
class ScanConfig:
    """Configuration for one scan run."""

    session_id: str
    region: str
    dd_site: str
    dd_api_key: str
    interactive: bool = False
    dry_run: bool = False


def parse_scan_config(argv: Optional[Sequence[str]] = None) -> ScanConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If --session-id is missing or not a valid UUID, the region
            is missing, or --dd-api-key is missing.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa scan",
        description="Discover every MWAA environment in a region and compute an OpenLineage onboarding plan for each.",
    )
    parser.add_argument(
        "--session-id",
        help="UUID identifying this scan session -- the UI polls for updates keyed by this. Required.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        help="AWS region to scan (default: $AWS_REGION or $AWS_DEFAULT_REGION)",
    )
    parser.add_argument(
        "--dd-site",
        default=os.environ.get("DD_SITE", "datadoghq.com"),
        help="Datadog site, used to render the OpenLineage transport URL (default: $DD_SITE or datadoghq.com)",
    )
    parser.add_argument(
        "--dd-api-key",
        default=os.environ.get("DD_API_KEY"),
        help=(
            "Datadog API key, interpolated directly into the proposed startup.sh (default: $DD_API_KEY). "
            "Required -- the startup script needs the real value to work."
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help=(
            "Walk through selecting an environment, reviewing its plan, and confirming apply at the "
            "terminal. Without this, the session is persisted and you're pointed back to the UI."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --interactive: skip the apply confirmation prompt entirely and never make changes. Ignored otherwise.",
    )
    args = parser.parse_args(argv)

    errors = []
    if not args.session_id:
        errors.append("--session-id is required")
    else:
        try:
            uuid.UUID(args.session_id)
        except ValueError:
            errors.append(f"--session-id must be a valid UUID, got '{args.session_id}'")
    if not args.region:
        errors.append("Region is required: pass --region or set AWS_REGION")
    if not args.dd_api_key:
        errors.append("Datadog API key is required: pass --dd-api-key or set DD_API_KEY")

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return ScanConfig(
        session_id=args.session_id,
        region=args.region,
        dd_site=args.dd_site,
        dd_api_key=args.dd_api_key,
        interactive=args.interactive,
        dry_run=args.dry_run,
    )
