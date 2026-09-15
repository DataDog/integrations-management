# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Orchestrates a full scan run: survey every MWAA environment in a region, persist the
session, and either hand off to the UI or walk through it right here at the terminal.

Without --interactive: `scan` only ever surveys and persists -- picking an
environment is the UI's job, not this command's, so it just points back
there with a link carrying the session id.

With --interactive: approximates the Configure Airflow UI's flow entirely
from the CLI. Mirrors the screenshots this was built from: select an
environment from the surveyed list, review its plan, confirm, apply. Useful
for testing the whole thing end to end before there's a real UI or backend to
drive it -- everything here is the same code the eventual UI-driven flow
would call, just wired together with terminal prompts instead of an HTTP
round trip.

Step 5 of the UI flow ("Run a DAG") is deliberately just guidance printed at
the end, not an automated DAG trigger -- there's no canonical DAG to run
against an arbitrary customer environment, and triggering one via the MWAA
REST API is a separate scope decision.

`config.dry_run` (the --dry-run flag) skips the "Run apply now?" prompt
entirely rather than relying on the user answering it correctly -- so nothing
ever gets applied, no matter what. Only meaningful with --interactive.
"""

from typing import Any, Callable

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .apply import apply_to_environment, compute_apply_actions
from .checks import ProbeContext
from .diff_preview import render_unified_diff
from .discovery import discover_environments
from .plan import Plan
from .scan_config import ScanConfig
from .session import Session, build_session
from .session_store import save_session

WORKFLOW_TYPE = "mwaa-setup"

InputFunc = Callable[[str], str]


def _status_label(plan: Plan) -> str:
    if not plan.file_changes:
        return "already configured"
    if plan.upgrade_needed:
        return "OpenLineage upgrade needed"
    return "transport setup needed"


def _prompt_choice(count: int, input_func: InputFunc) -> "int | None":
    """Prompt for a 1-based selection; returns None if the user quits."""
    while True:
        raw = input_func(f"Select an environment [1-{count}] (q to quit): ").strip()
        if raw.lower() in ("q", "quit"):
            return None
        try:
            choice = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= choice <= count:
            return choice
        print(f"Please enter a number between 1 and {count}.")


def _prompt_yes_no(prompt: str, input_func: InputFunc) -> bool:
    while True:
        raw = input_func(f"{prompt} [y/N]: ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("", "n", "no"):
            return False
        print("Please answer y or n.")


def _print_ui_handoff(session: Session) -> None:
    print(f"\nSession persisted: {session.session_id}")
    print("Continue in the Configure Airflow UI:")
    print(f"  https://app.datadoghq.com/data-observability/configure-airflow?session_id={session.session_id}")


def _run_interactive(
    client: MwaaClient,
    config: ScanConfig,
    session: Session,
    contexts: list[ProbeContext],
    reporter: Reporter,
    input_func: InputFunc,
) -> dict[str, Any]:
    print()
    print("=" * 60)
    print("  Configure Airflow for Data Observability -- interactive CLI")
    print("=" * 60)

    if not session.environments:
        print(f"\nNo MWAA environments found in {config.region}.")
        return {"applied": False, "session": session}

    print(f"\n{len(session.environments)} MWAA environment(s) found. Each was checked against its active configuration files.\n")
    for i, entry in enumerate(session.environments, start=1):
        print(f"  [{i}] {entry.name}  (Airflow {entry.airflow_version}, {_status_label(entry.plan)})")

    choice = _prompt_choice(len(session.environments), input_func)
    if choice is None:
        print("\nExiting -- no changes made.")
        return {"applied": False, "session": session}

    entry, ctx = session.environments[choice - 1], contexts[choice - 1]

    print(f"\nSelected: {entry.name}")
    if not entry.plan.file_changes:
        print("This environment is already fully configured for Data Observability. Nothing to do.")
        return {"applied": False, "session": session, "environment": entry.name}

    print(f"\nRationale: {entry.plan.rationale}")

    uploads = compute_apply_actions(ctx, entry.plan)
    print("\nProposed changes:")
    for upload in uploads:
        diff = render_unified_diff(upload.path, upload.old_content, upload.content)
        print(f"\n--- {upload.action}: {upload.path} ---")
        print(diff if diff else "(no textual change)")

    if config.dry_run:
        print("\nDry run (--dry-run) -- not applying. No changes made.")
        return {"applied": False, "session": session, "environment": entry.name, "uploads": uploads}

    if not _prompt_yes_no("\nRun apply now?", input_func):
        cmd = f"python mwaa.pyz apply --session-id {session.session_id} --name {entry.name} --region {config.region} --yes"
        print(f"\nNo changes made. To apply later, run:\n  {cmd}")
        return {"applied": False, "session": session, "environment": entry.name, "uploads": uploads}

    with reporter.report_step("apply_changes"):
        result = apply_to_environment(client, ctx, uploads)

    print(f"\nUploaded {len(result['uploaded'])} file(s).")
    if result["update_environment_called"]:
        print("UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).")
        print()
        print("Next: once it's back, trigger a DAG run in the Airflow UI, then check")
        print("Data Observability: Jobs Monitoring in Datadog (https://app.datadoghq.com/data-jobs/)")
        print("to confirm lineage events are arriving. This CLI does not trigger a DAG run for you.")

    return {"applied": True, "session": session, "environment": entry.name, "uploads": uploads, "result": result}


def run_scan(config: ScanConfig, reporter: Reporter, input_func: InputFunc = input) -> dict[str, Any]:
    """Discover every environment in the region, persist the session, and hand off."""
    client = MwaaClient(region=config.region)

    with reporter.report_step("discover_environments"):
        contexts = discover_environments(client)

    with reporter.report_step("build_session"):
        session = build_session(config.session_id, config.region, config.dd_site, contexts)

    with reporter.report_step("persist_session"):
        save_session(session)

    if not config.interactive:
        _print_ui_handoff(session)
        return {"applied": False, "session": session}

    return _run_interactive(client, config, session, contexts, reporter, input_func)
