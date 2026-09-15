# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Orchestrates a full apply run against one MWAA environment.

Always fetches fresh and always previews before doing anything mutating --
without --yes (see apply_config.py), this only prints what it would do.

--interactive delegates to interactive.py's discovery-driven, multi-environment
walkthrough instead of targeting the one environment named by --name.
"""

import os
from typing import Any

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .apply import apply_to_environment, compute_apply_actions
from .apply_config import ApplyConfig
from .diff_preview import render_unified_diff
from .interactive import run_interactive
from .plan import Plan, compute_plan
from .plan_override import PLAN_OVERRIDE_ENV_VAR, load_plan_override
from .probe import build_context
from .scan_config import ScanConfig

WORKFLOW_TYPE = "mwaa-setup"


def run_apply(config: ApplyConfig, reporter: Reporter) -> dict[str, Any]:
    """Fetch the environment fresh, compute its plan, and preview or apply the changes.

    PLAN_OVERRIDE_PATH (see plan_override.py) is a local/dev escape hatch, not
    part of the documented customer-facing CLI surface: when set, it supplies
    the environment name, region, and plan itself, overriding config entirely
    -- takes precedence even over --interactive.
    """
    override_path = os.environ.get(PLAN_OVERRIDE_ENV_VAR)

    if config.interactive and not override_path:
        scan_config = ScanConfig(region=config.region, dd_site=config.dd_site, dry_run=config.dry_run)
        return run_interactive(scan_config, reporter)

    plan: Plan
    if override_path:
        override = load_plan_override(override_path)
        print(f"{PLAN_OVERRIDE_ENV_VAR} is set -- applying the plan from {override_path} instead of computing one.")
        environment_name, region, dd_site, plan = override.environment_name, override.region, override.dd_site, override.plan
    else:
        environment_name, region, dd_site = config.environment_name, config.region, config.dd_site

    client = MwaaClient(region=region)

    with reporter.report_step("fetch_environment"):
        ctx = build_context(client, environment_name)

    if not override_path:
        with reporter.report_step("compute_plan"):
            plan = compute_plan(
                airflow_version=ctx.environment.get("AirflowVersion", ""),
                requirements_text=ctx.requirements_text,
                constraints_text=ctx.constraints_text,
                startup_script_text=ctx.startup_script_text,
                dd_site=dd_site,
            )

    if not plan.file_changes:
        print("Nothing to apply -- this environment is already fully configured.")
        return {"applied": False, "plan": plan, "uploads": []}

    uploads = compute_apply_actions(ctx, plan)

    print()
    print(f"Rationale: {plan.rationale}")
    print()
    print("Planned changes:")
    for upload in uploads:
        diff = render_unified_diff(upload.path, upload.old_content, upload.content)
        print(f"\n--- {upload.action}: {upload.path} ---")
        print(diff if diff else "(no textual change)")

    if not config.confirmed:
        print()
        print("Dry run only -- pass --yes to actually upload these files and update the environment.")
        return {"applied": False, "plan": plan, "uploads": uploads}

    with reporter.report_step("apply_changes"):
        result = apply_to_environment(client, ctx.environment, uploads)

    print()
    print(f"Uploaded {len(result['uploaded'])} file(s).")
    if result["update_environment_called"]:
        print("UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).")

    return {"applied": True, "plan": plan, "uploads": uploads, "result": result}
