# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from airflow_shared.reporter import FindingStatus
from mwaa.checks import (
    ProbeContext,
    check_constraint_path,
    check_execution_role_s3_access,
    check_openlineage_pins,
    check_openlineage_precedence,
    check_requirements_constraints_match,
    check_wheel_references,
    resolve_constraint_key,
)

BASE_ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "ExecutionRoleArn": "arn:aws:iam::123456789012:role/my-execution-role",
    "AirflowConfigurationOptions": {},
    "NetworkConfiguration": {"SubnetIds": ["subnet-1", "subnet-2"]},
}


def make_context(**overrides) -> ProbeContext:
    environment = {**BASE_ENVIRONMENT, **overrides.pop("environment", {})}
    defaults = {
        "environment": environment,
        "requirements_text": "",
        "constraints_text": None,
        "startup_script_text": None,
        "client": MagicMock(),
    }
    defaults.update(overrides)
    return ProbeContext(**defaults)


# --- check_constraint_path ---------------------------------------------------


def test_constraint_path_warns_when_no_constraint_line():
    ctx = make_context(requirements_text="apache-airflow-providers-openlineage==2.18.0\n")
    finding = check_constraint_path(ctx)
    assert finding.status == FindingStatus.WARN


def test_constraint_path_passes_when_object_exists():
    ctx = make_context(requirements_text='--constraint "/usr/local/airflow/dags/constraints.txt"\n')
    ctx.client.object_exists.return_value = True
    finding = check_constraint_path(ctx)
    assert finding.status == FindingStatus.PASS
    ctx.client.object_exists.assert_called_once_with("my-bucket", "dags/constraints.txt")


def test_constraint_path_fails_when_object_missing():
    ctx = make_context(requirements_text='--constraint "/usr/local/airflow/dags/constraints.txt"\n')
    ctx.client.object_exists.return_value = False
    finding = check_constraint_path(ctx)
    assert finding.status == FindingStatus.FAIL


def test_constraint_path_warns_on_non_standard_path():
    ctx = make_context(requirements_text='--constraint "/some/other/path.txt"\n')
    finding = check_constraint_path(ctx)
    assert finding.status == FindingStatus.WARN


def test_resolve_constraint_key_none_without_constraint_line():
    assert resolve_constraint_key("apache-airflow==2.8.1\n", "dags") is None


def test_resolve_constraint_key_resolves_nested_path():
    text = '--constraint "/usr/local/airflow/dags/constraints/constraints.txt"\n'
    assert resolve_constraint_key(text, "custom/dags") == "custom/dags/constraints/constraints.txt"


# --- check_openlineage_pins ---------------------------------------------------


def test_openlineage_pins_fails_when_unpinned_on_flagged_version():
    ctx = make_context(requirements_text="", environment={"AirflowVersion": "2.8.1"})
    finding = check_openlineage_pins(ctx)
    assert finding.status == FindingStatus.FAIL


def test_openlineage_pins_passes_when_unpinned_on_unflagged_version():
    ctx = make_context(requirements_text="", environment={"AirflowVersion": "3.0.6"})
    finding = check_openlineage_pins(ctx)
    assert finding.status == FindingStatus.PASS


def test_openlineage_pins_warns_when_common_compat_missing():
    ctx = make_context(requirements_text="apache-airflow-providers-openlineage==2.18.0\n")
    finding = check_openlineage_pins(ctx)
    assert finding.status == FindingStatus.WARN


def test_openlineage_pins_passes_when_fully_pinned():
    ctx = make_context(
        requirements_text=(
            "apache-airflow-providers-openlineage==2.18.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
        )
    )
    finding = check_openlineage_pins(ctx)
    assert finding.status == FindingStatus.PASS


# --- check_requirements_constraints_match ------------------------------------


def test_requirements_constraints_match_warns_when_constraints_unavailable():
    ctx = make_context(requirements_text="apache-airflow-providers-openlineage==2.18.0\n", constraints_text=None)
    finding = check_requirements_constraints_match(ctx)
    assert finding.status == FindingStatus.WARN


