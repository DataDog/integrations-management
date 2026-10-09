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

from dataclasses import dataclass, replace
from typing import Optional, Union

from .base_constraints import BaseConstraints
from .pins import DAGS_MOUNT_PREFIX, OPENLINEAGE_PROVIDER, find_constraint_lines, find_constraint_path, mentions_package, resolve_constraint_s3_key, stale_pin, wheel_identity
from .openlineage_config import OpenLineageState, analyze, is_intake_url, is_set
from .startup_script import KEEP_EXISTING_VAR_NAMES, SECRET_VAR_NAMES, parse_exports, target_values
from .version_table import DATADOG_WHEEL_BASE_URL, FLAGGED_VERSION_TABLE, SOURCE_DOC, FlaggedVersionEntry, datadog_wheel_filename

REQUIREMENTS_PATH = "requirements.txt"
CONSTRAINTS_PATH = "dags/constraints.txt"
STARTUP_SCRIPT_PATH = "dags/startup.sh"
# written instead of CONSTRAINTS_PATH/REQUIREMENTS_PATH/STARTUP_SCRIPT_PATH when a file the
# environment doesn't use already sits there -- it may well be another environment's, so
# it's never overwritten
DATADOG_CONSTRAINTS_PATH = "dags/constraints-datadog.txt"
DATADOG_REQUIREMENTS_PATH = "requirements-datadog.txt"
DATADOG_STARTUP_SCRIPT_PATH = "dags/startup-datadog.sh"
REQUIREMENTS_PATHS = (REQUIREMENTS_PATH, DATADOG_REQUIREMENTS_PATH)
STARTUP_SCRIPT_PATHS = (STARTUP_SCRIPT_PATH, DATADOG_STARTUP_SCRIPT_PATH)


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
    Replaces whatever line already installs `package` (a pin, a different
    wheel, or this same line when its S3 object is missing), else is appended.
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


def constraint_line_for(constraints_path: str) -> str:
    """The --constraint line pointing at a `dags/...` constraints label's file under the DAGs mount."""
    return f'--constraint "{DAGS_MOUNT_PREFIX}{constraints_path.removeprefix("dags/")}"'


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
    entry: FlaggedVersionEntry,
    requirements_text: str,
    base_constraints: Optional[BaseConstraints],
    present_wheel_files: frozenset[str],
    constraints_path: str,
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
            f"{rationale} No safe full constraints file could be planned ({reason}), so this plan leaves out "
            "every package change -- a constraints file holding only the OpenLineage pins would unconstrain "
            "every other package.",
            [],
        )
    constraint_lines = find_constraint_lines(requirements_text)
    if len(constraint_lines) > 1:
        # pip enforces every --constraint line, so replacing one would leave the
        # others' old pins in force; a single ConstraintDirectiveChange can't say
        # "remove the rest", so leave it to the customer instead (see check_constraint_directives)
        return (
            True,
            f"{rationale} requirements.txt has {len(constraint_lines)} --constraint lines, and pip enforces all of "
            "them, so this plan leaves out every package change. Consolidate them into one and re-run scan.",
            [],
        )

    changes: list[FileChange] = []
    for package, target in entry.target_versions.items():
        needs_change, from_version = stale_pin(base_constraints.text, package, target)
        if needs_change:
            changes.append(PinChange(path=constraints_path, package=package, from_version=from_version, to_version=target))
    if changes:
        rationale += f" {constraints_path} is the full constraints file from {base_constraints.source}, with these pins patched in."
        if constraints_path == DATADOG_CONSTRAINTS_PATH:
            rationale += (
                f" {CONSTRAINTS_PATH} already exists but isn't referenced by requirements.txt, so the patched "
                f"constraints are written to {DATADOG_CONSTRAINTS_PATH.removeprefix('dags/')} instead of overwriting it."
            )
        # a --constraint already under the dags mount is the file being patched in place
        if resolve_constraint_s3_key(find_constraint_path(requirements_text) or "", "dags") is None:
            changes.append(
                ConstraintDirectiveChange(path=REQUIREMENTS_PATH, from_line=constraint_lines[0] if constraint_lines else None, to_line=constraint_line_for(constraints_path))
            )
    for package, target in entry.target_versions.items():
        if package in entry.wheel_only_packages:
            filename = datadog_wheel_filename(package, target)
            # a reference line whose object is missing still gets one, so apply uploads it
            if wheel_identity(filename) not in {wheel_identity(f) for f in present_wheel_files}:
                changes.append(
                    WheelReference(
                        path=REQUIREMENTS_PATH,
                        package=package,
                        version=target,
                        wheel_url=f"{DATADOG_WHEEL_BASE_URL}{filename}",
                        line=f"{DAGS_MOUNT_PREFIX}{filename}",
                    )
                )
        else:
            needs_change, from_version = stale_pin(requirements_text, package, target)
            if needs_change:
                changes.append(PinChange(path=REQUIREMENTS_PATH, package=package, from_version=from_version, to_version=target))
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


