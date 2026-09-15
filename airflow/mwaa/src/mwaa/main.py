# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Entry point: `python mwaa.pyz --name <env> --region <region>`."""

import sys

from airflow_shared.reporter import FindingStatus, Reporter

from .config import ConfigError, parse_config
from .probe import WORKFLOW_TYPE, run_probe


def main() -> None:
    try:
        config = parse_config()
    except ConfigError as e:
        print(f"Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)

    print(f"Probing MWAA environment '{config.environment_name}' in {config.region}...")
    reporter = Reporter(workflow_type=WORKFLOW_TYPE)

    try:
        findings = run_probe(config, reporter)
    except Exception as e:
        print(f"\nProbe failed: {e}", file=sys.stderr)
        sys.exit(1)

    if any(f.status == FindingStatus.FAIL for f in findings):
        sys.exit(1)


if __name__ == "__main__":
    main()
