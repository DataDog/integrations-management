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

  PinChange                 a package's version, in constraints.txt or requirements.txt
  ConstraintDirectiveChange requirements.txt's one non-package line: --constraint "..."
  WheelReference            a requirements.txt line installing a Datadog-patched wheel (2.7.2)
  EnvVarChange              one startup.sh variable being added or corrected

No "removed" variant exists because nothing in this plan ever removes a line
-- only adds or corrects one. If that changes, add the variant that case
actually needs then, rather than guessing its shape now.

A flagged version's constraints.txt PinChanges are against the full base
constraints file base_constraints.py resolves, never a file holding only
those pins -- and when that base can't be read, the plan has no package
changes at all rather than ones apply couldn't safely write.

EnvVarChange.to_value is never a real secret -- see startup_script.py's
DD_API_KEY_PLACEHOLDER -- so a Plan is always safe to persist, log, or
display as-is.
"""

from dataclasses import dataclass
from typing import Optional, Union

from .base_constraints import BaseConstraints
from .pins import DAGS_MOUNT_PREFIX, find_constraint_line, find_constraint_path, find_wheel_references, mentions_package, parse_pins, resolve_constraint_s3_key
from .startup_script import SECRET_VAR_NAMES, parse_exports, target_values
from .version_table import DATADOG_WHEEL_BASE_URL, FLAGGED_VERSION_TABLE, SOURCE_DOC, FlaggedVersionEntry, datadog_wheel_filename

REQUIREMENTS_PATH = "requirements.txt"
CONSTRAINTS_PATH = "dags/constraints.txt"
STARTUP_SCRIPT_PATH = "dags/startup.sh"
EXPECTED_CONSTRAINT_LINE_TARGET = "/usr/local/airflow/dags/constraints.txt"
EXPECTED_CONSTRAINT_LINE = f'--constraint "{EXPECTED_CONSTRAINT_LINE_TARGET}"'
OPENLINEAGE_PROVIDER = "apache-airflow-providers-openlineage"


@dataclass(frozen=True)
class PinChange:
    """One package's version being added or bumped, in constraints.txt or requirements.txt."""

    path: str
    package: str
    from_version: Optional[str]  # None means the package wasn't pinned before
    to_version: Optional[str]  # None means the bare package name, no version -- MWAA's constraints resolve it
    type: str = "pin_change"


@dataclass(frozen=True)
class ConstraintDirectiveChange:
    """requirements.txt's `--constraint "..."` line, pointed at the constraints file this plan writes.

    Its own variant because it's neither a package pin nor a startup.sh
    variable -- it's a pip requirements-file directive. from_line is the
    existing --constraint line it replaces (e.g. the upstream URL), or None
    when requirements.txt has none yet; there's only ever one.
    """

    path: str
    from_line: Optional[str]
    to_line: str
    type: str = "constraint_directive_change"


@dataclass(frozen=True)
class WheelReference:
    """A requirements.txt line installing a Datadog-patched wheel, instead of a pin for that package.

    `line` is the wheel's path under the DAGs mount; apply downloads
    `wheel_url` and uploads it to the matching key under DagS3Path first.
    Replaces whatever line already installs `package` (a pin, or a
    different wheel), else is appended.
    """

    path: str
    package: str
    version: str
    wheel_url: str
    line: str
    type: str = "wheel_reference"


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


FileChange = Union[PinChange, ConstraintDirectiveChange, WheelReference, EnvVarChange]


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
        return PinChange(path=data["path"], package=data["package"], from_version=data.get("from_version"), to_version=data.get("to_version"))
    if change_type == "constraint_directive_change":
        return ConstraintDirectiveChange(path=data["path"], from_line=data.get("from_line"), to_line=data["to_line"])
    if change_type == "wheel_reference":
        return WheelReference(
            path=data["path"], package=data["package"], version=data["version"], wheel_url=data["wheel_url"], line=data["line"]
        )
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


