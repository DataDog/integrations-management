# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Thin boto3 wrappers for inspecting and updating a live MWAA environment.

Plays the role gcp_shared/gcloud.py and az_shared/execute_cmd.py play for
their clouds: MWAA has no CLI to shell out to, so this wraps the relevant
boto3 clients (mwaa, s3, logs, iam, ec2) directly instead.

Most methods here are read-only. Two are not -- `put_object_text` and
`update_environment`, used by the `apply` command -- and both are called out
individually in their own docstrings, since an `update_environment` call
restarts the environment's workers.
"""

from dataclasses import dataclass
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError


class ObjectNotFoundError(Exception):
    """The requested S3 object does not exist."""


class ReadOnlyViolation(RuntimeError):
    """A read-only MwaaClient attempted an operation outside its allowlist.

    `scan` promises never to write to a customer's account. Rather than rely
    on every call site staying read-only by review discipline,
    `read_only=True` makes that mechanically true: this is raised before the
    call ever reaches AWS. It can only mean a bug in this codebase, never a
    customer problem, so there is no override flag -- adding an operation
    here means editing READ_ONLY_ALLOWED instead.
    """


#: Every (service, operation) pair `scan`'s read-only path is allowed to call.
#: Deliberately exact, not permissive -- it should read as the list of calls
#: this codebase's read-only paths actually make today.
READ_ONLY_ALLOWED: dict[str, frozenset[str]] = {
    "mwaa": frozenset({"ListEnvironments", "GetEnvironment"}),
    "s3": frozenset({"GetObject", "HeadObject"}),
    "iam": frozenset({"SimulatePrincipalPolicy"}),
}


def _read_only_hook(service_name: str) -> Any:
    """Build a before-call hook bound to the service its client was created for.

    Registered per-client (see `_apply_read_only_guard`), not on a shared
    boto3 Session -- a session-wide hook would also intercept botocore's own
    credential resolution (SSO token exchange, AssumeRole), which is how
    botocore authenticates rather than something this code asked AWS to do.
    """

    def hook(model: Any = None, **_kwargs: Any) -> None:
        operation = getattr(model, "name", None)
        if operation in READ_ONLY_ALLOWED.get(service_name, frozenset()):
            return
        raise ReadOnlyViolation(
            f"blocked a call outside the read-only allowlist: {service_name}:{operation}. "
            "If this operation is genuinely needed here, add it to READ_ONLY_ALLOWED in mwaa_client.py."
        )

    return hook


def _apply_read_only_guard(client: Any, service_name: str) -> Any:
    client.meta.events.register(
        "before-call", _read_only_hook(service_name), unique_id=f"mwaa-client-readonly-{service_name}"
    )
    return client


@dataclass
class RouteTableEgress:
    """Egress posture for one subnet's route table."""

    subnet_id: str
    route_table_id: Optional[str]
    has_nat_route: bool
    has_internet_gateway_route: bool


