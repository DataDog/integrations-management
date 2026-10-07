# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from mwaa.probe import build_context

from .conftest import UPSTREAM_2_8_1_TEXT, UPSTREAM_2_8_1_URL

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
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.latest_version_id.side_effect = lambda bucket, key: f"v-{key}" if key == "dags/constraints.txt" else None
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
    client.latest_version_id.side_effect = None
    client.latest_version_id.return_value = None  # HeadObject: 404 for everything

    ctx = build_context(client, "my-env")

    assert ctx.constraints_text is None
    assert ctx.file_versions["dags/constraints.txt"] is None
    assert all(call.args[1] != "dags/constraints.txt" for call in client.get_object_text.call_args_list)


def test_build_context_tolerates_environment_with_no_requirements_configured():
    client = make_client()
    environment_without_requirements = {k: v for k, v in ENVIRONMENT.items() if k != "RequirementsS3Path"}
    client.get_environment.return_value = environment_without_requirements

    ctx = build_context(client, "my-env")

    assert ctx.requirements_text == ""
    assert ctx.constraints_text is None


def test_build_context_uses_the_referenced_local_constraints_file_as_its_own_base(fake_fetch):
    fake_fetch.clear()  # a local base must never need the network
    client = make_client()

    ctx = build_context(client, "my-env")

    assert ctx.base_constraints.source == "s3://my-bucket/dags/constraints.txt"
    assert ctx.base_constraints.text == "apache-airflow-providers-openlineage==2.18.0\n"


def test_build_context_fetches_the_url_requirements_already_points_at(fake_fetch):
    url = "https://example.invalid/my-constraints.txt"
    fake_fetch[url] = b"apache-airflow-providers-openlineage==1.4.0\nboto3==1.33.13\n"
    client = make_client()
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": f'--constraint "{url}"\n',
        "startup/mwaa-startup.sh": "",
    }[key]

    ctx = build_context(client, "my-env")

    assert ctx.constraints_text is None
    assert ctx.base_constraints.source == url
    assert "boto3==1.33.13" in ctx.base_constraints.text


def test_build_context_falls_back_to_upstream_constraints_for_the_airflow_and_python_version():
    client = make_client()
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": "pandas==2.1.4\n",
        "startup/mwaa-startup.sh": "",
    }[key]

    ctx = build_context(client, "my-env")

    assert ctx.base_constraints.source == UPSTREAM_2_8_1_URL
    assert ctx.base_constraints.text == UPSTREAM_2_8_1_TEXT


def test_build_context_records_a_base_constraints_fetch_failure_instead_of_raising(fake_fetch):
    fake_fetch.clear()
    client = make_client()
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": "pandas==2.1.4\n",
        "startup/mwaa-startup.sh": "",
    }[key]

    ctx = build_context(client, "my-env")

    assert ctx.base_constraints.text is None
    assert ctx.base_constraints.source == UPSTREAM_2_8_1_URL
    assert "could not download" in ctx.base_constraints.error


def test_build_context_skips_base_constraints_for_unflagged_versions(fake_fetch):
    fake_fetch.clear()
    client = make_client()
    client.get_environment.return_value = {**ENVIRONMENT, "AirflowVersion": "2.10.3"}

    assert build_context(client, "my-env").base_constraints is None


def test_build_context_fingerprints_referenced_wheels_and_derives_presence_from_that():
    wheel = "apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl"
    client = make_client()
    client.get_environment.return_value = {**ENVIRONMENT, "AirflowVersion": "2.7.2"}
    client.get_object_text.side_effect = lambda bucket, key, version_id=None: {
        "requirements.txt": f"/usr/local/airflow/dags/{wheel}\n/usr/local/airflow/dags/other-1.0-py3-none-any.whl\n",
        "startup/mwaa-startup.sh": "",
    }[key]

    def latest_version_id(bucket, key):
        if key == "dags/other-1.0-py3-none-any.whl":
            return "v-other"
        if key == f"dags/{wheel}":
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
        return None

    client.latest_version_id.side_effect = latest_version_id

    ctx = build_context(client, "my-env")

    assert ctx.present_wheel_files == frozenset({"other-1.0-py3-none-any.whl"})
    assert ctx.file_versions["dags/other-1.0-py3-none-any.whl"] == "v-other"
    assert f"dags/{wheel}" in ctx.file_version_errors  # an unknowable wheel blocks the package changes instead
