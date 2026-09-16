# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""A Session: the full realm of possibilities `scan` surveys for one region.

Not a decision -- just a blob of state. `scan` builds one by discovering
every MWAA environment in a region and computing each one's onboarding plan,
then persists it (session_store.py) keyed by session id. Later, `apply`
--session-id picks ONE environment out of that survey via --name; the
session itself never says which one to act on.

Deliberately does NOT include raw requirements.txt/constraints.txt/startup
script content. Startup scripts routinely export live credentials, and a
real scan against the do-test-env account proved it: one environment's
startup script had a live Datadog API key in it, captured verbatim. Rather
than maintain a secret-redaction pass over arbitrary free-form shell script
content, a session only ever carries each environment's *computed plan* --
pin diffs, rationale, the matched version-table entry -- which is exactly
what's needed to understand why a diff was proposed, and structurally can't
contain a credential, since none of it is copied from the environment's
actual files.
"""

from dataclasses import dataclass, field

from .checks import ProbeContext
from .plan import Plan, compute_plan, plan_from_dict
from .startup_script import startup_script_looks_configured


@dataclass(frozen=True)
class EnvironmentEntry:
    """One environment's onboarding status and plan, as surveyed by `scan`."""

    name: str
    airflow_version: str
    already_configured: bool
    plan: Plan


@dataclass(frozen=True)
class Session:
    """One `scan` run's full survey: every environment found, and each one's plan."""

    session_id: str
    region: str
    environments: list[EnvironmentEntry] = field(default_factory=list)

    def find(self, name: str) -> "EnvironmentEntry | None":
        return next((e for e in self.environments if e.name == name), None)


def _environment_entry(ctx: ProbeContext, dd_site: str, dd_api_key: str) -> EnvironmentEntry:
    airflow_version = ctx.environment.get("AirflowVersion", "")
    plan = compute_plan(
        airflow_version=airflow_version,
        requirements_text=ctx.requirements_text,
        constraints_text=ctx.constraints_text,
        startup_script_text=ctx.startup_script_text,
        dd_site=dd_site,
        dd_api_key=dd_api_key,
    )
    return EnvironmentEntry(
        name=ctx.environment.get("Name"),
        airflow_version=airflow_version,
        already_configured=startup_script_looks_configured(ctx.startup_script_text),
        plan=plan,
    )


def build_session(session_id: str, region: str, dd_site: str, dd_api_key: str, contexts: list[ProbeContext]) -> Session:
    """Assemble the full session for every environment discovered in one scan run."""
    return Session(
        session_id=session_id,
        region=region,
        environments=[_environment_entry(ctx, dd_site, dd_api_key) for ctx in contexts],
    )


def session_from_dict(data: dict) -> Session:
    """The reverse of dataclasses.asdict(session) -- see plan_from_dict for why this can't
    just be Session(**data)."""
    return Session(
        session_id=data["session_id"],
        region=data["region"],
        environments=[
            EnvironmentEntry(
                name=e["name"],
                airflow_version=e["airflow_version"],
                already_configured=e["already_configured"],
                plan=plan_from_dict(e["plan"]),
            )
            for e in data["environments"]
        ],
    )
