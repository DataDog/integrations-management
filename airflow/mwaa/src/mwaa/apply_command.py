# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Orchestrates a full apply run against one MWAA environment.

Loads the Session a prior `scan --session-id` persisted -- via whichever
SessionStore select_session_store picks for this run (network by default,
local file under --offline or if the network's unreachable), or under
SESSION_OVERRIDE_PATH, a hand-authored one instead -- see session_override.py.
Pulls out the plan for --name, then always fetches that environment fresh
and previews before doing anything mutating -- without --yes (see
apply_config.py), this only prints what it would do.

Once a real apply succeeds, seal_applied (session.py) marks that one
environment's entry AppliedStatus and this re-persists the session --
scoped to just that environment, since a session covers every environment
`scan` found and only --name's one is ever acted on here.
"""

import os
from typing import Any

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Reporter

from .apply import apply_to_environment, compute_apply_actions, interpolate_api_key
from .apply_config import ApplyConfig
from .diff_preview import render_unified_diff
from .probe import build_context
from .session import seal_applied
from .session_override import SESSION_OVERRIDE_ENV_VAR, load_session_override
from .session_store_selection import select_session_store

WORKFLOW_TYPE = "mwaa-setup"


def run_apply(config: ApplyConfig, reporter: Reporter) -> dict[str, Any]:
    """Load the session, find --name's plan in it, and preview or apply it."""
    store = select_session_store(config.offline, config.dd_site, config.dd_api_key)

    override_path = os.environ.get(SESSION_OVERRIDE_ENV_VAR)
    if override_path:
        print(f"{SESSION_OVERRIDE_ENV_VAR} is set -- loading the session from {override_path} instead of session {config.session_id}.")
        session = load_session_override(override_path)
    else:
        with reporter.report_step("load_session"):
            session = store.load(config.session_id)

    entry = session.find(config.environment_name)
    if entry is None:
        known = ", ".join(e.name for e in session.environments) or "(none)"
        print(f"No plan for '{config.environment_name}' in this session. Environments in this session: {known}")
        return {"applied": False, "plan": None, "uploads": []}

    plan = entry.plan

    if entry.issues:
        print(f"\n{len(entry.issues)} issue(s) were found when this session was scanned:")
        for issue in entry.issues:
            reporter.report_finding(issue)
        print("\nThese don't block applying -- review them before continuing.")

    client = MwaaClient(region=config.region)

    with reporter.report_step("fetch_environment"):
        ctx = build_context(client, config.environment_name)

    if not plan.file_changes:
        print("Nothing to apply -- this environment is already fully configured.")
        return {"applied": False, "plan": plan, "uploads": []}

    uploads = interpolate_api_key(compute_apply_actions(ctx, plan), config.dd_api_key)

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
        result = apply_to_environment(client, ctx, uploads)

    session = seal_applied(session, config.environment_name)
    store.save(session)

    print()
    print(f"Uploaded {len(result['uploaded'])} file(s).")
    if result["update_environment_called"]:
        print("UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).")

    return {"applied": True, "plan": plan, "uploads": uploads, "result": result}
