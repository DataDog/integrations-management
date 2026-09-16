# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest
from botocore.stub import ANY, Stubber

from airflow_shared.mwaa_client import MwaaClient, ObjectNotFoundError, ReadOnlyViolation


@pytest.fixture
def client() -> MwaaClient:
    return MwaaClient(region="us-east-1")


def test_get_environment_returns_environment_body(client: MwaaClient):
    stubber = Stubber(client._mwaa)
    stubber.add_response(
        "get_environment",
        {"Environment": {"Name": "my-env", "AirflowVersion": "3.0.6"}},
        {"Name": "my-env"},
    )
    with stubber:
        env = client.get_environment("my-env")
    assert env["AirflowVersion"] == "3.0.6"


def test_get_object_text_returns_decoded_body(client: MwaaClient):
    stubber = Stubber(client._s3)
    body = b"apache-airflow-providers-openlineage==2.18.0\n"
    stubber.add_response(
        "get_object",
        {"Body": _StreamingBody(body)},
        {"Bucket": "my-bucket", "Key": "requirements.txt"},
    )
    with stubber:
        text = client.get_object_text("my-bucket", "requirements.txt")
    assert text == body.decode("utf-8")


def test_get_object_text_raises_on_missing_object(client: MwaaClient):
    stubber = Stubber(client._s3)
    stubber.add_client_error(
        "get_object",
        service_error_code="NoSuchKey",
        expected_params={"Bucket": "my-bucket", "Key": "missing.txt"},
    )
    with stubber, pytest.raises(ObjectNotFoundError):
        client.get_object_text("my-bucket", "missing.txt")


def test_put_object_text_returns_version_id(client: MwaaClient):
    stubber = Stubber(client._s3)
    stubber.add_response(
        "put_object",
        {"VersionId": "v2"},
        {"Bucket": "my-bucket", "Key": "requirements.txt", "Body": ANY},
    )
    with stubber:
        version_id = client.put_object_text("my-bucket", "requirements.txt", "pandas==2.1.4\n")
    assert version_id == "v2"


def test_update_environment_passes_kwargs_through(client: MwaaClient):
    stubber = Stubber(client._mwaa)
    stubber.add_response(
        "update_environment",
        {},
        {"Name": "my-env", "RequirementsS3Path": "requirements.txt", "RequirementsS3ObjectVersion": "v2"},
    )
    with stubber:
        client.update_environment("my-env", RequirementsS3Path="requirements.txt", RequirementsS3ObjectVersion="v2")


def test_object_exists_true(client: MwaaClient):
    stubber = Stubber(client._s3)
    stubber.add_response("head_object", {}, {"Bucket": "my-bucket", "Key": "dags/constraints.txt"})
    with stubber:
        assert client.object_exists("my-bucket", "dags/constraints.txt") is True


def test_object_exists_false_on_404(client: MwaaClient):
    stubber = Stubber(client._s3)
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={"Bucket": "my-bucket", "Key": "dags/missing.txt"},
    )
    with stubber:
        assert client.object_exists("my-bucket", "dags/missing.txt") is False


def test_simulate_s3_read_access_reports_denied_action(client: MwaaClient):
    stubber = Stubber(client._iam)
    stubber.add_response(
        "simulate_principal_policy",
        {
            "EvaluationResults": [
                {"EvalActionName": "s3:GetObject", "EvalDecision": "allowed"},
                {"EvalActionName": "s3:ListBucket", "EvalDecision": "implicitDeny"},
            ]
        },
        {
            "PolicySourceArn": "arn:aws:iam::123456789012:role/my-role",
            "ActionNames": ["s3:GetObject", "s3:ListBucket"],
            "ResourceArns": ANY,
        },
    )
    with stubber:
        result = client.simulate_s3_read_access(
            "arn:aws:iam::123456789012:role/my-role", "arn:aws:s3:::my-bucket"
        )
    assert result == {"s3:GetObject": True, "s3:ListBucket": False}


def test_filter_log_events_returns_empty_list_for_missing_log_group(client: MwaaClient):
    stubber = Stubber(client._logs)
    stubber.add_client_error("filter_log_events", service_error_code="ResourceNotFoundException")
    with stubber:
        assert client.filter_log_events("no-such-group", "ERROR") == []


def test_filter_log_events_returns_messages(client: MwaaClient):
    stubber = Stubber(client._logs)
    stubber.add_response(
        "filter_log_events",
        {"events": [{"message": "ResolutionImpossible: ..."}]},
        {"logGroupName": "my-log-group", "filterPattern": "ResolutionImpossible", "limit": 100},
    )
    with stubber:
        messages = client.filter_log_events("my-log-group", "ResolutionImpossible")
    assert messages == ["ResolutionImpossible: ..."]


def test_describe_subnet_egress_detects_nat_route(client: MwaaClient):
    stubber = Stubber(client._ec2)
    stubber.add_response(
        "describe_subnets",
        {"Subnets": [{"SubnetId": "subnet-1", "VpcId": "vpc-1"}]},
        {"SubnetIds": ["subnet-1"]},
    )
    stubber.add_response(
        "describe_route_tables",
        {
            "RouteTables": [
                {
                    "RouteTableId": "rtb-1",
                    "Associations": [{"SubnetId": "subnet-1", "Main": False}],
                    "Routes": [{"DestinationCidrBlock": "0.0.0.0/0", "NatGatewayId": "nat-1"}],
                }
            ]
        },
        {"Filters": [{"Name": "vpc-id", "Values": ["vpc-1"]}]},
    )
    with stubber:
        results = client.describe_subnet_egress(["subnet-1"])
    assert results[0].has_nat_route is True
    assert results[0].has_internet_gateway_route is False


# --- read_only guard ----------------------------------------------------------


@pytest.fixture
def read_only_client() -> MwaaClient:
    return MwaaClient(region="us-east-1", read_only=True)


def test_read_only_client_blocks_put_object(read_only_client: MwaaClient):
    with pytest.raises(ReadOnlyViolation):
        read_only_client.put_object_text("my-bucket", "requirements.txt", "pandas==2.1.4\n")


def test_read_only_client_blocks_update_environment(read_only_client: MwaaClient):
    with pytest.raises(ReadOnlyViolation):
        read_only_client.update_environment("my-env", RequirementsS3Path="requirements.txt")


def test_read_only_client_allows_get_environment(read_only_client: MwaaClient):
    stubber = Stubber(read_only_client._mwaa)
    stubber.add_response("get_environment", {"Environment": {"Name": "my-env"}}, {"Name": "my-env"})
    with stubber:
        env = read_only_client.get_environment("my-env")
    assert env["Name"] == "my-env"


def test_default_client_is_not_read_only(client: MwaaClient):
    # get_object is on the write client's happy path too -- this just confirms
    # the default constructor doesn't attach the guard at all.
    assert client.read_only is False


class _StreamingBody:
    """Minimal stand-in for botocore.response.StreamingBody in stubbed responses."""

    def __init__(self, content: bytes):
        self._content = content

    def read(self) -> bytes:
        return self._content
