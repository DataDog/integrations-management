# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the `scan` command."""

import argparse
import os
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import ConfigError


@dataclass(frozen=True)
class ScanConfig:
    """Configuration for one scan (or interactive) run."""

    region: str
    dd_site: str
    dry_run: bool = False


def parse_scan_config(argv: Optional[Sequence[str]] = None, prog: str = "mwaa scan") -> ScanConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Shared by `scan` and `interactive` -- pass `prog` so --help reflects
    whichever one actually invoked this.

    Raises:
        ConfigError: If the region is missing.
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Discover every MWAA environment in a region and compute an OpenLineage onboarding plan for each.",
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
        "--dry-run",
        action="store_true",
        help=(
            "For `interactive`: skip the apply confirmation prompt entirely and never make changes, "
            "no matter what you'd answer. Ignored by `scan`, which never applies changes anyway."
        ),
    )
    args = parser.parse_args(argv)

    if not args.region:
        raise ConfigError("  - Region is required: pass --region or set AWS_REGION")

    return ScanConfig(region=args.region, dd_site=args.dd_site, dry_run=args.dry_run)
