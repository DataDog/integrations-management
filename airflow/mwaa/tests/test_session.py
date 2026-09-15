# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import asdict

from mwaa.checks import ProbeContext
from mwaa.session import build_session, session_from_dict

ENVIRONMENT = {"Name": "my-mwaa-prod", "AirflowVersion": "2.8.1", "SourceBucketArn": "arn:aws:s3:::my-bucket"}


def make_context(**overrides) -> ProbeContext:
    defaults = {
        "environment": ENVIRONMENT,
        "requirements_text": "apache-airflow-providers-openlineage==1.4.0\n",
        "constraints_text": "apache-airflow-providers-openlineage==1.4.0\n",
        "startup_script_text": None,
        "client": None,
    }
    defaults.update(overrides)
    return ProbeContext(**defaults)


def test_build_session_computes_a_plan_per_environment():
    session = build_session("session-1", "us-east-1", "datadoghq.com", [make_context()])

    assert session.session_id == "session-1"
    assert session.region == "us-east-1"
    assert len(session.environments) == 1
    entry = session.environments[0]
    assert entry.name == "my-mwaa-prod"
    assert entry.airflow_version == "2.8.1"
    assert entry.plan.upgrade_needed is True


def test_session_find_returns_matching_entry():
    session = build_session("session-1", "us-east-1", "datadoghq.com", [make_context()])

    assert session.find("my-mwaa-prod") is not None
    assert session.find("does-not-exist") is None


def test_session_never_carries_raw_startup_script_content():
    ctx = make_context(startup_script_text="export OPENLINEAGE_API_KEY=00000000000000000000000000000000\n")
    session = build_session("session-1", "us-east-1", "datadoghq.com", [ctx])

    serialized = str(asdict(session))
    assert "00000000000000000000000000000000" not in serialized


def test_session_round_trips_through_asdict_and_session_from_dict():
    # Unflagged Airflow version so matched_table_entry stays None -- a flagged
    # version's FlaggedVersionEntry.wheel_only_packages round-trips as a list
    # (asdict turns the tuple into one), which would fail a strict == here
    # even though the content is identical. See test_plan.py for that shape.
    ctx = make_context(environment={**ENVIRONMENT, "AirflowVersion": "3.0.6"})
    session = build_session("session-1", "us-east-1", "datadoghq.com", [ctx])

    loaded = session_from_dict(asdict(session))

    assert loaded == session