def _plan_env_var_changes(airflow_version: str, dd_site: str, startup_script_text: Optional[str], state: OpenLineageState) -> list[EnvVarChange]:
    """Diff startup.sh variable-by-variable against the *effective* configuration (openlineage_config.py).

    OPENLINEAGE_URL/OPENLINEAGE_API_KEY are only proposed when setting them
    would actually make the transport resolve to the intake -- never when it
    already does, when something higher-precedence wins anyway, or when it
    can't be told statically. An API key that's already set to anything (a
    secret lookup, another variable) is left alone: there's nothing real to
    compare it against, and proposing to overwrite a customer's working key
    on every scan would be worse than occasionally missing a wrong one. The
    namespace is left alone whenever it's non-empty, since it's the
    customer's `env` identity (see startup_script.py), and the 2.7/2.8
    workaround variables whenever they're defined at all (a non-empty
    CONFIG_PATH is a config file, not something to blank out).
    """
    environment = state.environment
    written = parse_exports(startup_script_text or "")
    changes = []
    for name, to_value in target_values(airflow_version, dd_site):
        if name == "OPENLINEAGE_URL":
            skip = not state.transport_fixable or is_intake_url(environment.get(name), dd_site)
        elif name == "OPENLINEAGE_API_KEY":
            skip = not state.transport_fixable or is_set(environment, name)
        elif name in KEEP_EXISTING_VAR_NAMES:
            skip = is_set(environment, name)
        else:
            skip = name in environment
        if not skip:
            changes.append(
                EnvVarChange(path=STARTUP_SCRIPT_PATH, name=name, from_value=written.get(name), to_value=to_value, secret=name in SECRET_VAR_NAMES)
            )
    return changes


def compute_plan(
    airflow_version: str,
    requirements_text: str,
    base_constraints: Optional[BaseConstraints],
    startup_script_text: Optional[str],
    dd_site: str,
    present_wheel_files: frozenset[str] = frozenset(),
    constraints_path: str = CONSTRAINTS_PATH,
    requirements_path: str = REQUIREMENTS_PATH,
    startup_script_path: str = STARTUP_SCRIPT_PATH,
    configuration_options: Optional[dict] = None,
) -> Plan:
    """Compute the onboarding plan for one environment from its real current files.

    base_constraints, present_wheel_files and constraints_path are only
    consulted for flagged versions (see ProbeContext). requirements_path/
    startup_script_path are the labels of the files written (see ProbeContext).
    configuration_options is the environment's AirflowConfigurationOptions,
    which count the same as startup.sh exports (openlineage_config.py).
    """
    flagged_entry = FLAGGED_VERSION_TABLE.get(airflow_version)
    if flagged_entry:
        upgrade_needed, rationale, file_changes = _plan_flagged_version(flagged_entry, requirements_text, base_constraints, present_wheel_files, constraints_path)
        source = "flagged_version_table"
    else:
        upgrade_needed, rationale, file_changes = _plan_unflagged_version(airflow_version, requirements_text)
        source = "unflagged_version"

    effective_constraints = base_constraints.text if base_constraints else None
    state = analyze(airflow_version, requirements_text, startup_script_text, configuration_options or {}, dd_site, effective_constraints)
    file_changes += _plan_env_var_changes(airflow_version, dd_site, startup_script_text, state)

    relabel = {REQUIREMENTS_PATH: requirements_path, STARTUP_SCRIPT_PATH: startup_script_path}
    file_changes = [replace(fc, path=relabel.get(fc.path, fc.path)) for fc in file_changes]
    for default, datadog in ((REQUIREMENTS_PATH, DATADOG_REQUIREMENTS_PATH), (STARTUP_SCRIPT_PATH, DATADOG_STARTUP_SCRIPT_PATH)):
        if datadog in (requirements_path, startup_script_path) and any(fc.path == datadog for fc in file_changes):
            rationale += (
                f" {default} already exists but the environment isn't configured to use it, so the plan writes "
                f"{datadog.removeprefix('dags/')} instead of overwriting it."
            )

    return Plan(
        upgrade_needed=upgrade_needed,
        rationale=rationale,
        source=source,
        matched_table_entry=flagged_entry,
        source_doc=SOURCE_DOC,
        file_changes=file_changes,
    )
