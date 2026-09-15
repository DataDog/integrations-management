# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Assembles the scan payload that would eventually be phoned home to Datadog.

For now this is only ever printed (--dry-run is implicit, there is no
phone-home endpoint yet) -- see main.py. The shape here is a first draft,
expected to change as the Configure Airflow UI's actual needs get nailed down.

Deliberately does NOT include raw requirements.txt/constraints.txt/startup
script content. Startup scripts routinely export live credentials, and a
real scan against the do-test-env account proved it: one environment's
startup script had a live Datadog API key in it, captured verbatim. Rather
than maintain a secret-redaction pass over arbitrary free-form shell script
content, the payload only ever carries the *computed plan* -- pin diffs,
rationale, the matched version-table entry -- which is exactly what's needed
to understand why a diff was proposed, and structurally can't contain a
credential, since none of it is copied from the environment's actual files.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .checks import ProbeContext
from .plan import compute_plan
from .startup_script import startup_script_looks_configured


def _environment_entry(ctx: ProbeContext, dd_site: str) -> dict[str, Any]:
    airflow_version = ctx.environment.get("AirflowVersion", "")
    plan = compute_plan(
        airflow_version=airflow_version,
        requirements_text=ctx.requirements_text,
        constraints_text=ctx.constraints_text,
        startup_script_text=ctx.startup_script_text,
        dd_site=dd_site,
    )
    return {
        "name": ctx.environment.get("Name"),
        "airflow_version": airflow_version,
        "already_configured": startup_script_looks_configured(ctx.startup_script_text),
        "plan": asdict(plan),
    }


def build_payload(session_id: str, region: str, dd_site: str, contexts: list[ProbeContext]) -> dict[str, Any]:
    """Assemble the full scan payload for every discovered environment."""
    return {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "environments": [_environment_entry(ctx, dd_site) for ctx in contexts],
    }
