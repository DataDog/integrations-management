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
    offline: bool = False


def parse_scan_config(argv: Optional[Sequence[str]] = None) -> ScanConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If --session-id is missing or not a valid UUID, the region
            is missing, --dd-api-key is missing, or --dd-site is missing while
            --offline isn't set.
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
        default=os.environ.get("DD_SITE"),
        help=(
            "Datadog site (default: $DD_SITE) -- also used to render the OpenLineage transport URL. "
            "Required unless --offline: this session gets submitted to https://data-obs-intake.<site>, "
            "and there's no safe default to guess which organization that should be."
        ),
    )
    parser.add_argument(
        "--dd-api-key",
        default=os.environ.get("DD_API_KEY"),
        help=(
            "Datadog API key (default: $DD_API_KEY). Required for --interactive's own apply step "
            "(the substituted key never appears in the persisted session -- see startup_script.py) "
            "and to authenticate the session submission unless --offline."
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
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Persist the session to a local file instead of submitting it to Datadog. Also the "
            "automatic fallback when the intake API isn't reachable -- see session_store_selection.py."
        ),
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

    dd_site = args.dd_site
    if not args.offline and not dd_site:
        errors.append("Datadog site is required unless --offline is set: pass --dd-site or set DD_SITE")
    elif args.offline and not dd_site:
        dd_site = "datadoghq.com"  # only rendered into a local startup.sh preview -- no network implication

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return ScanConfig(
        session_id=args.session_id,
        region=args.region,
        dd_site=dd_site,
        dd_api_key=args.dd_api_key,
        interactive=args.interactive,
        dry_run=args.dry_run,
        offline=args.offline,
    )
