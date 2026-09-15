# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Entry point.

  python mwaa.pyz scan --region <region>              # discover every MWAA environment, print the
                                                        # scan payload (dry run -- nothing is sent yet)
  python mwaa.pyz probe --name <env> --region <region> # read-only diagnostics against one environment

`scan` is the default if no subcommand is given.
"""

import json
import sys

from airflow_shared.reporter import FindingStatus, Reporter

from .config import ConfigError, parse_config
from .probe import WORKFLOW_TYPE, run_probe
from .scan import run_scan
from .scan_config import parse_scan_config

COMMANDS = ("scan", "probe")


def _run_scan(argv: list[str]) -> None:
    try:
        config = parse_scan_config(argv)
    except ConfigError as e:
        print(f"Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning MWAA environments in {config.region}...")
    reporter = Reporter(workflow_type=WORKFLOW_TYPE)

    try:
        payload = run_scan(config, reporter)
    except Exception as e:
        print(f"\nScan failed: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print("--- dry run: no phone-home endpoint exists yet, printing the payload instead ---")
    print(json.dumps(payload, indent=2))


def _run_probe(argv: list[str]) -> None:
    try:
        config = parse_config(argv)
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


def main() -> None:
    argv = sys.argv[1:]
    command = "scan"
    if argv and argv[0] in COMMANDS:
        command, argv = argv[0], argv[1:]

    if command == "probe":
        _run_probe(argv)
    else:
        _run_scan(argv)


if __name__ == "__main__":
    main()
