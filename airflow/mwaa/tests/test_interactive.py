# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

from airflow_shared.reporter import Reporter
from mwaa.interactive import run_interactive
from mwaa.scan_config import ScanConfig

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


def test_run_interactive_lists_environments_with_status(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")

    with patch("mwaa.interactive.MwaaClient", return_value=make_client()):
        run_interactive(config, reporter, input_func=fake_input("q"))

    out = capsys.readouterr().out
    assert "my-mwaa-prod" in out
    assert "OpenLineage upgrade needed" in out
    assert "my-mwaa-staging" in out
    assert "already configured" in out


def test_run_interactive_quit_makes_no_changes():
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input("q"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False


def test_run_interactive_selects_already_configured_environment_and_stops(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input("2"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False
    assert "already fully configured" in capsys.readouterr().out


def test_run_interactive_declining_apply_makes_no_changes():
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input("1", "n"))

    client.put_object_text.assert_not_called()
    assert result["applied"] is False


def test_run_interactive_dry_run_never_prompts_to_apply_or_uploads(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com", dry_run=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    # Only "1" (environment selection) is provided -- if the code tried to
    # prompt for apply confirmation too, this would raise StopIteration.
    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input("1"))

    client.put_object_text.assert_not_called()
    client.update_environment.assert_not_called()
    assert result["applied"] is False
    assert "Dry run (--dry-run)" in capsys.readouterr().out


def test_run_interactive_confirming_apply_uploads_and_updates(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input("1", "y"))

    assert result["applied"] is True
    client.update_environment.assert_called_once()
    out = capsys.readouterr().out
    assert "UpdateEnvironment called" in out
    assert "This CLI does not trigger a DAG run for you" in out


def test_run_interactive_no_environments_found(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    client.list_environment_names.return_value = []

    with patch("mwaa.interactive.MwaaClient", return_value=client):
        result = run_interactive(config, reporter, input_func=fake_input())

    assert result["applied"] is False
    assert "No MWAA environments found" in capsys.readouterr().out
