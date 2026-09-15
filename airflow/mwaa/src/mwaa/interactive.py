# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Approximates the Configure Airflow UI's flow entirely from the CLI.

Mirrors the screenshots this was built from: select an environment from a
discovered list, review the proposed changes, confirm, apply. Useful for
testing the whole thing end to end before there's a real UI or backend to
drive it -- everything here is the same code the eventual UI-driven `scan`/
`apply` split would call, just wired together with terminal prompts instead
of an HTTP round trip.

Step 5 of the UI flow ("Run a DAG") is deliberately just guidance printed at
the end, not an automated DAG trigger -- there's no canonical DAG to run
against an arbitrary customer environment, and triggering one via the MWAA
REST API is a separate scope decision.

`config.dry_run` (the --dry-run flag) skips the "Apply these changes?" prompt
entirely rather than relying on the user answering it correctly -- so nothing
ever gets applied, no matter what.
"""

from typing import Any, Callable

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .apply import apply_to_environment, compute_apply_actions
from .diff_preview import render_unified_diff
from .discovery import discover_environments
from .plan import Plan, compute_plan
from .scan_config import ScanConfig

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


def run_interactive(config: ScanConfig, reporter: Reporter, input_func: InputFunc = input) -> dict[str, Any]:
    """Discover environments, let the user pick one, review, and apply -- all from the terminal."""
    client = MwaaClient(region=config.region)

    print()
    print("=" * 60)
    print("  Configure Airflow for Data Observability -- interactive CLI")
    print("=" * 60)

    with reporter.report_step("discover_environments"):
        contexts = discover_environments(client)

    if not contexts:
        print(f"\nNo MWAA environments found in {config.region}.")
        return {"applied": False}

    plans = [
        compute_plan(
            airflow_version=ctx.environment.get("AirflowVersion", ""),
            requirements_text=ctx.requirements_text,
            constraints_text=ctx.constraints_text,
            startup_script_text=ctx.startup_script_text,
            dd_site=config.dd_site,
        )
        for ctx in contexts
    ]

    print(f"\n{len(contexts)} MWAA environment(s) found. Each was checked against its active configuration files.\n")
    for i, (ctx, plan) in enumerate(zip(contexts, plans), start=1):
        name = ctx.environment.get("Name")
        version = ctx.environment.get("AirflowVersion")
        print(f"  [{i}] {name}  (Airflow {version}, {_status_label(plan)})")

    choice = _prompt_choice(len(contexts), input_func)
    if choice is None:
        print("\nExiting -- no changes made.")
        return {"applied": False}

    ctx, plan = contexts[choice - 1], plans[choice - 1]
    name = ctx.environment.get("Name")

    print(f"\nSelected: {name}")
    if not plan.file_changes:
        print("This environment is already fully configured for Data Observability. Nothing to do.")
        return {"applied": False, "environment": name}

    print(f"\nRationale: {plan.rationale}")

    uploads = compute_apply_actions(ctx, plan)
    print("\nProposed changes:")
    for upload in uploads:
        diff = render_unified_diff(upload.path, upload.old_content, upload.content)
        print(f"\n--- {upload.action}: {upload.path} ---")
        print(diff if diff else "(no textual change)")

    if config.dry_run:
        print("\nDry run (--dry-run) -- not applying. No changes made.")
        return {"applied": False, "environment": name, "plan": plan, "uploads": uploads}

    if not _prompt_yes_no("\nApply these changes?", input_func):
        print("\nAborted -- no changes made.")
        return {"applied": False, "environment": name, "plan": plan}

    with reporter.report_step("apply_changes"):
        result = apply_to_environment(client, ctx.environment, uploads)

    print(f"\nUploaded {len(result['uploaded'])} file(s).")
    if result["update_environment_called"]:
        print("UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).")
        print()
        print("Next: once it's back, trigger a DAG run in the Airflow UI, then check")
        print("Data Observability: Jobs Monitoring in Datadog (https://app.datadoghq.com/data-jobs/)")
        print("to confirm lineage events are arriving. This CLI does not trigger a DAG run for you.")

    return {"applied": True, "environment": name, "plan": plan, "uploads": uploads, "result": result}
