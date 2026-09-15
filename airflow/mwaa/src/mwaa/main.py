# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Entry point.

  python mwaa.pyz scan --session-id <uuid> --region <region>              # survey every MWAA environment, persist
                                                                            # the session, point back to the UI
  python mwaa.pyz scan --session-id <uuid> --region <region> --interactive # same, but walk the whole flow (select,
                                                                            # review, apply) at the terminal instead
  python mwaa.pyz scan ... --interactive --dry-run                        # same, but never applies -- skips the
                                                                            # confirmation prompt too
  python mwaa.pyz probe --name <env> --region <region>                    # read-only diagnostics against one environment
  python mwaa.pyz apply --session-id <uuid> --name <env> --region <region>        # just prints the plan's file changes
  python mwaa.pyz apply --session-id <uuid> --name <env> --region <region> --yes  # actually applies them

  SESSION_OVERRIDE_PATH=<path> python mwaa.pyz apply --session-id <uuid> --name <env> --region <region>
      # local/dev only: apply a hand-authored Session from disk instead of one `scan` persisted --
      # --session-id is still required for a consistent signature, its value is just unused here --
      # see session_override.py

`scan` is the default if no subcommand is given.
"""

import sys

from airflow_shared.reporter import FindingStatus, Reporter

from .apply_command import run_apply
from .apply_config import parse_apply_config
from .config import ConfigError, parse_config
from .probe import WORKFLOW_TYPE, run_probe
from .scan import run_scan
from .scan_config import parse_scan_config

COMMANDS = ("scan", "probe", "apply")


def _run_scan(argv: list[str]) -> None:
    try:
        config = parse_scan_config(argv)
    except ConfigError as e:
        print(f"Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning MWAA environments in {config.region}... (session {config.session_id})")
    reporter = Reporter(workflow_type=WORKFLOW_TYPE)

    try:
        run_scan(config, reporter)
    except Exception as e:
        print(f"\nScan failed: {e}", file=sys.stderr)
        sys.exit(1)


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


def _run_apply(argv: list[str]) -> None:
    try:
        config = parse_apply_config(argv)
    except ConfigError as e:
        print(f"Invalid configuration:\n{e}", file=sys.stderr)
        sys.exit(1)

    print(f"Applying the onboarding plan for '{config.environment_name}' in {config.region} (session {config.session_id})...")
    reporter = Reporter(workflow_type=WORKFLOW_TYPE)

    try:
        run_apply(config, reporter)
    except Exception as e:
        print(f"\nApply failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    argv = sys.argv[1:]
    command = "scan"
    if argv and argv[0] in COMMANDS:
        command, argv = argv[0], argv[1:]

    if command == "probe":
        _run_probe(argv)
    elif command == "apply":
        _run_apply(argv)
    else:
        _run_scan(argv)


if __name__ == "__main__":
    main()
