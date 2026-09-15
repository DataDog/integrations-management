# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the mwaa probe tool."""

import argparse
import os
from dataclasses import dataclass
from typing import Optional, Sequence


class ConfigError(Exception):
    """Missing or invalid configuration."""


@dataclass(frozen=True)
class Config:
    """Configuration for one probe run."""

    environment_name: str
    region: str


def parse_config(argv: Optional[Sequence[str]] = None) -> Config:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If the environment name or region is missing.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa",
        description="Read-only diagnostics for an Amazon MWAA environment's onboarding setup.",
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
    args = parser.parse_args(argv)

    errors = []
    if not args.name:
        errors.append("Environment name is required: pass --name or set MWAA_ENVIRONMENT_NAME")
    if not args.region:
        errors.append("Region is required: pass --region or set AWS_REGION")

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return Config(environment_name=args.name, region=args.region)
