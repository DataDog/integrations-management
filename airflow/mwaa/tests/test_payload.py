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


def test_build_payload_environment_entry_includes_plan_and_current_state():
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [make_context()])
    entry = payload["environments"][0]

    assert entry["name"] == "my-mwaa-prod"
    assert entry["airflow_version"] == "2.8.1"
    assert entry["already_configured"] is False
    assert entry["current_state"]["requirements_text"] == "apache-airflow-providers-openlineage==1.4.0\n"
    assert entry["plan"]["upgrade_needed"] is True
    assert entry["plan"]["source"] == "flagged_version_table"


def test_build_payload_is_json_serializable():
    payload = build_payload("session-1", "us-east-1", "datadoghq.com", [make_context()])
    # Should not raise -- this is what main.py actually does with it.
    json.dumps(payload)