def _plan_flagged_version(
    entry: FlaggedVersionEntry, requirements_text: str, base_constraints: Optional[BaseConstraints]
) -> tuple[bool, str, list[FileChange]]:
    default_ol_version = entry.default_versions.get(OPENLINEAGE_PROVIDER, "an old version")
    rationale = (
        f"Airflow {entry.airflow_version} is flagged by Datadog's MWAA upgrade guide: its MWAA-default "
        f"constraints pin {OPENLINEAGE_PROVIDER} {default_ol_version}, which has known "
        "reliability/compatibility issues."
    )
    if base_constraints is None or base_constraints.text is None:
        reason = base_constraints.error if base_constraints else "it wasn't resolved"
        return (
            True,
            f"{rationale} The full base constraints file couldn't be read ({reason}), so this plan leaves out "
            "every package change -- a constraints file holding only the OpenLineage pins would unconstrain "
            "every other package. Re-run scan once it's reachable.",
            [],
        )

    base_pins = parse_pins(base_constraints.text)
    current_req_pins = parse_pins(requirements_text)
    changes: list[FileChange] = [
        PinChange(path=CONSTRAINTS_PATH, package=package, from_version=base_pins.get(package), to_version=target)
        for package, target in entry.target_versions.items()
        if base_pins.get(package) != target
    ]
    if changes:
        rationale += f" {CONSTRAINTS_PATH} is the full constraints file from {base_constraints.source}, with these pins patched in."
        # a --constraint already under the dags mount is the file being patched in place
        if resolve_constraint_s3_key(find_constraint_path(requirements_text) or "", "dags") is None:
            changes.append(
                ConstraintDirectiveChange(path=REQUIREMENTS_PATH, from_line=find_constraint_line(requirements_text), to_line=EXPECTED_CONSTRAINT_LINE)
            )
    referenced_wheels = {ref.rsplit("/", 1)[-1] for ref in find_wheel_references(requirements_text)}
    for package, target in entry.target_versions.items():
        if package in entry.wheel_only_packages:
            filename = datadog_wheel_filename(package, target)
            if filename not in referenced_wheels:
                changes.append(
                    WheelReference(
                        path=REQUIREMENTS_PATH,
                        package=package,
                        version=target,
                        wheel_url=f"{DATADOG_WHEEL_BASE_URL}{filename}",
                        line=f"{DAGS_MOUNT_PREFIX}{filename}",
                    )
                )
        elif current_req_pins.get(package) != target:
            changes.append(PinChange(path=REQUIREMENTS_PATH, package=package, from_version=current_req_pins.get(package), to_version=target))
    return bool(changes), rationale, changes


def _plan_unflagged_version(airflow_version: str, requirements_text: str) -> tuple[bool, str, list[FileChange]]:
    if mentions_package(requirements_text, OPENLINEAGE_PROVIDER):
        return (
            False,
            f"Airflow {airflow_version} is not one of the flagged versions (2.7.2/2.8.1/2.9.2), "
            "and the OpenLineage provider is already in requirements.txt.",
            [],
        )
    return (
        True,
        f"Airflow {airflow_version} is not one of the flagged versions, so MWAA's own default constraints "
        "should already resolve a healthy OpenLineage provider version -- only the package itself needs to "
        "be added, with no constraints.txt change.",
        [PinChange(path=REQUIREMENTS_PATH, package=OPENLINEAGE_PROVIDER, from_version=None, to_version=None)],
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
    base_constraints: Optional[BaseConstraints],
    startup_script_text: Optional[str],
    dd_site: str,
    environment_name: str,
) -> Plan:
    """Compute the onboarding plan for one environment from its real current files.

    base_constraints is only consulted for flagged versions (see ProbeContext).
    """
    flagged_entry = FLAGGED_VERSION_TABLE.get(airflow_version)
    if flagged_entry:
        upgrade_needed, rationale, file_changes = _plan_flagged_version(flagged_entry, requirements_text, base_constraints)
        source = "flagged_version_table"
    else:
        upgrade_needed, rationale, file_changes = _plan_unflagged_version(airflow_version, requirements_text)
        source = "unflagged_version"

    file_changes += _plan_env_var_changes(airflow_version, dd_site, environment_name, startup_script_text)

    return Plan(
        upgrade_needed=upgrade_needed,
        rationale=rationale,
        source=source,
        matched_table_entry=flagged_entry,
        source_doc=SOURCE_DOC,
        file_changes=file_changes,
    )
