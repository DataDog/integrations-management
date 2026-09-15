# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

from airflow_shared.reporter import Reporter
from mwaa.scan import run_scan
from mwaa.scan_config import ScanConfig

ENVIRONMENT = {
    "Name": "my-mwaa-prod",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": None,
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.list_environment_names.return_value = ["my-mwaa-prod"]
    client.get_environment.return_value = ENVIRONMENT
    client.get_object_text.return_value = "apache-airflow-providers-openlineage==1.4.0\n"
    return client


def test_run_scan_returns_payload_with_one_environment(capsys):
    config = ScanConfig(region="us-east-1", dd_site="datadoghq.com")
    reporter = Reporter(workflow_type="mwaa-setup")

    with patch("mwaa.scan.MwaaClient", return_value=make_client()):
        payload = run_scan(config, reporter)

    assert payload["region"] == "us-east-1"
    assert len(payload["environments"]) == 1
    assert payload["environments"][0]["name"] == "my-mwaa-prod"

    out = capsys.readouterr().out
    assert "Session ID:" in out
    assert "Found 1 MWAA environment(s)" in out
