# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import uuid
from unittest.mock import MagicMock, patch

from airflow_shared.reporter import Reporter
from mwaa.scan import run_scan
from mwaa.scan_config import ScanConfig
from mwaa.session_store import load_session

SESSION_ID = str(uuid.uuid4())

ENVIRONMENT_NEEDS_UPGRADE = {
    "Name": "my-mwaa-prod",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": None,
}

ENVIRONMENT_ALREADY_CONFIGURED = {
    "Name": "my-mwaa-staging",
    "AirflowVersion": "3.0.6",
    "SourceBucketArn": "arn:aws:s3:::my-bucket-2",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": "dags/startup.sh",
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.list_environment_names.return_value = ["my-mwaa-prod", "my-mwaa-staging"]
    client.get_environment.side_effect = lambda name: {
        "my-mwaa-prod": ENVIRONMENT_NEEDS_UPGRADE,
        "my-mwaa-staging": ENVIRONMENT_ALREADY_CONFIGURED,
    }[name]
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        ("my-bucket", "requirements.txt"): "apache-airflow-providers-openlineage==1.4.0\n",
        ("my-bucket-2", "requirements.txt"): "apache-airflow-providers-openlineage==2.18.0\n",
        ("my-bucket-2", "dags/startup.sh"): "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
    }[(bucket, key)]
    client.put_object_text.return_value = "v2"
    return client


def fake_input(*responses: str):
    it = iter(responses)
    return lambda _prompt: next(it)


def test_run_scan_persists_a_session_with_one_entry_per_environment():
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")

    with patch("mwaa.scan.MwaaClient", return_value=make_client()):
        result = run_scan(config, reporter)

    session = result["session"]
    assert session.session_id == SESSION_ID
    assert session.region == "us-east-1"
    assert {e.name for e in session.environments} == {"my-mwaa-prod", "my-mwaa-staging"}

    persisted = load_session(SESSION_ID)
    # Not a strict == : a flagged environment's FlaggedVersionEntry.wheel_only_packages
    # round-trips as a list (asdict turns the tuple into one) -- see test_session.py.
    assert persisted.session_id == session.session_id
    assert persisted.region == session.region
    assert [e.name for e in persisted.environments] == [e.name for e in session.environments]


def test_run_scan_without_interactive_prints_ui_link_and_does_not_prompt(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")

    with patch("mwaa.scan.MwaaClient", return_value=make_client()):
        result = run_scan(config, reporter, input_func=fake_input())  # would raise StopIteration if prompted

    assert result["applied"] is False
    out = capsys.readouterr().out
    assert SESSION_ID in out
    assert "Configure Airflow UI" in out


def test_run_scan_interactive_lists_environments_with_status(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")

    with patch("mwaa.scan.MwaaClient", return_value=make_client()):
        run_scan(config, reporter, input_func=fake_input("q"))

    out = capsys.readouterr().out
    assert "my-mwaa-prod" in out
    assert "OpenLineage upgrade needed" in out
    assert "my-mwaa-staging" in out
    assert "already configured" in out


def test_run_scan_interactive_quit_makes_no_changes():
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input("q"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False


def test_run_scan_interactive_selects_already_configured_environment_and_stops(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input("2"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False
    assert "already fully configured" in capsys.readouterr().out


def test_run_scan_interactive_declining_apply_prints_apply_command(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input("1", "n"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False
    out = capsys.readouterr().out
    assert f"apply --session-id {SESSION_ID} --name my-mwaa-prod --region us-east-1 --yes" in out


def test_run_scan_interactive_dry_run_never_prompts_to_apply_or_uploads(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True, dry_run=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    # Only "1" (environment selection) is provided -- if the code tried to
    # prompt for apply confirmation too, this would raise StopIteration.
    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input("1"))

    client.put_object_text.assert_not_called()
    client.update_environment.assert_not_called()
    assert result["applied"] is False
    assert "Dry run (--dry-run)" in capsys.readouterr().out


def test_run_scan_interactive_confirming_apply_uploads_and_updates(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input("1", "y"))

    assert result["applied"] is True
    client.update_environment.assert_called_once()
    out = capsys.readouterr().out
    assert "UpdateEnvironment called" in out
    assert "This CLI does not trigger a DAG run for you" in out


def test_run_scan_interactive_no_environments_found(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", interactive=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    client.list_environment_names.return_value = []

    with patch("mwaa.scan.MwaaClient", return_value=client):
        result = run_scan(config, reporter, input_func=fake_input())

    assert result["applied"] is False
    assert "No MWAA environments found" in capsys.readouterr().out
