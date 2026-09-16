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
"""

from dataclasses import dataclass, field
from typing import Optional

from .pins import OPENLINEAGE_PACKAGES, find_constraint_path, parse_bare_packages, parse_pins, resolve_constraint_s3_key
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


def plan_from_dict(data: dict) -> Plan:
    """The reverse of dataclasses.asdict(plan) -- reconstructs real Plan/FileChange/PinDiff/
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
        file_changes=[
            FileChange(
                path=fc["path"],
                action=fc["action"],
                pin_diff=[PinDiff(**pd) for pd in fc.get("pin_diff", [])],
                content=fc.get("content"),
                notes=fc.get("notes", []),
            )
            for fc in data["file_changes"]
        ],
    )


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


def _plan_unflagged_version(airflow_version: str, mentioned_packages: set) -> tuple[bool, str, list[PinDiff]]:
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
        [PinDiff("apache-airflow-providers-openlineage", None, "unpinned (resolved by MWAA's current default constraints)")],
    )


def compute_plan(
    airflow_version: str,
    requirements_text: str,
    constraints_text: Optional[str],
    startup_script_text: Optional[str],
    dd_site: str,
    dd_api_key: str,
    environment_name: str,
) -> Plan:
    """Compute the onboarding plan for one environment from its real current files."""
    current_req_pins = parse_pins(requirements_text)
    current_con_pins = parse_pins(constraints_text or "")

    flagged_entry = FLAGGED_VERSION_TABLE.get(airflow_version)
    if flagged_entry:
        upgrade_needed, rationale, pin_diffs = _plan_flagged_version(flagged_entry, current_req_pins, current_con_pins)
        source = "flagged_version_table"
    else:
        mentioned_packages = set(current_req_pins) | parse_bare_packages(requirements_text)
        upgrade_needed, rationale, pin_diffs = _plan_unflagged_version(airflow_version, mentioned_packages)
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
                content=render_startup_script(airflow_version, dd_site, dd_api_key, environment_name),
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
