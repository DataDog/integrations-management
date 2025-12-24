# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing from environment variables."""

import os
import sys
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for the agentless scanner setup."""

    # Datadog configuration
    api_key: str
    app_key: str
    site: str

    # GCP configuration
    scanner_project: str
    region: str
    projects_to_scan: list[str]

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
    """Parse configuration from environment variables."""
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
    scanner_project = os.environ.get("GCP_SCANNER_PROJECT", "").strip()
    if not scanner_project:
        errors.append("GCP_SCANNER_PROJECT is required")

    region = os.environ.get("GCP_REGION", "").strip()
    if not region:
        errors.append("GCP_REGION is required (e.g., us-central1)")

    projects_to_scan_str = os.environ.get("GCP_PROJECTS_TO_SCAN", "").strip()
    if not projects_to_scan_str:
        errors.append("GCP_PROJECTS_TO_SCAN is required (comma-separated list)")

    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"   - {error}")
        print()
        print("Usage:")
        print("  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\")
        print("  GCP_SCANNER_PROJECT=my-project GCP_REGION=us-central1 \\")
        print("  GCP_PROJECTS_TO_SCAN=proj1,proj2,proj3 \\")
        print("  python gcp_agentless_setup.pyz")
        sys.exit(1)

    # Parse projects list
    projects_to_scan = [p.strip() for p in projects_to_scan_str.split(",") if p.strip()]

    if not projects_to_scan:
        print("❌ GCP_PROJECTS_TO_SCAN must contain at least one project")
        sys.exit(1)

    return Config(
        api_key=api_key,
        app_key=app_key,
        site=site,
        scanner_project=scanner_project,
        region=region,
        projects_to_scan=projects_to_scan,
    )

