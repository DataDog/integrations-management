# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from mwaa.discovery import discover_environments

ENVIRONMENTS = {
    "env-a": {
        "Name": "env-a",
        "AirflowVersion": "2.8.1",
        "SourceBucketArn": "arn:aws:s3:::bucket-a",
        "DagS3Path": "dags",
        "RequirementsS3Path": "requirements.txt",
        "StartupScriptS3Path": None,
    },
    "env-b": {
        "Name": "env-b",
        "AirflowVersion": "2.10.1",
        "SourceBucketArn": "arn:aws:s3:::bucket-b",
        "DagS3Path": "dags",
        "RequirementsS3Path": "requirements.txt",
        "StartupScriptS3Path": None,
    },
}


def make_client() -> MagicMock:
    client = MagicMock()
    client.list_environment_names.return_value = list(ENVIRONMENTS)
    client.get_environment.side_effect = lambda name: ENVIRONMENTS[name]
    client.get_object_text.return_value = "pandas==2.1.4\n"
    return client


def test_discover_environments_fetches_context_per_environment():
    client = make_client()

    contexts = discover_environments(client)

    assert [ctx.environment["Name"] for ctx in contexts] == ["env-a", "env-b"]


def test_discover_environments_returns_empty_list_when_none_found():
    client = make_client()
    client.list_environment_names.return_value = []

    assert discover_environments(client) == []


def test_discover_environments_skips_one_environment_that_fails(capsys):
    client = make_client()

    def get_environment(name):
        if name == "env-a":
            raise RuntimeError("boom")
        return ENVIRONMENTS[name]

    client.get_environment.side_effect = get_environment

    contexts = discover_environments(client)

    assert [ctx.environment["Name"] for ctx in contexts] == ["env-b"]
    assert "skipping env-a" in capsys.readouterr().out
