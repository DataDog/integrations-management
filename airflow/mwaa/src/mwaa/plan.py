# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Computes the OpenLineage onboarding plan for one MWAA environment.

This is the client-side equivalent of the "Review proposed changes" screen in
the Configure Airflow UI: given an environment's real current requirements.txt/
constraints.txt/startup script, decide what needs to change and why. The
"why" (rationale, source, matched_table_entry) is carried alongside the diff
itself so a persisted payload is enough to reconstruct the reasoning later,
without needing to re-run this code against the version table as it existed
at the time.
"""

from dataclasses import dataclass, field
from typing import Optional

from .pins import OPENLINEAGE_PACKAGES, find_constraint_path, parse_pins, resolve_constraint_s3_key
from .startup_script import render_startup_script, startup_script_looks_configured
from .version_table import FLAGGED_VERSION_TABLE, SOURCE_DOC, FlaggedVersionEntry

REQUIREMENTS_PATH = "requirements.txt"
CONSTRAINTS_PATH = "dags/constraints.txt"
STARTUP_SCRIPT_PATH = "dags/startup.sh"
EXPECTED_CONSTRAINT_LINE_TARGET = "/usr/local/airflow/dags/constraints.txt"


@dataclass(frozen=True)
class PinDiff:
    """One package's version change (or unpinned addition)."""

    package: str
    from_version: Optional[str]
    to_version: str


@dataclass(frozen=True)
class FileChange:
    """One file this plan proposes creating or updating."""

    path: str
    action: str  # "create" | "update"
    pin_diff: list[PinDiff] = field(default_factory=list)
    content: Optional[str] = None  # full new content, for startup.sh
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    """The full onboarding plan for one environment."""

    upgrade_needed: bool
    rationale: str
    source: str  # "flagged_version_table" | "unflagged_version"
    matched_table_entry: Optional[FlaggedVersionEntry]
    source_doc: str
    file_changes: list[FileChange]


@dataclass(frozen=True)
class PlanBundle:
    """Everything one `apply` run needs: which environment, which region, and the plan.

    This is the general "ready to apply" shape, not something specific to
    plan_override.py's local-file loading. `apply` normally builds one itself
    by computing a Plan and pairing it with the config it was already given.
    plan_override.py is just today's one OTHER way to obtain a PlanBundle --
    reading one whole, already-computed, from local disk instead of computing
    it from a freshly-fetched environment. A future backend that hands back a
    plan for a given session id would produce this exact same shape, over a
    different transport -- not a special case of its own.
    """

    environment_name: str
    region: str
    dd_site: str
    plan: Plan


def _plan_flagged_version(entry: FlaggedVersionEntry, current_req_pins: dict, current_con_pins: dict) -> tuple[bool, str, list[PinDiff]]:
    pin_diffs = [
        PinDiff(package, current_con_pins.get(package) or current_req_pins.get(package), target)
        for package, target in entry.target_versions.items()
        if (current_con_pins.get(package) or current_req_pins.get(package)) != target
    ]
    default_ol_version = entry.default_versions.get("apache-airflow-providers-openlineage", "an old version")
    rationale = (
        f"Airflow {entry.airflow_version} is flagged by Datadog's MWAA upgrade guide: its MWAA-default "
        f"constraints pin apache-airflow-providers-openlineage {default_ol_version}, which has known "
        "reliability/compatibility issues."
    )
    return bool(pin_diffs), rationale, pin_diffs


def _plan_unflagged_version(airflow_version: str, current_req_pins: dict) -> tuple[bool, str, list[PinDiff]]:
    if any(pkg in current_req_pins for pkg in OPENLINEAGE_PACKAGES):
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
        [PinDiff("apache-airflow-providers-openlineage", None, "unpinned (resolved by MWAA's current default constraints)")],
    )


def compute_plan(
    airflow_version: str,
    requirements_text: str,
    constraints_text: Optional[str],
    startup_script_text: Optional[str],
    dd_site: str,
) -> Plan:
    """Compute the onboarding plan for one environment from its real current files."""
    current_req_pins = parse_pins(requirements_text)
    current_con_pins = parse_pins(constraints_text or "")

    flagged_entry = FLAGGED_VERSION_TABLE.get(airflow_version)
    if flagged_entry:
        upgrade_needed, rationale, pin_diffs = _plan_flagged_version(flagged_entry, current_req_pins, current_con_pins)
        source = "flagged_version_table"
    else:
        upgrade_needed, rationale, pin_diffs = _plan_unflagged_version(airflow_version, current_req_pins)
        flagged_entry = None
        source = "unflagged_version"

    file_changes: list[FileChange] = []

    if pin_diffs:
        if flagged_entry:
            file_changes.append(
                FileChange(
                    path=CONSTRAINTS_PATH,
                    action="update" if constraints_text else "create",
                    pin_diff=pin_diffs,
                )
            )

        req_notes = []
        existing_constraint_path = find_constraint_path(requirements_text)
        if flagged_entry and resolve_constraint_s3_key(existing_constraint_path or "", "dags") != CONSTRAINTS_PATH:
            req_notes.append(f'adds `--constraint "{EXPECTED_CONSTRAINT_LINE_TARGET}"`')
        file_changes.append(
            FileChange(
                path=REQUIREMENTS_PATH,
                action="update",
                pin_diff=pin_diffs,
                notes=req_notes,
            )
        )

    if not startup_script_looks_configured(startup_script_text):
        file_changes.append(
            FileChange(
                path=STARTUP_SCRIPT_PATH,
                action="update" if startup_script_text else "create",
                content=render_startup_script(airflow_version, dd_site),
                notes=["sets the OpenLineage transport variables that point Airflow at Datadog"],
            )
        )

    return Plan(
        upgrade_needed=upgrade_needed,
        rationale=rationale,
        source=source,
        matched_table_entry=flagged_entry,
        source_doc=SOURCE_DOC,
        file_changes=file_changes,
    )
