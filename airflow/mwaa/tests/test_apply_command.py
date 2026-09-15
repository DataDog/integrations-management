# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

from airflow_shared.reporter import Reporter
from mwaa.apply_config import ApplyConfig
from mwaa.apply_command import run_apply

ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": None,
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.get_environment.return_value = ENVIRONMENT
    client.get_object_text.return_value = "apache-airflow-providers-openlineage==1.4.0\n"
    client.put_object_text.return_value = "v2"
    return client


def test_run_apply_without_yes_does_not_call_put_object(capsys):
    config = ApplyConfig(environment_name="my-env", region="us-east-1", dd_site="datadoghq.com", confirmed=False)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.apply_command.MwaaClient", return_value=client):
        result = run_apply(config, reporter)

    client.put_object_text.assert_not_called()
    client.update_environment.assert_not_called()
    assert result["applied"] is False
    assert "Dry run only" in capsys.readouterr().out


def test_run_apply_with_yes_uploads_files(capsys):
    config = ApplyConfig(environment_name="my-env", region="us-east-1", dd_site="datadoghq.com", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()

    with patch("mwaa.apply_command.MwaaClient", return_value=client):
        result = run_apply(config, reporter)

    assert client.put_object_text.call_count == len(result["uploads"])
    client.update_environment.assert_called_once()
    assert result["applied"] is True
    assert "UpdateEnvironment called" in capsys.readouterr().out


def test_run_apply_reports_nothing_to_do_when_already_configured(capsys):
    config = ApplyConfig(environment_name="my-env", region="us-east-1", dd_site="datadoghq.com", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    already_configured_env = {**ENVIRONMENT, "StartupScriptS3Path": "dags/startup.sh"}
    client.get_environment.return_value = already_configured_env
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": (
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        "dags/constraints.txt": (
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        "dags/startup.sh": "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
    }[key]

    with patch("mwaa.apply_command.MwaaClient", return_value=client):
        result = run_apply(config, reporter)

    assert result["applied"] is False
    assert result["uploads"] == []
    client.put_object_text.assert_not_called()
    assert "already fully configured" in capsys.readouterr().out
