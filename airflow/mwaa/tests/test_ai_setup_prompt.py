# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""AI_SETUP_PROMPT.md encodes the same rules as the CLI; these fail when version_table.py moves without it."""

import re
from pathlib import Path

import pytest

from mwaa.base_constraints import MINIMAL_CONSTRAINTS_HEADER
from mwaa.startup_script import VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND, target_values
from mwaa.version_table import (
    DATADOG_WHEEL_BASE_URL,
    FLAGGED_VERSION_TABLE,
    PYTHON_VERSION_BY_AIRFLOW_VERSION,
    UPSTREAM_CONSTRAINTS_URL,
    datadog_wheel_filename,
)

PROMPT = (Path(__file__).parent.parent / "AI_SETUP_PROMPT.md").read_text()
ENTRIES = list(FLAGGED_VERSION_TABLE.values())


def version_section(airflow_version: str) -> str:
    """The prompt's target-pins bullet for one version, up to the next version's."""
    start = PROMPT.index(f"- **{airflow_version}:**")
    following = [PROMPT.find("- **", start + 1), PROMPT.find("\nEvery other Airflow version", start)]
    return PROMPT[start : min(i for i in following if i != -1)]


@pytest.mark.parametrize("entry", ENTRIES, ids=[e.airflow_version for e in ENTRIES])
def test_the_prompt_has_every_target_pin_and_constraint_bump(entry):
    section = version_section(entry.airflow_version)
    for package, version in entry.target_versions.items():
        assert f"`{package}=={version}`" in section
    for package, (minimum, needed_by) in entry.constraint_bumps.items():
        assert f"`{package}=={minimum}`" in section
        assert f"{needed_by} {entry.target_versions[needed_by]} needs {package}>={minimum}" in section
    if not entry.constraint_bumps:
        assert "No constraint bumps." in section


@pytest.mark.parametrize("entry", ENTRIES, ids=[e.airflow_version for e in ENTRIES])
def test_the_prompt_has_each_versions_python_default_pin_and_forcing_behavior(entry):
    row = next(line for line in PROMPT.splitlines() if line.startswith(f"| {entry.airflow_version} |"))
    assert f"| {PYTHON_VERSION_BY_AIRFLOW_VERSION[entry.airflow_version]} |" in row
    assert f"`apache-airflow-providers-openlineage=={entry.default_versions['apache-airflow-providers-openlineage']}`" in row
    assert f"{entry.airflow_version}: mwaa_forces_upstream_constraints = {str(entry.mwaa_forces_upstream_constraints).lower()}" in row
    if entry.mwaa_forces_upstream_constraints:
        url = UPSTREAM_CONSTRAINTS_URL.format(airflow_version=entry.airflow_version, python_version=PYTHON_VERSION_BY_AIRFLOW_VERSION[entry.airflow_version])
        assert url in PROMPT


def test_the_prompt_has_every_wheel_and_the_minimal_file():
    for entry in ENTRIES:
        for package in entry.wheel_only_packages:
            assert f"{DATADOG_WHEEL_BASE_URL}{datadog_wheel_filename(package, entry.target_versions[package])}" in PROMPT
    minimal = [e for e in ENTRIES if not e.mwaa_forces_upstream_constraints]
    for entry in minimal:
        template = MINIMAL_CONSTRAINTS_HEADER + "".join(f"{package}=={version}\n" for package, version in entry.target_versions.items())
        assert template in PROMPT


def test_the_prompt_has_the_startup_script_targets():
    for name, _ in target_values(sorted(VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND)[0], "{{DD_SITE}}"):
        assert name in PROMPT
    assert "export OPENLINEAGE_URL=https://data-obs-intake.{{DD_SITE}}" in PROMPT
    assert 'export AIRFLOW__OPENLINEAGE__NAMESPACE="${AIRFLOW_ENV_NAME}"' in PROMPT
    assert f"# Airflow {' and '.join(sorted(VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND))} only:" in PROMPT


def test_the_prompt_only_uses_the_two_placeholders_the_ui_substitutes():
    assert set(re.findall(r"\{\{[^}]*\}\}", PROMPT)) == {"{{DD_SITE}}", "{{MWAA_PYZ_URL}}"}


def test_the_prompt_carries_no_key_or_account_id():
    assert not re.search(r"\b[0-9a-fA-F]{32}\b", PROMPT)
    assert not re.search(r"\b\d{12}\b", PROMPT)
