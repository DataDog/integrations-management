# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from airflow_shared.mwaa_client import ObjectNotFoundError
from mwaa.probe import build_context

ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "RequirementsS3ObjectVersion": "v1",
    "StartupScriptS3Path": "startup/mwaa-startup.sh",
    "StartupScriptS3ObjectVersion": "v1",
    "ExecutionRoleArn": "arn:aws:iam::123456789012:role/my-execution-role",
    "AirflowConfigurationOptions": {},
    "NetworkConfiguration": {"SubnetIds": ["subnet-1"]},
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.get_environment.return_value = ENVIRONMENT
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": (
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            "apache-airflow-providers-openlineage==2.18.0\n"
        ),
        "dags/constraints.txt": "apache-airflow-providers-openlineage==2.18.0\n",
        "startup/mwaa-startup.sh": "",
    }[key]
    client.object_exists.return_value = True
    client.simulate_s3_read_access.return_value = {"s3:GetObject": True, "s3:ListBucket": True}
    return client


def test_build_context_fetches_requirements_and_constraints():
    client = make_client()

    ctx = build_context(client, "my-env")

    assert ctx.environment == ENVIRONMENT
    assert "openlineage" in ctx.requirements_text
    assert ctx.constraints_text == "apache-airflow-providers-openlineage==2.18.0\n"


def test_build_context_tolerates_missing_constraints_object():
    client = make_client()

    def get_object_text(bucket, key, version_id=None):
        if key == "dags/constraints.txt":
            raise ObjectNotFoundError(key)
        return {
            "requirements.txt": '--constraint "/usr/local/airflow/dags/constraints.txt"\n',
            "startup/mwaa-startup.sh": "",
        }[key]

    client.get_object_text.side_effect = get_object_text

    ctx = build_context(client, "my-env")

    assert ctx.constraints_text is None


def test_build_context_tolerates_environment_with_no_requirements_configured():
    client = make_client()
    environment_without_requirements = {k: v for k, v in ENVIRONMENT.items() if k != "RequirementsS3Path"}
    client.get_environment.return_value = environment_without_requirements

    ctx = build_context(client, "my-env")

    assert ctx.requirements_text == ""
    assert ctx.constraints_text is None
