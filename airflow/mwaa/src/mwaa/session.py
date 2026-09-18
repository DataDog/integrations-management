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
actual files. The one piece of *computed* (not copied) content a Plan does
carry -- the proposed startup.sh -- still can't leak the customer's real
Datadog API key either, because it's never in there in the first place: see
startup_script.py's DD_API_KEY_PLACEHOLDER. apply.py is the only place the
real key ever gets substituted in, right before a file is written or
previewed.

Each environment also carries `issues`: findings from the subset of probe
checks.py checks that matter for whether it's *safe* to apply this plan --
a conflicting AirflowConfigurationOptions value, a referenced constraints/
wheel file that doesn't exist, an execution role that can't read what the
plan would write. Recorded at scan time so `apply` can surface them right
before acting, without recomputing anything -- and without blocking apply
outright, since the person running it may already know and want to proceed
anyway.

Each environment also carries `status`: has THIS session's plan actually
been applied to it yet? Deliberately just the current state, not a history
of transitions -- ScannedStatus/AppliedStatus are the only two that exist
today, and each is its own type so a later status (e.g. a "failed" one)
can carry whatever fields it needs without touching these two. Sealing an
environment to AppliedStatus is done by replacing its EnvironmentEntry
(see apply_command.py/scan.py) -- Session and EnvironmentEntry stay frozen,
consistent with everything else here.
"""

from dataclasses import dataclass, field, replace

from airflow_shared.reporter import Finding, FindingStatus

from .checks import (
    ProbeContext,
    check_constraint_path,
    check_execution_role_s3_access,
    check_openlineage_precedence,
    check_wheel_references,
)
from .plan import Plan, compute_plan, plan_from_dict
from .startup_script import startup_script_looks_configured

#: The subset of probe checks worth recording at scan time and re-surfacing
#: at apply time -- each one is a way applying this environment's plan could
#: go wrong or interact badly with something already there, not just a
#: normal onboarding-status fact (that's already_configured/plan above).
_ISSUE_CHECKS = (
    check_openlineage_precedence,
    check_constraint_path,
    check_wheel_references,
    check_execution_role_s3_access,
)


@dataclass(frozen=True)
class ScannedStatus:
    """Default status: `scan` found this environment and computed a plan for it. Nothing applied yet."""

    type: str = "scanned"


@dataclass(frozen=True)
class AppliedStatus:
    """`apply` (or `scan --interactive`) actually applied this environment's plan."""

    type: str = "applied"


@dataclass(frozen=True)
class EnvironmentEntry:
    """One environment's onboarding status and plan, as surveyed by `scan`."""

    name: str
    airflow_version: str
    already_configured: bool
    plan: Plan
    issues: list[Finding] = field(default_factory=list)
    status: "ScannedStatus | AppliedStatus" = field(default_factory=ScannedStatus)


@dataclass(frozen=True)
class Session:
    """One `scan` run's full survey: every environment found, and each one's plan."""

    session_id: str
    region: str
    environments: list[EnvironmentEntry] = field(default_factory=list)

    def find(self, name: str) -> "EnvironmentEntry | None":
        return next((e for e in self.environments if e.name == name), None)


def seal_applied(session: Session, environment_name: str) -> Session:
    """Return a copy of `session` with one environment's status set to AppliedStatus.

    Called by apply_command.py/scan.py once apply_to_environment has actually
    succeeded for that environment. Session/EnvironmentEntry are frozen, so
    sealing replaces the one entry rather than mutating anything in place.
    """
    return replace(
        session,
        environments=[replace(e, status=AppliedStatus()) if e.name == environment_name else e for e in session.environments],
    )


def _compute_issues(ctx: ProbeContext) -> list[Finding]:
    """Run the issue-relevant checks and keep only what didn't pass.

    Skips the checks that need a real AWS client when ctx.client is None --
    true in tests today, and a real possibility later if scan ever grows a
    structural-only mode. One check raising unexpectedly (e.g. an IAM
    permission gap check.py itself doesn't already catch) is recorded as its
    own issue rather than aborting the scan for this environment.
    """
    issues: list[Finding] = []
    for check in _ISSUE_CHECKS:
        if ctx.client is None and check is not check_openlineage_precedence:
            continue
        try:
            finding = check(ctx)
        except Exception as exc:  # noqa: BLE001 - one check's bug shouldn't sink the whole scan
            issues.append(Finding(check.__name__, FindingStatus.WARN, f"could not run this check: {exc}"))
            continue
        if finding.status != FindingStatus.PASS:
            issues.append(finding)
    return issues


def _environment_entry(ctx: ProbeContext, dd_site: str) -> EnvironmentEntry:
    airflow_version = ctx.environment.get("AirflowVersion", "")
    environment_name = ctx.environment.get("Name")
    plan = compute_plan(
        airflow_version=airflow_version,
        requirements_text=ctx.requirements_text,
        constraints_text=ctx.constraints_text,
        startup_script_text=ctx.startup_script_text,
        dd_site=dd_site,
        environment_name=environment_name,
    )
    return EnvironmentEntry(
        name=environment_name,
        airflow_version=airflow_version,
        already_configured=startup_script_looks_configured(ctx.startup_script_text),
        plan=plan,
        issues=_compute_issues(ctx),
    )


def build_session(session_id: str, region: str, dd_site: str, contexts: list[ProbeContext]) -> Session:
    """Assemble the full session for every environment discovered in one scan run."""
    return Session(
        session_id=session_id,
        region=region,
        environments=[_environment_entry(ctx, dd_site) for ctx in contexts],
    )


def _status_from_dict(data: dict) -> "ScannedStatus | AppliedStatus":
    if data["type"] == "scanned":
        return ScannedStatus()
    if data["type"] == "applied":
        return AppliedStatus()
    raise ValueError(f"unknown EnvironmentEntry status type {data['type']!r}")


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
                issues=[
                    Finding(
                        check_id=i["check_id"],
                        status=FindingStatus(i["status"]),
                        message=i["message"],
                        detail=i.get("detail"),
                    )
                    for i in e.get("issues", [])
                ],
                status=_status_from_dict(e.get("status", {"type": "scanned"})),
            )
            for e in data["environments"]
        ],
    )
