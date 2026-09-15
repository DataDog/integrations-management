# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the `apply` command."""

import argparse
import os
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import ConfigError


@dataclass(frozen=True)
class ApplyConfig:
    """Configuration for one apply run.

    session_id says which Session (see session.py) to pull a plan out of --
    that survey covers every environment `scan` found, not a decision, so
    name/region are still required to say which one to actually act on.
    """

    session_id: str
    environment_name: str
    region: str
    confirmed: bool = False


def parse_apply_config(argv: Optional[Sequence[str]] = None) -> ApplyConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If --session-id (or a valid UUID for it), the environment
            name, or the region is missing.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa apply",
        description="Apply one environment's OpenLineage onboarding plan from a scan session.",
    )
    parser.add_argument(
        "--session-id",
        help=(
            "UUID of the session a prior `scan --session-id` persisted. Required even when "
            "SESSION_OVERRIDE_PATH is set, for a consistent command signature -- its value is "
            "just unused in that case."
        ),
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("MWAA_ENVIRONMENT_NAME"),
        help="MWAA environment name to apply the plan to (default: $MWAA_ENVIRONMENT_NAME)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        help="AWS region (default: $AWS_REGION or $AWS_DEFAULT_REGION)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually upload files and update the environment. Without this, only prints a preview.",
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
    if not args.name:
        errors.append("Environment name is required: pass --name or set MWAA_ENVIRONMENT_NAME")
    if not args.region:
        errors.append("Region is required: pass --region or set AWS_REGION")

    if errors:
        raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return ApplyConfig(session_id=args.session_id, environment_name=args.name, region=args.region, confirmed=args.yes)
