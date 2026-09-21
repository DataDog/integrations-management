# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Computes the OpenLineage onboarding plan for one MWAA environment.

This is the client-side equivalent of the "Review proposed changes" screen in
the Configure Airflow UI: given an environment's real current requirements.txt/
constraints.txt/startup script, decide what needs to change and why. The
"why" (rationale, source, matched_table_entry) is carried alongside the diff
itself so a persisted session (see session.py) is enough to reconstruct the
reasoning later, without needing to re-run this code against the version
table as it existed at the time.

Plan.file_changes is a discriminated union (tagged by `type`) rather than one
generic shape, because "a package version changed" and "a startup.sh
variable changed" are genuinely different things with different fields, and
forcing them into one generic before/after-line shape would either lose the
structure (package name, variable name) a UI wants to key off of, or invite
smuggling human-readable description text into the same field as literal
diff content -- which is exactly the ambiguity that motivated this shape:

  PinChange                a package's version, in constraints.txt or requirements.txt
  ConstraintDirectiveAdded requirements.txt's one non-package line: --constraint "..."
  EnvVarChange             one startup.sh variable being added or corrected

No "removed" variant exists because nothing in this plan ever removes a line
-- only adds or corrects one. If that changes, add the variant that case
actually needs then, rather than guessing its shape now.

EnvVarChange.to_value is never a real secret -- see startup_script.py's
DD_API_KEY_PLACEHOLDER -- so a Plan is always safe to persist, log, or
display as-is.
"""

from dataclasses import dataclass
from typing import Optional, Union

from .pins import OPENLINEAGE_PACKAGES, find_constraint_path, parse_bare_packages, parse_pins, resolve_constraint_s3_key
from .startup_script import SECRET_VAR_NAMES, parse_exports, target_values
from .version_table import FLAGGED_VERSION_TABLE, SOURCE_DOC, FlaggedVersionEntry

REQUIREMENTS_PATH = "requirements.txt"
CONSTRAINTS_PATH = "dags/constraints.txt"
STARTUP_SCRIPT_PATH = "dags/startup.sh"
EXPECTED_CONSTRAINT_LINE_TARGET = "/usr/local/airflow/dags/constraints.txt"


@dataclass(frozen=True)
class PinChange:
    """One package's version being added or bumped, in constraints.txt or requirements.txt."""

    path: str
    package: str
    from_version: Optional[str]  # None means the package wasn't pinned before
    to_version: str
    type: str = "pin_change"


@dataclass(frozen=True)
class ConstraintDirectiveAdded:
    """requirements.txt's `--constraint "..."` line, when it doesn't have one yet.

    Its own variant because it's neither a package pin nor a startup.sh
    variable -- it's a pip requirements-file directive.
    """

    path: str
    line: str
    type: str = "constraint_directive_added"


@dataclass(frozen=True)
class EnvVarChange:
    """One startup.sh variable being added or corrected.

    from_value is None either because the variable is missing entirely, or
    (see plan.py's _plan_env_var_changes) because it's a secret variable that
    already has *some* value -- we have no real value to compare against, so
    we never propose "correcting" one, only adding it when it's missing.
    to_value is a placeholder, never the real value, when secret is True.
    """

    path: str
    name: str
    from_value: Optional[str]
    to_value: str
    secret: bool
    type: str = "env_var_change"


FileChange = Union[PinChange, ConstraintDirectiveAdded, EnvVarChange]


@dataclass(frozen=True)
class Plan:
    """The full onboarding plan for one environment."""

    upgrade_needed: bool
    rationale: str
    source: str  # "flagged_version_table" | "unflagged_version"
    matched_table_entry: Optional[FlaggedVersionEntry]
    source_doc: str
    file_changes: list[FileChange]


def _file_change_from_dict(data: dict) -> FileChange:
    change_type = data["type"]
    if change_type == "pin_change":
        return PinChange(path=data["path"], package=data["package"], from_version=data.get("from_version"), to_version=data["to_version"])
    if change_type == "constraint_directive_added":
        return ConstraintDirectiveAdded(path=data["path"], line=data["line"])
    if change_type == "env_var_change":
        return EnvVarChange(
            path=data["path"], name=data["name"], from_value=data.get("from_value"), to_value=data["to_value"], secret=data["secret"]
        )
    raise ValueError(f"unknown FileChange type {change_type!r}")


def plan_from_dict(data: dict) -> Plan:
    """The reverse of dataclasses.asdict(plan) -- reconstructs real Plan/FileChange variant/
    FlaggedVersionEntry instances from their plain-dict JSON form.

    Shared by session.py (loading a persisted or overridden Session's per-
    environment plans) -- asdict() alone only serializes, dataclasses don't
    reconstruct themselves from a plain dict.
    """
    matched_table_entry = data.get("matched_table_entry")
    return Plan(
        upgrade_needed=data["upgrade_needed"],
        rationale=data["rationale"],
        source=data["source"],
        matched_table_entry=FlaggedVersionEntry(**matched_table_entry) if matched_table_entry else None,
        source_doc=data["source_doc"],
        file_changes=[_file_change_from_dict(fc) for fc in data["file_changes"]],
    )


