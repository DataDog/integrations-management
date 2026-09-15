# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Orchestrates a full scan run: discover every MWAA environment in a region and plan each one."""

import uuid
from typing import Any

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .discovery import discover_environments
from .payload import build_payload
from .scan_config import ScanConfig

WORKFLOW_TYPE = "mwaa-setup"


def run_scan(config: ScanConfig, reporter: Reporter) -> dict[str, Any]:
    """Discover every environment in the configured region and compute its onboarding plan."""
    client = MwaaClient(region=config.region)
    session_id = str(uuid.uuid4())
    print(f"Session ID: {session_id}")

    with reporter.report_step("discover_environments"):
        contexts = discover_environments(client)
    print(f"Found {len(contexts)} MWAA environment(s) in {config.region}.")

    with reporter.report_step("compute_plans"):
        payload = build_payload(session_id, config.region, config.dd_site, contexts)

    return payload
