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
actual files. The one exception carries no risk either: an EnvVarChange
proposing to add OPENLINEAGE_API_KEY never carries the real key, only
DD_API_KEY_PLACEHOLDER (startup_script.py) -- apply.py is the only place the
real key ever gets substituted in, right before a file is written or
previewed.

Each environment also carries `issues`: findings from the subset of probe
checks.py checks that matter for whether it's *safe* to apply this plan --
a conflicting AirflowConfigurationOptions value, a referenced constraints/
wheel file that doesn't exist, an execution role that can't read what the
plan would write, a base constraints file that couldn't be downloaded.
Recorded at scan time so `apply` can surface them right before acting,
without recomputing anything. A WARN issue doesn't block apply, since the
person running it may already know and want to proceed anyway; a FAIL one
does (see blocking_issues), matching the UI, which won't continue past
review while one exists.

Each environment also carries `file_versions` (see probe.py): the latest
S3 VersionId of every file its plan reads or might write, so apply can
refuse if any changed since. Changes depending on a file with an
unapplied upload or an unreadable version are left out of the plan
entirely (_without_blocked_changes).

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
from typing import Optional

from airflow_shared.reporter import Finding, FindingStatus

from .checks import (
    ProbeContext,
    check_base_constraints,
    check_constraint_directives,
    check_constraint_path,
    check_execution_role_s3_access,
    check_file_versions,
    check_openlineage_precedence,
    check_unapplied_uploads,
    check_wheel_references,
    unapplied_uploads,
)
from .openlineage_config import analyze
from .plan import STARTUP_SCRIPT_PATHS, ConstraintDirectiveChange, EnvVarChange, Plan, compute_plan, plan_from_dict

#: The subset of probe checks worth recording at scan time and re-surfacing
#: at apply time -- each one is a way applying this environment's plan could
#: go wrong or interact badly with something already there, not just a
#: normal onboarding-status fact (that's already_configured/plan above).
_ISSUE_CHECKS = (
    check_base_constraints,
    check_constraint_directives,
    check_unapplied_uploads,
    check_file_versions,
    check_openlineage_precedence,
    check_constraint_path,
    check_wheel_references,
    check_execution_role_s3_access,
)


#: The checks that only read ProbeContext, never call AWS themselves.
_PURE_CHECKS = (check_base_constraints, check_constraint_directives, check_unapplied_uploads, check_file_versions, check_openlineage_precedence)


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
    already_configured: bool  # OpenLineage is effectively configured -- see openlineage_config.py
    plan: Plan
    issues: list[Finding] = field(default_factory=list)
    status: "ScannedStatus | AppliedStatus" = field(default_factory=ScannedStatus)
    # plan path label -> latest S3 VersionId at scan time (None = didn't exist); see probe.py
    file_versions: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Session:
    """One `scan` run's full survey: every environment found, and each one's plan."""

    session_id: str
    region: str
    environments: list[EnvironmentEntry] = field(default_factory=list)

    def find(self, name: str) -> "EnvironmentEntry | None":
        return next((e for e in self.environments if e.name == name), None)


class BlockingIssuesError(RuntimeError):
    """The environment has FAIL issues, so its plan won't be applied until they're fixed and `scan` re-run."""


def blocking_issues(entry: EnvironmentEntry) -> list[Finding]:
    """The issues that stop `apply` (and interactive `scan`) from applying this environment's plan."""
    return [issue for issue in entry.issues if issue.status == FindingStatus.FAIL]


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
        if ctx.client is None and check not in _PURE_CHECKS:
            continue
        try:
            finding = check(ctx)
        except Exception as exc:  # noqa: BLE001 - one check's bug shouldn't sink the whole scan
            issues.append(Finding(check.__name__, FindingStatus.WARN, f"could not run this check: {exc}"))
            continue
        if finding.status != FindingStatus.PASS:
            issues.append(finding)
    return issues


def _without_blocked_changes(plan: Plan, ctx: ProbeContext) -> Plan:
    """Drop the changes that depend on a file with an unapplied upload or an unreadable version.

    startup.sh blocks only the env-var changes; any other file (requirements.txt,
    the constraints file, a wheel) blocks every package change. See
    check_unapplied_uploads/check_file_versions for the issues that say why.
    """
    blocked = set(unapplied_uploads(ctx)) | set(ctx.file_version_errors)
    drop_packages = any(label not in STARTUP_SCRIPT_PATHS for label in blocked)
    drop_env_vars = any(label in STARTUP_SCRIPT_PATHS for label in blocked)
    if not drop_packages and not drop_env_vars:
        return plan
    kept = [fc for fc in plan.file_changes if (isinstance(fc, EnvVarChange) and not drop_env_vars) or (not isinstance(fc, EnvVarChange) and not drop_packages)]
    left_out = " and ".join(name for name, dropped in (("package", drop_packages), ("startup.sh", drop_env_vars)) if dropped)
    return replace(
        plan,
        rationale=f"{plan.rationale} The {left_out} changes are left out until the issues recorded for {', '.join(sorted(blocked))} are resolved.",
        file_changes=kept,
    )


def _environment_entry(ctx: ProbeContext, dd_site: str) -> EnvironmentEntry:
    airflow_version = ctx.environment.get("AirflowVersion", "")
    configuration_options = ctx.environment.get("AirflowConfigurationOptions") or {}
    plan = compute_plan(
        airflow_version=airflow_version,
        requirements_text=ctx.requirements_text,
        base_constraints=ctx.base_constraints,
        startup_script_text=ctx.startup_script_text,
        dd_site=dd_site,
        present_wheel_files=ctx.present_wheel_files,
        constraints_path=ctx.constraints_path,
        requirements_path=ctx.requirements_path,
        startup_script_path=ctx.startup_script_path,
        configuration_options=configuration_options,
    )
    openlineage = analyze(airflow_version, ctx.requirements_text, ctx.startup_script_text, configuration_options, dd_site)
    issues = _compute_issues(ctx) + openlineage.issues
    if any(isinstance(fc, ConstraintDirectiveChange) and fc.from_line is None for fc in plan.file_changes):
        # "no --constraint line" is exactly what the plan is about to add
        issues = [i for i in issues if i.check_id != "constraint_path"]
    return EnvironmentEntry(
        name=ctx.environment.get("Name"),
        airflow_version=airflow_version,
        # a flagged version also has to be on the upgrade guide's packages (its plan, before
        # blocked changes are dropped, needs none -- upgrade_needed is also set when that
        # can't be determined, e.g. an unreadable base constraints file)
        already_configured=openlineage.configured and not (plan.source == "flagged_version_table" and plan.upgrade_needed),
        plan=_without_blocked_changes(plan, ctx),
        issues=issues,
        file_versions=ctx.file_versions,
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
                file_versions=e.get("file_versions", {}),
            )
            for e in data["environments"]
        ],
    )
