# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the `apply` command."""

import argparse
import os
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import ConfigError


@dataclass(frozen=True)
class ApplyConfig:
    """Configuration for one apply run."""

    environment_name: str
    region: str
    dd_site: str
    confirmed: bool


def parse_apply_config(argv: Optional[Sequence[str]] = None) -> ApplyConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If the environment name or region is missing.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa apply",
        description="Apply the OpenLineage onboarding plan to one MWAA environment.",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("MWAA_ENVIRONMENT_NAME"),
        help="MWAA environment name (default: $MWAA_ENVIRONMENT_NAME)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        help="AWS region (default: $AWS_REGION or $AWS_DEFAULT_REGION)",
    )
    parser.add_argument(
        "--dd-site",
        default=os.environ.get("DD_SITE", "datadoghq.com"),
        help="Datadog site, used to render the OpenLineage transport URL (default: $DD_SITE or datadoghq.com)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually upload files and update the environment. Without this, only prints a preview.",
    )
    args = parser.parse_args(argv)

    errors = []
    if not args.name:
        errors.append("Environment name is required: pass --name or set MWAA_ENVIRONMENT_NAME")
    if not args.region:
        errors.append("Region is required: pass --region or set AWS_REGION")

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return ApplyConfig(environment_name=args.name, region=args.region, dd_site=args.dd_site, confirmed=args.yes)
