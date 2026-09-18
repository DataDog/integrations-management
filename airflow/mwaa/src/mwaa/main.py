# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Entry point.

  python mwaa.pyz scan --session-id <uuid> --region <region> --dd-site <site> --dd-api-key <key>
      # survey every MWAA environment, submit the session to Datadog, point back to the UI
  python mwaa.pyz scan ... --interactive   # same, but walk the whole flow (select, review, apply)
                                            # at the terminal instead
  python mwaa.pyz scan ... --interactive --dry-run   # same, but never applies -- skips the
                                                      # confirmation prompt too
  python mwaa.pyz apply --session-id <uuid> --name <env> --region <region> --dd-site <site> --dd-api-key <key>
      # just prints the plan's file changes
  python mwaa.pyz apply ... --yes   # actually applies them

  Both commands need --dd-site: the session gets submitted to and read back
  from https://data-obs-intake.<site>, and there's no safe default to guess
  which Datadog organization that should be. Not required with --offline,
  which persists to a local file instead -- see session_store_selection.py.
  Also the automatic fallback if the intake API isn't reachable at all.

  A scanned session's startup.sh only ever carries a placeholder for the API key
  (see startup_script.py) -- apply's --dd-api-key is what gets substituted in,
  right before a file is previewed or written. Never persisted upstream of that,
  nor sent to the intake API -- DD-API-KEY there is just how it authenticates.

  SESSION_OVERRIDE_PATH=<path> python mwaa.pyz apply --session-id <uuid> --name <env> --region <region> --dd-site <site> --dd-api-key <key>
      # local/dev only: apply a hand-authored Session from disk instead of one `scan` persisted --
      # --session-id is still required for a consistent signature, its value is just unused here --
      # see session_override.py

`scan` is the default if no subcommand is given.

There used to be a third command, `probe` -- read-only diagnostics against one
already-named environment, with no session involved. Retired: every check it
ran now feeds `scan`'s per-environment `issues` (see session.py), which is the
one place onboarding problems should surface.
"""

import sys

from airflow_shared.reporter import Reporter

from .apply_command import run_apply
from .apply_config import parse_apply_config
from .config import ConfigError
from .scan import run_scan
from .scan_config import parse_scan_config

WORKFLOW_TYPE = "mwaa-setup"
COMMANDS = ("scan", "apply")


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

    if command == "apply":
        _run_apply(argv)
    else:
        _run_scan(argv)


if __name__ == "__main__":
    main()
