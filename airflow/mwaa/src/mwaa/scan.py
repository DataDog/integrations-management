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

Where the session actually gets persisted (network intake API vs a local
file) is select_session_store's call, not this module's -- see
session_store_selection.py. Whatever it picks, the UI-handoff/apply-hint
messages below have to agree with it, since a session saved locally isn't
visible to the network API or the UI at all.
"""

from typing import Any, Callable

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .apply import apply_to_environment, compute_apply_actions, interpolate_api_key
from .checks import ProbeContext
from .diff_preview import render_unified_diff
from .discovery import discover_environments
from .plan import Plan
from .scan_config import ScanConfig
from .session import Session, build_session, seal_applied
from .session_store import FilesystemSessionStore, SessionStore
from .session_store_selection import select_session_store

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


def _apply_hint(session: Session, environment_name: str, region: str, offline: bool) -> str:
    """The apply command to suggest -- must use the same store mode this session was saved to."""
    cmd = f"python mwaa.pyz apply --session-id {session.session_id} --name {environment_name} --region {region} --dd-api-key <DD_API_KEY>"
    return f"{cmd} --offline" if offline else f"{cmd} --dd-site <DD_SITE>"


def _print_ui_handoff(session: Session, region: str, dd_site: str, offline: bool) -> None:
    print(f"\nSession persisted: {session.session_id}")
    flagged = [e for e in session.environments if e.issues]
    if flagged:
        print(f"{len(flagged)} of {len(session.environments)} environment(s) have issues recorded -- see them when you apply.")
    if offline:
        # Saved to a local file, not the network -- the Configure Airflow UI has
        # no way to see this session, so pointing at it would be misleading.
        print("Saved locally (offline) -- apply with, e.g.:")
        print(f"  {_apply_hint(session, '<ENVIRONMENT_NAME>', region, offline)}")
    else:
        print("Continue in the Configure Airflow UI:")
        print(f"  https://app.{dd_site}/data-obs/configure/airflow?session_id={session.session_id}")


def _run_interactive(
    client: MwaaClient,
    config: ScanConfig,
    session: Session,
    contexts: list[ProbeContext],
    reporter: Reporter,
    input_func: InputFunc,
    store: SessionStore,
    offline: bool,
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
        issue_note = f", {len(entry.issues)} issue(s) found" if entry.issues else ""
        print(f"  [{i}] {entry.name}  (Airflow {entry.airflow_version}, {_status_label(entry.plan)}{issue_note})")

    choice = _prompt_choice(len(session.environments), input_func)
    if choice is None:
        print("\nExiting -- no changes made.")
        return {"applied": False, "session": session}

    entry, ctx = session.environments[choice - 1], contexts[choice - 1]

    print(f"\nSelected: {entry.name}")

    if entry.issues:
        print(f"\n{len(entry.issues)} issue(s) were found when this session was scanned:")
        for issue in entry.issues:
            reporter.report_finding(issue)
        print("\nThese don't block applying -- review them before continuing.")

    if not entry.plan.file_changes:
        print("This environment is already fully configured for Data Observability. Nothing to do.")
        return {"applied": False, "session": session, "environment": entry.name}

    print(f"\nRationale: {entry.plan.rationale}")

    uploads = interpolate_api_key(compute_apply_actions(ctx, entry.plan), config.dd_api_key)
    print("\nProposed changes:")
    for upload in uploads:
        diff = render_unified_diff(upload.path, upload.old_content, upload.content)
        print(f"\n--- {upload.action}: {upload.path} ---")
        print(diff if diff else "(no textual change)")

    if config.dry_run:
        print("\nDry run (--dry-run) -- not applying. No changes made.")
        return {"applied": False, "session": session, "environment": entry.name, "uploads": uploads}

    if not _prompt_yes_no("\nRun apply now?", input_func):
        cmd = _apply_hint(session, entry.name, config.region, offline)
        print(f"\nNo changes made. To apply later, run:\n  {cmd}")
        return {"applied": False, "session": session, "environment": entry.name, "uploads": uploads}

    # The scan/discovery client above is read-only by construction (see
    # MwaaClient's `read_only` guard); applying needs a separate, full-power
    # client, created only once the user has explicitly confirmed.
    apply_client = MwaaClient(region=config.region)
    with reporter.report_step("apply_changes"):
        result = apply_to_environment(apply_client, ctx, uploads)

    session = seal_applied(session, entry.name)
    store.save(session)

    print(f"\nUploaded {len(result['uploaded'])} file(s).")
    if result["update_environment_called"]:
        print("UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).")
        print()
        print("Next: once it's back, trigger a DAG run in the Airflow UI, then check")
        print(f"Data Observability: Jobs Monitoring in Datadog (https://app.{config.dd_site}/data-jobs/)")
        print("to confirm lineage events are arriving. This CLI does not trigger a DAG run for you.")

    return {"applied": True, "session": session, "environment": entry.name, "uploads": uploads, "result": result}


def run_scan(config: ScanConfig, reporter: Reporter, input_func: InputFunc = input) -> dict[str, Any]:
    """Discover every environment in the region, persist the session, and hand off."""
    store, forced_by_unreachable_network = select_session_store(config.offline, config.dd_site, config.dd_api_key)
    offline = isinstance(store, FilesystemSessionStore)

    client = MwaaClient(region=config.region, read_only=True)

    with reporter.report_step("discover_environments"):
        contexts = discover_environments(client)

    with reporter.report_step("build_session"):
        session = build_session(config.session_id, config.region, config.dd_site, contexts)

    with reporter.report_step("persist_session"):
        store.save(session)

    # Explicit --offline still leaves a plain scan-then-apply flow fully
    # workable; an unreachable network wasn't a choice, and non-interactive
    # scan's whole design is to hand off to a UI that will never see a
    # locally-saved session. Interactive is the only way left to review and
    # apply anything in that case, so force it rather than stranding the
    # customer with just a print-out.
    if not config.interactive and forced_by_unreachable_network:
        print("\nContinuing interactively instead, since there's no UI that can see a session saved locally.")
    if not config.interactive and not forced_by_unreachable_network:
        _print_ui_handoff(session, config.region, config.dd_site, offline)
        return {"applied": False, "session": session}

    return _run_interactive(client, config, session, contexts, reporter, input_func, store, offline)
