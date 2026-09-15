# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from dataclasses import asdict

from mwaa.plan import FileChange, Plan, PinDiff
from mwaa.plan_override import load_plan_override
from mwaa.version_table import FLAGGED_VERSION_TABLE


def _write(tmp_path, environment_name: str, region: str, plan: Plan, dd_site: "str | None" = None):
    data = {"environment_name": environment_name, "region": region, "plan": asdict(plan)}
    if dd_site is not None:
        data["dd_site"] = dd_site
    path = tmp_path / "override.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_round_trips_environment_name_region_and_plan(tmp_path):
    plan = Plan(
        upgrade_needed=True,
        rationale="needs the provider added",
        source="unflagged_version",
        matched_table_entry=None,
        source_doc="",
        file_changes=[
            FileChange(
                path="requirements.txt",
                action="update",
                pin_diff=[PinDiff("apache-airflow-providers-openlineage", None, "unpinned (resolved by MWAA's current default constraints)")],
            )
        ],
    )

    override = load_plan_override(_write(tmp_path, "my-mwaa-environment", "us-east-1", plan, dd_site="datad0g.com"))

    assert override.environment_name == "my-mwaa-environment"
    assert override.region == "us-east-1"
    assert override.dd_site == "datad0g.com"
    assert override.plan == plan


def test_dd_site_defaults_when_omitted(tmp_path):
    plan = Plan(
        upgrade_needed=False,
        rationale="already configured",
        source="unflagged_version",
        matched_table_entry=None,
        source_doc="",
        file_changes=[],
    )

    override = load_plan_override(_write(tmp_path, "my-env", "us-east-1", plan))

    assert override.dd_site == "datadoghq.com"


def test_round_trips_a_plan_with_a_matched_table_entry(tmp_path):
    entry = FLAGGED_VERSION_TABLE["2.8.1"]
    plan = Plan(
        upgrade_needed=True,
        rationale="flagged version",
        source="flagged_version_table",
        matched_table_entry=entry,
        source_doc="https://example.invalid",
        file_changes=[
            FileChange(
                path="dags/constraints.txt",
                action="update",
                pin_diff=[PinDiff("apache-airflow-providers-openlineage", "1.4.0", "1.14.0")],
            ),
            FileChange(
                path="dags/startup.sh",
                action="create",
                content="#!/bin/sh\nexport OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
                notes=["sets the OpenLineage transport variables"],
            ),
        ],
    )

    override = load_plan_override(_write(tmp_path, "my-env", "us-east-1", plan))

    assert override.plan.matched_table_entry.airflow_version == entry.airflow_version
    assert override.plan.matched_table_entry.target_versions == entry.target_versions
    assert override.plan.file_changes[1].content == plan.file_changes[1].content
    assert override.plan.file_changes[0].pin_diff == plan.file_changes[0].pin_diff
