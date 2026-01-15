# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing from environment variables."""

import os
from dataclasses import dataclass
from typing import Optional

from .errors import ConfigurationError


# Maximum number of regions that can be specified
MAX_SCANNER_REGIONS = 4


@dataclass
class Config:
    """Configuration for the agentless scanner setup."""

    # Datadog configuration
    api_key: str
    app_key: str
    site: str

    # GCP configuration
    scanner_project: str
    regions: list[str]
    projects_to_scan: list[str]

    # Optional: custom GCS bucket for Terraform state
    state_bucket: Optional[str] = None

    @property
    def all_projects(self) -> list[str]:
        """All projects including scanner project (deduplicated)."""
        projects = set(self.projects_to_scan)
        projects.add(self.scanner_project)
        return sorted(projects)

    @property
    def other_projects(self) -> list[str]:
        """Projects to scan excluding the scanner project."""
        return [p for p in self.projects_to_scan if p != self.scanner_project]


def parse_config() -> Config:
    """Parse configuration from environment variables.

    Raises:
        ConfigurationError: If required environment variables are missing.
    """
    errors = []

    # Required: Datadog configuration
    api_key = os.environ.get("DD_API_KEY", "").strip()
    if not api_key:
        errors.append("DD_API_KEY is required")

    app_key = os.environ.get("DD_APP_KEY", "").strip()
    if not app_key:
        errors.append("DD_APP_KEY is required")

    site = os.environ.get("DD_SITE", "").strip()
    if not site:
        errors.append("DD_SITE is required (e.g., datadoghq.com, datadoghq.eu, us5.datadoghq.com). See https://docs.datadoghq.com/getting_started/site/")

    # Required: GCP configuration
    scanner_project = os.environ.get("SCANNER_PROJECT", "").strip()
    if not scanner_project:
        errors.append("SCANNER_PROJECT is required")

    regions_str = os.environ.get("SCANNER_REGIONS", "").strip()
    if not regions_str:
        errors.append("SCANNER_REGIONS is required (e.g., us-central1 or us-central1,europe-west1)")

    projects_to_scan_str = os.environ.get("PROJECTS_TO_SCAN", "").strip()
    if not projects_to_scan_str:
        errors.append("PROJECTS_TO_SCAN is required (comma-separated list)")

    if errors:
        usage = """
Usage:
  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\
  SCANNER_PROJECT=my-project SCANNER_REGIONS=us-central1 \\
  PROJECTS_TO_SCAN=proj1,proj2,proj3 \\
  python gcp_agentless_setup.pyz deploy"""

        raise ConfigurationError(
            "Missing required configuration",
            "\n".join(f"  - {e}" for e in errors) + "\n" + usage,
        )

    # Parse and deduplicate regions list
    regions = list(dict.fromkeys(
        r.strip() for r in regions_str.split(",") if r.strip()
    ))

    if not regions:
        raise ConfigurationError(
            "Invalid configuration",
            "SCANNER_REGIONS must contain at least one region",
        )

    if len(regions) > MAX_SCANNER_REGIONS:
        raise ConfigurationError(
            "Invalid configuration",
            f"SCANNER_REGIONS cannot exceed {MAX_SCANNER_REGIONS} regions (got {len(regions)})",
        )

    # Parse and deduplicate projects list
    projects_to_scan = list(dict.fromkeys(
        p.strip() for p in projects_to_scan_str.split(",") if p.strip()
    ))

    if not projects_to_scan:
        raise ConfigurationError(
            "Invalid configuration",
            "PROJECTS_TO_SCAN must contain at least one project",
        )

    # Optional: custom GCS bucket for Terraform state
    state_bucket = os.environ.get("TF_STATE_BUCKET", "").strip() or None

    return Config(
        api_key=api_key,
        app_key=app_key,
        site=site,
        scanner_project=scanner_project,
        regions=regions,
        projects_to_scan=projects_to_scan,
        state_bucket=state_bucket,
    )
