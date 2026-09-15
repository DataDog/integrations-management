# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json

from mwaa.checks import ProbeContext
from mwaa.payload import build_payload

ENVIRONMENT = {"Name": "my-mwaa-prod", "AirflowVersion": "2.8.1"}


def make_context() -> ProbeContext:
    return ProbeContext(
        environment=ENVIRONMENT,
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.4.0\n",
        startup_script_text=None,
        client=None,
    )


def test_build_payload_has_session_and_region():
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [make_context()])
    assert payload["session_id"] == "session-1"
    assert payload["region"] == "us-east-1"
    assert "created_at" in payload
    assert len(payload["environments"]) == 1


def test_build_payload_environment_entry_includes_plan_but_no_raw_file_content():
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [make_context()])
    entry = payload["environments"][0]

    assert entry["name"] == "my-mwaa-prod"
    assert entry["airflow_version"] == "2.8.1"
    assert entry["already_configured"] is False
    assert entry["plan"]["upgrade_needed"] is True
    assert entry["plan"]["source"] == "flagged_version_table"
    assert "current_state" not in entry


def test_build_payload_never_carries_startup_script_content_even_with_a_live_looking_secret():
    # Regression: a real scan surfaced a live Datadog API key inside a startup
    # script. The payload must never include that text at all, not even redacted.
    ctx = ProbeContext(
        environment=ENVIRONMENT,
        requirements_text="",
        constraints_text=None,
        startup_script_text="export OPENLINEAGE_API_KEY=not-a-real-key-but-pretend-it-is\n",
        client=None,
    )
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [ctx])
    serialized = json.dumps(payload)

    # The variable NAME can legitimately appear -- it's in our own generated
    # startup.sh template, always with the <DD_API_KEY> placeholder, never a
    # real value. Only the real value from the environment's actual file must
    # never appear.
    assert "not-a-real-key-but-pretend-it-is" not in serialized


def test_build_payload_plan_still_reflects_startup_script_state():
    ctx = ProbeContext(
        environment={"Name": "env", "AirflowVersion": "3.0.6"},
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text=None,
        startup_script_text="export OPENLINEAGE_API_KEY=secretvalue\nexport OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        client=None,
    )
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [ctx])
    entry = payload["environments"][0]

    assert entry["already_configured"] is True
    assert entry["plan"]["upgrade_needed"] is False


def test_build_payload_is_json_serializable():
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [make_context()])
    # Should not raise -- this is what main.py actually does with it.
    json.dumps(payload)