def test_requirements_constraints_match_fails_on_version_mismatch():
    ctx = make_context(
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.14.0\n",
    )
    finding = check_requirements_constraints_match(ctx)
    assert finding.status == FindingStatus.FAIL


def test_requirements_constraints_match_passes_when_agreeing():
    ctx = make_context(
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text="apache-airflow-providers-openlineage==2.18.0\n",
    )
    finding = check_requirements_constraints_match(ctx)
    assert finding.status == FindingStatus.PASS


# --- check_openlineage_precedence --------------------------------------------


def test_openlineage_precedence_passes_when_nothing_configured():
    ctx = make_context()
    finding = check_openlineage_precedence(ctx)
    assert finding.status == FindingStatus.PASS


def test_openlineage_precedence_warns_on_conflicting_transport():
    ctx = make_context(
        environment={"AirflowConfigurationOptions": {"openlineage.transport": '{"url": "https://a.invalid"}'}},
        startup_script_text='export AIRFLOW__OPENLINEAGE__TRANSPORT=\'{"url": "https://b.invalid"}\'\n',
    )
    finding = check_openlineage_precedence(ctx)
    assert finding.status == FindingStatus.WARN


def test_openlineage_precedence_passes_when_sources_agree():
    ctx = make_context(
        environment={"AirflowConfigurationOptions": {"openlineage.namespace": "shared"}},
        startup_script_text="export AIRFLOW__OPENLINEAGE__NAMESPACE=shared\n",
    )
    finding = check_openlineage_precedence(ctx)
    assert finding.status == FindingStatus.PASS


# --- check_execution_role_s3_access ------------------------------------------


def test_execution_role_s3_access_passes_when_all_allowed():
    ctx = make_context()
    ctx.client.simulate_s3_read_access.return_value = {"s3:GetObject": True, "s3:ListBucket": True}
    finding = check_execution_role_s3_access(ctx)
    assert finding.status == FindingStatus.PASS


def test_execution_role_s3_access_fails_when_denied():
    ctx = make_context()
    ctx.client.simulate_s3_read_access.return_value = {"s3:GetObject": True, "s3:ListBucket": False}
    finding = check_execution_role_s3_access(ctx)
    assert finding.status == FindingStatus.FAIL


def test_execution_role_s3_access_warns_not_verified_when_caller_lacks_iam_permission():
    ctx = make_context()
    ctx.client.simulate_s3_read_access.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "not authorized to perform: iam:SimulatePrincipalPolicy"}},
        "SimulatePrincipalPolicy",
    )
    finding = check_execution_role_s3_access(ctx)
    assert finding.status == FindingStatus.WARN
    assert "couldn't run" in finding.detail.lower()


# --- check_wheel_references ---------------------------------------------------


def test_wheel_references_passes_when_none_referenced():
    ctx = make_context(requirements_text="apache-airflow-providers-openlineage==2.18.0\n")
    finding = check_wheel_references(ctx)
    assert finding.status == FindingStatus.PASS


def test_wheel_references_passes_when_referenced_wheel_exists():
    ctx = make_context(
        requirements_text="/usr/local/airflow/dags/wheels/datadog_provider-1.0.0-py3-none-any.whl\n"
    )
    ctx.client.object_exists.return_value = True
    finding = check_wheel_references(ctx)
    assert finding.status == FindingStatus.PASS
    ctx.client.object_exists.assert_called_once_with("my-bucket", "dags/wheels/datadog_provider-1.0.0-py3-none-any.whl")


def test_wheel_references_fails_when_referenced_wheel_missing():
    ctx = make_context(
        requirements_text="/usr/local/airflow/dags/wheels/datadog_provider-1.0.0-py3-none-any.whl\n"
    )
    ctx.client.object_exists.return_value = False
    finding = check_wheel_references(ctx)
    assert finding.status == FindingStatus.FAIL


def test_wheel_references_warns_when_path_outside_dags_mount():
    ctx = make_context(requirements_text="/opt/other/datadog_provider-1.0.0-py3-none-any.whl\n")
    finding = check_wheel_references(ctx)
    assert finding.status == FindingStatus.WARN