class MwaaClient:
    """boto3 client bundle for one AWS region.

    `read_only=True` (used by `scan`'s discovery/issue-checking phase)
    mechanically enforces that this instance never calls anything beyond
    READ_ONLY_ALLOWED -- see ReadOnlyViolation. `apply`, and the one
    deliberate write inside interactive `scan`, are the only callers that
    need the default, full-power instance.
    """

    def __init__(self, region: str, read_only: bool = False):
        self.region = region
        self.read_only = read_only
        self._mwaa = boto3.client("mwaa", region_name=region)
        self._s3 = boto3.client("s3", region_name=region)
        self._logs = boto3.client("logs", region_name=region)
        self._iam = boto3.client("iam", region_name=region)
        self._ec2 = boto3.client("ec2", region_name=region)
        if read_only:
            for service_name, client in (
                ("mwaa", self._mwaa),
                ("s3", self._s3),
                ("logs", self._logs),
                ("iam", self._iam),
                ("ec2", self._ec2),
            ):
                _apply_read_only_guard(client, service_name)

    def list_environment_names(self) -> list[str]:
        """Return the names of every MWAA environment in this region, paginating as needed."""
        names: list[str] = []
        paginator = self._mwaa.get_paginator("list_environments")
        for page in paginator.paginate():
            names.extend(page.get("Environments", []))
        return names

    def get_environment(self, name: str) -> dict[str, Any]:
        """Return the raw GetEnvironment response body for an MWAA environment."""
        return self._mwaa.get_environment(Name=name)["Environment"]

    def get_object_text(self, bucket: str, key: str, version_id: Optional[str] = None) -> str:
        """Fetch an S3 object's content as text.

        Raises ObjectNotFoundError if the object (or the given version) does not exist.
        """
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if version_id:
            kwargs["VersionId"] = version_id
        try:
            response = self._s3.get_object(**kwargs)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise ObjectNotFoundError(f"s3://{bucket}/{key}") from e
            raise
        return response["Body"].read().decode("utf-8")

    def put_object_text(self, bucket: str, key: str, content: str) -> Optional[str]:
        """Write text content to an S3 object. Mutating -- used only by `apply`.

        Returns the new object's S3 VersionId (None if the bucket isn't versioned).
        """
        response = self._s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"))
        return response.get("VersionId")

    def update_environment(self, name: str, **kwargs: Any) -> None:
        """Call MWAA UpdateEnvironment. Mutating -- restarts the environment's workers.

        `kwargs` are passed straight through as UpdateEnvironment parameters,
        e.g. RequirementsS3Path/RequirementsS3ObjectVersion,
        StartupScriptS3Path/StartupScriptS3ObjectVersion.
        """
        self._mwaa.update_environment(Name=name, **kwargs)

    def object_exists(self, bucket: str, key: str) -> bool:
        """Return whether an S3 object exists, without fetching its content."""
        try:
            self._s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def simulate_s3_read_access(self, role_arn: str, bucket_arn: str) -> dict[str, bool]:
        """Simulate whether an IAM role can read from a bucket, per action.

        Uses IAM policy simulation rather than the caller's own credentials, so
        this reflects what the MWAA execution role itself can do -- not what
        the person running the probe can do.
        """
        actions = ["s3:GetObject", "s3:ListBucket"]
        response = self._iam.simulate_principal_policy(
            PolicySourceArn=role_arn,
            ActionNames=actions,
            ResourceArns=[bucket_arn, f"{bucket_arn}/*"],
        )
        allowed: dict[str, bool] = {action: False for action in actions}
        for result in response.get("EvaluationResults", []):
            action = result["EvalActionName"]
            if result["EvalDecision"] == "allowed":
                allowed[action] = True
        return allowed

    def filter_log_events(
        self, log_group_name: str, filter_pattern: str, start_time_ms: Optional[int] = None, limit: int = 100
    ) -> list[str]:
        """Return matching CloudWatch log event messages, newest first.

        Returns an empty list (rather than raising) if the log group does not
        exist -- a missing log group is itself a finding, not a script error.
        """
        kwargs: dict[str, Any] = {
            "logGroupName": log_group_name,
            "filterPattern": filter_pattern,
            "limit": limit,
        }
        if start_time_ms is not None:
            kwargs["startTime"] = start_time_ms
        try:
            response = self._logs.filter_log_events(**kwargs)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return []
            raise
        return [event["message"] for event in response.get("events", [])]

    def describe_subnet_egress(self, subnet_ids: list[str]) -> list[RouteTableEgress]:
        """Describe each subnet's route table for internet/NAT egress routes."""
        subnets = self._ec2.describe_subnets(SubnetIds=subnet_ids)["Subnets"]
        vpc_id = subnets[0]["VpcId"] if subnets else None

        route_tables = self._ec2.describe_route_tables(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else []
        )["RouteTables"]

        # A subnet with no explicit association uses the VPC's main route table.
        explicit_by_subnet: dict[str, dict[str, Any]] = {}
        main_table: Optional[dict[str, Any]] = None
        for table in route_tables:
            for assoc in table.get("Associations", []):
                if assoc.get("Main"):
                    main_table = table
                subnet_id = assoc.get("SubnetId")
                if subnet_id:
                    explicit_by_subnet[subnet_id] = table

        results = []
        for subnet_id in subnet_ids:
            table = explicit_by_subnet.get(subnet_id, main_table)
            routes = table.get("Routes", []) if table else []
            has_nat = any(r.get("NatGatewayId") for r in routes)
            has_igw = any(str(r.get("GatewayId", "")).startswith("igw-") for r in routes)
            results.append(
                RouteTableEgress(
                    subnet_id=subnet_id,
                    route_table_id=table.get("RouteTableId") if table else None,
                    has_nat_route=has_nat,
                    has_internet_gateway_route=has_igw,
                )
            )
        return results
