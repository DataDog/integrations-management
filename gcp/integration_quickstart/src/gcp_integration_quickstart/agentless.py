# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import sys

from gcp_agentless_setup.config import MISSING_CONFIGURATION_MESSAGE, Config, parse_config
from gcp_agentless_setup.errors import SetupError
from gcp_agentless_setup.main import (
    TOTAL_STEPS,
    deploy,
    print_setup_error,
    validate_credentials_and_workflow,
)
from gcp_agentless_setup.reporter import Reporter

AGENTLESS_WORKFLOW_ID_VAR: str = "AGENTLESS_WORKFLOW_ID"

AGENTLESS_ENVIRONMENT_VARS: tuple[str, ...] = (
    AGENTLESS_WORKFLOW_ID_VAR,
    "SCANNER_PROJECT",
    "SCANNER_REGIONS",
    "PROJECTS_TO_SCAN",
)


def is_agentless_requested() -> bool:
    return any(os.environ.get(var, "").strip() for var in AGENTLESS_ENVIRONMENT_VARS)


def prepare_agentless_setup() -> tuple[Config, Reporter]:
    """Validate agentless inputs and credentials before the integration is set up, exiting on failure."""
    try:
        config = parse_config(workflow_id_var=AGENTLESS_WORKFLOW_ID_VAR, include_usage=False)
    except SetupError as e:
        print_setup_error(e)
        if e.message == MISSING_CONFIGURATION_MESSAGE:
            print(
                "Agentless Scanning setup requires all of: "
                f"{', '.join(AGENTLESS_ENVIRONMENT_VARS)}. "
                "Unset them all to only set up the GCP integration."
            )
        sys.exit(1)
    reporter = Reporter(TOTAL_STEPS, workflow_id=config.workflow_id)
    validate_credentials_and_workflow(config, reporter)
    return config, reporter


def run_agentless_setup(config: Config, reporter: Reporter) -> None:
    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - GCP Cloud Shell Setup")
    print("=" * 60)
    try:
        deploy(config, reporter)
    except Exception as e:
        if isinstance(e, SetupError):
            print_setup_error(e)
        else:
            print(f"\n❌ Unexpected error: {e}\n")
        print("The GCP integration was set up successfully, but the Agentless Scanning setup failed.")
        print("Start the Agentless Scanning setup again from the Datadog UI to retry.")
        sys.exit(1)