def _plan_flagged_version(entry: FlaggedVersionEntry, current_req_pins: dict, current_con_pins: dict) -> tuple[bool, str, list[tuple]]:
    diffs = [
        (package, current_con_pins.get(package) or current_req_pins.get(package), target)
        for package, target in entry.target_versions.items()
        if (current_con_pins.get(package) or current_req_pins.get(package)) != target
    ]
    default_ol_version = entry.default_versions.get("apache-airflow-providers-openlineage", "an old version")
    rationale = (
        f"Airflow {entry.airflow_version} is flagged by Datadog's MWAA upgrade guide: its MWAA-default "
        f"constraints pin apache-airflow-providers-openlineage {default_ol_version}, which has known "
        "reliability/compatibility issues."
    )
    return bool(diffs), rationale, diffs


def _plan_unflagged_version(airflow_version: str, mentioned_packages: set) -> tuple[bool, str, list[tuple]]:
    if any(pkg in mentioned_packages for pkg in OPENLINEAGE_PACKAGES):
        return (
            False,
            f"Airflow {airflow_version} is not one of the flagged versions (2.7.2/2.8.1/2.9.2), "
            "and the OpenLineage provider is already pinned in requirements.txt.",
            [],
        )
    return (
        True,
        f"Airflow {airflow_version} is not one of the flagged versions, so MWAA's own default constraints "
        "should already resolve a healthy OpenLineage provider version -- only the package itself needs to "
        "be added, with no constraints.txt change.",
        [("apache-airflow-providers-openlineage", None, "unpinned (resolved by MWAA's current default constraints)")],
    )


def _plan_env_var_changes(airflow_version: str, dd_site: str, environment_name: str, startup_script_text: Optional[str]) -> list[EnvVarChange]:
    """Diff startup.sh variable-by-variable instead of treating the whole file as one blob.

    A secret variable that already has *some* value is left alone even if we
    can't verify it's the right one -- we have nothing real to compare it
    against, and proposing to overwrite a customer's working key on every
    scan would be worse than occasionally missing a wrong one.
    """
    existing = parse_exports(startup_script_text or "")
    changes = []
    for name, to_value in target_values(airflow_version, dd_site, environment_name):
        from_value = existing.get(name)
        secret = name in SECRET_VAR_NAMES
        if secret and from_value is not None:
            continue
        if not secret and from_value == to_value:
            continue
        changes.append(EnvVarChange(path=STARTUP_SCRIPT_PATH, name=name, from_value=from_value, to_value=to_value, secret=secret))
    return changes


def compute_plan(
    airflow_version: str,
    requirements_text: str,
    constraints_text: Optional[str],
    startup_script_text: Optional[str],
    dd_site: str,
    environment_name: str,
) -> Plan:
    """Compute the onboarding plan for one environment from its real current files."""
    current_req_pins = parse_pins(requirements_text)
    current_con_pins = parse_pins(constraints_text or "")

    flagged_entry = FLAGGED_VERSION_TABLE.get(airflow_version)
    if flagged_entry:
        upgrade_needed, rationale, diffs = _plan_flagged_version(flagged_entry, current_req_pins, current_con_pins)
        source = "flagged_version_table"
    else:
        mentioned_packages = set(current_req_pins) | parse_bare_packages(requirements_text)
        upgrade_needed, rationale, diffs = _plan_unflagged_version(airflow_version, mentioned_packages)
        flagged_entry = None
        source = "unflagged_version"

    file_changes: list[FileChange] = []

    if diffs:
        if flagged_entry:
            file_changes += [PinChange(path=CONSTRAINTS_PATH, package=p, from_version=f, to_version=t) for p, f, t in diffs]

        existing_constraint_path = find_constraint_path(requirements_text)
        if flagged_entry and resolve_constraint_s3_key(existing_constraint_path or "", "dags") != CONSTRAINTS_PATH:
            file_changes.append(ConstraintDirectiveAdded(path=REQUIREMENTS_PATH, line=f'--constraint "{EXPECTED_CONSTRAINT_LINE_TARGET}"'))
        file_changes += [PinChange(path=REQUIREMENTS_PATH, package=p, from_version=f, to_version=t) for p, f, t in diffs]

    file_changes += _plan_env_var_changes(airflow_version, dd_site, environment_name, startup_script_text)

    return Plan(
        upgrade_needed=upgrade_needed,
        rationale=rationale,
        source=source,
        matched_table_entry=flagged_entry,
        source_doc=SOURCE_DOC,
        file_changes=file_changes,
    )
