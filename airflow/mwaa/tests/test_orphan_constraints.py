# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""An unreferenced dags/constraints.txt is never patched or overwritten -- see probe.py."""

from airflow_shared.reporter import FindingStatus
from mwaa.apply import apply_to_environment, compute_apply_actions, real_key_for_path
from mwaa.plan import ConstraintDirectiveChange, EnvVarChange, PinChange
from mwaa.probe import build_context
from mwaa.session import build_session

from .conftest import UPSTREAM_2_8_1_TEXT, UPSTREAM_2_8_1_URL, FakeS3Client

ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "ExecutionRoleArn": "arn:aws:iam::123456789012:role/r",
    "AirflowConfigurationOptions": {},
}
URL_REQUIREMENTS = f'--constraint "{UPSTREAM_2_8_1_URL}"\napache-airflow-providers-amazon==8.16.0\n'
SOMEONE_ELSES_CONSTRAINTS = "pandas==1.5.3\n"


def scan(client: FakeS3Client):
    ctx = build_context(client, "my-env")
    return ctx, build_session("s", "us-east-1", "datadoghq.com", [ctx]).environments[0]


def constraints_paths(plan) -> set[str]:
    return {fc.path for fc in plan.file_changes if isinstance(fc, PinChange) and fc.path != "requirements.txt"}


def test_an_existing_unreferenced_constraints_txt_sends_the_patch_to_constraints_datadog_txt():
    client = FakeS3Client(ENVIRONMENT, {"requirements.txt": URL_REQUIREMENTS, "dags/constraints.txt": SOMEONE_ELSES_CONSTRAINTS})

    ctx, entry = scan(client)

    assert constraints_paths(entry.plan) == {"dags/constraints-datadog.txt"}
    directive = next(fc for fc in entry.plan.file_changes if isinstance(fc, ConstraintDirectiveChange))
    assert directive.to_line == '--constraint "/usr/local/airflow/dags/constraints-datadog.txt"'
    assert (
        "dags/constraints.txt already exists but isn't referenced by requirements.txt, so the patched constraints "
        "are written to constraints-datadog.txt instead of overwriting it."
    ) in entry.plan.rationale
    assert real_key_for_path(ctx, "dags/constraints-datadog.txt") == "dags/constraints-datadog.txt"

    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])

    assert client.objects["dags/constraints.txt"] == SOMEONE_ELSES_CONSTRAINTS
    assert "boto3==1.33.13" in client.objects["dags/constraints-datadog.txt"]
    assert "apache-airflow-providers-openlineage==1.14.0" in client.objects["dags/constraints-datadog.txt"]
    assert client.objects["requirements.txt"].splitlines()[0] == '--constraint "/usr/local/airflow/dags/constraints-datadog.txt"'


def test_no_existing_constraints_txt_writes_constraints_txt():
    client = FakeS3Client(ENVIRONMENT, {"requirements.txt": URL_REQUIREMENTS})

    ctx, entry = scan(client)

    assert constraints_paths(entry.plan) == {"dags/constraints.txt"}
    directive = next(fc for fc in entry.plan.file_changes if isinstance(fc, ConstraintDirectiveChange))
    assert directive.to_line == '--constraint "/usr/local/airflow/dags/constraints.txt"'
    assert "constraints-datadog.txt" not in entry.plan.rationale


def test_not_being_able_to_tell_whether_constraints_txt_exists_drops_every_package_change():
    client = FakeS3Client(ENVIRONMENT, {"requirements.txt": URL_REQUIREMENTS}, unreadable=frozenset({"dags/constraints.txt"}))

    _, entry = scan(client)

    failed = [i for i in entry.issues if i.status == FindingStatus.FAIL]
    assert [i.check_id for i in failed] == ["base_constraints"]
    assert "couldn't tell whether dags/constraints.txt exists" in failed[0].message
    assert "s3:ListBucket" in failed[0].message
    assert entry.plan.file_changes and all(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)


def test_a_rescan_after_writing_constraints_datadog_txt_patches_it_in_place_without_an_orphan_check():
    client = FakeS3Client(ENVIRONMENT, {"requirements.txt": URL_REQUIREMENTS, "dags/constraints.txt": SOMEONE_ELSES_CONSTRAINTS})
    ctx, entry = scan(client)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])
    # a now-unreadable constraints.txt would fail the scan if it were still being checked
    client.unreadable = frozenset({"dags/constraints.txt"})

    ctx, entry = scan(client)

    assert ctx.constraints_path == "dags/constraints-datadog.txt"
    assert ctx.base_constraints.text == client.objects["dags/constraints-datadog.txt"]
    assert not any(fc.path != "dags/startup.sh" for fc in entry.plan.file_changes)


def test_a_referenced_custom_named_local_file_keeps_its_own_name_as_the_label():
    requirements = '--constraint "/usr/local/airflow/dags/deps/pinned.txt"\napache-airflow-providers-openlineage==1.4.0\n'
    client = FakeS3Client(ENVIRONMENT, {"requirements.txt": requirements, "dags/deps/pinned.txt": UPSTREAM_2_8_1_TEXT})

    ctx, entry = scan(client)

    assert constraints_paths(entry.plan) == {"dags/deps/pinned.txt"}
    assert not any(isinstance(fc, ConstraintDirectiveChange) for fc in entry.plan.file_changes)
    assert real_key_for_path(ctx, "dags/deps/pinned.txt") == "dags/deps/pinned.txt"
