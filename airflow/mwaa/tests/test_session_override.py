# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from dataclasses import asdict

from mwaa.plan import EnvVarChange, PinChange, Plan
from mwaa.session import EnvironmentEntry, Session
from mwaa.session_override import load_session_override
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER
from mwaa.version_table import FLAGGED_VERSION_TABLE


def _write(tmp_path, session: Session):
    path = tmp_path / "override.json"
    path.write_text(json.dumps(asdict(session)))
    return str(path)


def test_round_trips_a_session_with_no_matched_table_entry(tmp_path):
    session = Session(
        session_id="session-1",
        region="us-east-1",
        environments=[
            EnvironmentEntry(
                name="my-env",
                airflow_version="3.0.6",
                already_configured=False,
                plan=Plan(
                    upgrade_needed=True,
                    rationale="needs the provider added",
                    source="unflagged_version",
                    matched_table_entry=None,
                    source_doc="",
                    file_changes=[
                        PinChange(
                            path="requirements.txt",
                            package="apache-airflow-providers-openlineage",
                            from_version=None,
                            to_version="unpinned (resolved by MWAA's current default constraints)",
                        )
                    ],
                ),
            )
        ],
    )

    loaded = load_session_override(_write(tmp_path, session))

    assert loaded == session


def test_round_trips_a_session_with_a_matched_table_entry(tmp_path):
    entry = FLAGGED_VERSION_TABLE["2.8.1"]
    session = Session(
        session_id="session-1",
        region="us-east-1",
        environments=[
            EnvironmentEntry(
                name="my-env",
                airflow_version="2.8.1",
                already_configured=False,
                plan=Plan(
                    upgrade_needed=True,
                    rationale="flagged version",
                    source="flagged_version_table",
                    matched_table_entry=entry,
                    source_doc="https://example.invalid",
                    file_changes=[
                        PinChange(path="dags/constraints.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0"),
                        EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_URL", from_value=None, to_value="https://data-obs-intake.datadoghq.com", secret=False),
                        EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_API_KEY", from_value=None, to_value=DD_API_KEY_PLACEHOLDER, secret=True),
                    ],
                ),
            )
        ],
    )

    loaded = load_session_override(_write(tmp_path, session))

    loaded_plan = loaded.environments[0].plan
    original_plan = session.environments[0].plan
    assert loaded_plan.matched_table_entry.airflow_version == entry.airflow_version
    assert loaded_plan.matched_table_entry.target_versions == entry.target_versions
    assert loaded_plan.file_changes[1].to_value == original_plan.file_changes[1].to_value
    assert loaded_plan.file_changes[0].from_version == original_plan.file_changes[0].from_version
