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
    """Configuration for one scan run.

    Also reused, constructed directly rather than via parse_scan_config, by
    `apply --interactive` (see apply_command.py) to drive interactive.py's
    discovery-based walkthrough -- dry_run there means "skip the apply
    confirmation prompt entirely and never make changes."
    """

    region: str
    dd_site: str
    dry_run: bool = False


def parse_scan_config(argv: Optional[Sequence[str]] = None) -> ScanConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If the region is missing.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa scan",
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
    args = parser.parse_args(argv)

    if not args.region:
        raise ConfigError("  - Region is required: pass --region or set AWS_REGION")

    return ScanConfig(region=args.region, dd_site=args.dd_site)
