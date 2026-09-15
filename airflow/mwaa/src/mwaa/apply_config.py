# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing for the `apply` command."""

import argparse
import os
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import ConfigError
from .plan_override import PLAN_OVERRIDE_ENV_VAR


@dataclass(frozen=True)
class ApplyConfig:
    """Configuration for one apply run.

    environment_name is only Optional because it isn't needed at all in two
    cases: PLAN_OVERRIDE_PATH carries its own (see plan_override.py), and
    --interactive discovers every environment in the region instead of
    targeting one. region is only Optional for the PLAN_OVERRIDE_PATH case.
    run_apply always has a concrete environment_name/region by the time it
    needs one.
    """

    environment_name: Optional[str] = None
    region: Optional[str] = None
    dd_site: str = "datadoghq.com"
    confirmed: bool = False
    interactive: bool = False
    dry_run: bool = False


def parse_apply_config(argv: Optional[Sequence[str]] = None) -> ApplyConfig:
    """Parse configuration from CLI args, falling back to environment variables.

    Raises:
        ConfigError: If the region is missing, or the environment name is
            missing and neither --interactive nor PLAN_OVERRIDE_PATH supplies
            one another way.
    """
    parser = argparse.ArgumentParser(
        prog="mwaa apply",
        description="Apply the OpenLineage onboarding plan to one MWAA environment.",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("MWAA_ENVIRONMENT_NAME"),
        help="MWAA environment name (default: $MWAA_ENVIRONMENT_NAME). Not needed with --interactive.",
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
    parser.add_argument(
        "--interactive",
        action="store_true",
        help=(
            "Discover every environment in the region and walk through selecting one, "
            "reviewing its plan, and confirming apply at the terminal, instead of targeting "
            "one environment with --name. Omitting this just prints the plan for --name."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --interactive: skip the apply confirmation prompt entirely and never make changes. Ignored otherwise.",
    )
    args = parser.parse_args(argv)

    # PLAN_OVERRIDE_PATH carries its own environment_name/region (see
    # plan_override.py), so --name/--region become optional once it's set.
    if not os.environ.get(PLAN_OVERRIDE_ENV_VAR):
        errors = []
        if not args.name and not args.interactive:
            errors.append("Environment name is required: pass --name, use --interactive, or set MWAA_ENVIRONMENT_NAME")
        if not args.region:
            errors.append("Region is required: pass --region or set AWS_REGION")

        if errors:
            raise ConfigError("\n".join(f"  - {e}" for e in errors))

    return ApplyConfig(
        environment_name=args.name,
        region=args.region,
        dd_site=args.dd_site,
        confirmed=args.yes,
        interactive=args.interactive,
        dry_run=args.dry_run,
    )
