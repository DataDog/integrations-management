# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""No --constraint line on a flagged version: mirror the constraints MWAA itself applies there -- see base_constraints.py case 3."""

import pytest

from airflow_shared.reporter import FindingStatus
from mwaa.apply import apply_to_environment, check_files_unchanged, compute_apply_actions
from mwaa.base_constraints import MINIMAL_CONSTRAINTS_HEADER
from mwaa.plan import ConstraintDirectiveChange, PinChange, WheelReference
from mwaa.probe import build_context
from mwaa.session import build_session

from .conftest import UPSTREAM_2_7_2_URL, UPSTREAM_2_9_2_URL, FakeS3Client


def environment(airflow_version: str) -> dict:
    return {
        "Name": "my-env",
        "AirflowVersion": airflow_version,
        "SourceBucketArn": "arn:aws:s3:::my-bucket",
        "DagS3Path": "dags",
        "RequirementsS3Path": "requirements.txt",
        "ExecutionRoleArn": "arn:aws:iam::123456789012:role/r",
        "AirflowConfigurationOptions": {},
    }


def scan(airflow_version: str, requirements: str = "pandas\nboto3\n"):
    client = FakeS3Client(environment(airflow_version), {"requirements.txt": requirements})
    ctx = build_context(client, "my-env")
    return client, ctx, build_session("s", "us-east-1", "datadoghq.com", [ctx]).environments[0]


def issues(entry, status) -> dict[str, str]:
    return {i.check_id: i.message for i in entry.issues if i.status == status}


def constraint_pins(entry) -> dict[str, "tuple[str | None, str | None]"]:
    return {fc.package: (fc.from_version, fc.to_version) for fc in entry.plan.file_changes if isinstance(fc, PinChange) and fc.path == "dags/constraints.txt"}


def test_2_7_2_writes_the_upstream_file_mwaa_already_forces_with_the_openlineage_pins_raised():
    client, ctx, entry = scan("2.7.2")

    assert ctx.base_constraints.mwaa_default and ctx.base_constraints.source == UPSTREAM_2_7_2_URL
    assert constraint_pins(entry)["apache-airflow-providers-openlineage"] == ("1.1.0", "1.14.0")
    assert f"the Airflow constraints file MWAA already applies on Airflow 2.7.2 ({UPSTREAM_2_7_2_URL})" in entry.plan.rationale
    # wheel-only packages: still referenced as wheels, and pinned in constraints to the wheel's own version
    wheels = {fc.package: fc for fc in entry.plan.file_changes if isinstance(fc, WheelReference)}
    assert set(wheels) == {"apache-airflow-providers-openlineage", "apache-airflow-providers-common-compat"}
    assert constraint_pins(entry)["apache-airflow-providers-common-compat"] == (None, "1.2.2")
    assert ConstraintDirectiveChange(path="requirements.txt", from_line=None, to_line='--constraint "/usr/local/airflow/dags/constraints.txt"') in entry.plan.file_changes

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])
    written = client.objects["dags/constraints.txt"]
    assert "boto3==1.28.62" in written  # everything else stays at what MWAA was already enforcing
    assert "apache-airflow-providers-openlineage==1.14.0" in written
    assert "apache-airflow-providers-common-sql==1.7.2" in written  # no 2.7.2 change, and no bump
    assert not written.startswith(MINIMAL_CONSTRAINTS_HEADER)


def test_2_9_2_writes_the_upstream_file_with_the_sqlparse_bump():
    _, ctx, entry = scan("2.9.2")

    assert ctx.base_constraints.source == UPSTREAM_2_9_2_URL
    pins = constraint_pins(entry)
    assert pins["sqlparse"] == ("0.5.0", "0.5.1")
    assert pins["apache-airflow-providers-openlineage"] == ("1.8.0", "2.2.0")
    assert "apache-airflow-providers-common-sql 1.21.0 needs sqlparse>=0.5.1" in entry.plan.rationale


def test_2_8_1_still_writes_the_minimal_file_since_mwaa_forces_nothing_there(fake_fetch):
    fake_fetch.clear()  # and nothing is downloaded

    _, ctx, entry = scan("2.8.1")

    assert ctx.base_constraints.minimal
    assert all(from_version is None for from_version, _ in constraint_pins(entry).values())
    assert "sqlparse" not in constraint_pins(entry)
    assert "MWAA applies no constraints of its own on Airflow 2.8.1" in entry.plan.rationale


@pytest.mark.parametrize("airflow_version", ["2.7.2", "2.9.2"])
def test_a_forcing_version_whose_upstream_file_cant_be_downloaded_fails_with_no_package_changes(fake_fetch, airflow_version):
    fake_fetch.clear()

    _, ctx, entry = scan(airflow_version)

    assert not ctx.base_constraints.minimal  # never falls back to the minimal file
    assert "base_constraints" in issues(entry, FindingStatus.FAIL)
    assert not [fc for fc in entry.plan.file_changes if isinstance(fc, (PinChange, ConstraintDirectiveChange, WheelReference))]


def test_a_direct_pin_that_conflicts_with_the_constraints_mwaa_applies_is_a_warning():
    _, _, entry = scan("2.9.2", "pandas==2.1.4\nboto3==1.35.0\nsqlparse==0.5.0\napache-airflow-providers-openlineage==1.8.0\n")

    message = issues(entry, FindingStatus.WARN)["requirement_pins"]
    assert message == (
        "requirements.txt pins boto3==1.35.0 (the constraints pin 1.34.106), sqlparse==0.5.0 (the constraints pin 0.5.1), "
        "which conflict with the Airflow constraints MWAA applies on Airflow 2.9.2; pip will fail to install requirements.txt until they match"
    )  # pandas matches, and the provider is an OpenLineage target the plan sets in requirements.txt too


@pytest.mark.parametrize(
    "airflow_version, requirements",
    [("2.9.2", "pandas==2.1.4\nboto3==1.34.106\n"), ("2.8.1", "boto3==1.35.0\n")],
    ids=["agreeing-pins", "version-mwaa-forces-nothing-on"],
)
def test_no_pin_warning_when_nothing_conflicts_with_what_mwaa_applies(airflow_version, requirements):
    _, _, entry = scan(airflow_version, requirements)

    assert "requirement_pins" not in issues(entry, FindingStatus.WARN)
