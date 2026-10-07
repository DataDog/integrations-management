# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Scan records every file's latest VersionId; apply refuses if any changed since -- see probe.py/apply.py."""

import json
from dataclasses import asdict

import pytest

from airflow_shared.reporter import FindingStatus
from mwaa.apply import StaleSessionError, apply_to_environment, check_files_unchanged, compute_apply_actions
from mwaa.plan import EnvVarChange, WheelReference
from mwaa.probe import build_context
from mwaa.session import build_session, session_from_dict

from .conftest import FakeS3Client

STARTUP = "#!/bin/sh\necho hi\n"


def environment(airflow_version: str = "2.8.1", **overrides) -> dict:
    return {
        "Name": "my-env",
        "AirflowVersion": airflow_version,
        "SourceBucketArn": "arn:aws:s3:::my-bucket",
        "DagS3Path": "dags",
        "RequirementsS3Path": "requirements.txt",
        "RequirementsS3ObjectVersion": "v-requirements.txt-0",
        "StartupScriptS3Path": "dags/startup.sh",
        "StartupScriptS3ObjectVersion": "v-dags/startup.sh-0",
        "ExecutionRoleArn": "arn:aws:iam::123456789012:role/r",
        "AirflowConfigurationOptions": {},
        **overrides,
    }


def scan(client: FakeS3Client):
    ctx = build_context(client, "my-env")
    return ctx, build_session("s", "us-east-1", "datadoghq.com", [ctx]).environments[0]


def failed_checks(entry) -> list[str]:
    return [i.check_id for i in entry.issues if i.status == FindingStatus.FAIL]


def test_file_versions_cover_every_file_the_plan_reads_or_writes_including_missing_ones():
    client = FakeS3Client(
        environment("2.7.2", StartupScriptS3Path=None, StartupScriptS3ObjectVersion=None),
        {"requirements.txt": "apache-airflow-providers-openlineage==1.1.0\n"},
    )

    _, entry = scan(client)

    assert entry.file_versions == {
        "requirements.txt": "v-requirements.txt-0",
        "dags/startup.sh": None,
        "dags/constraints.txt": None,
        "dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl": None,
        "dags/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl": None,
    }


def test_an_orphan_and_the_datadog_file_are_both_fingerprinted():
    client = FakeS3Client(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP, "dags/constraints.txt": "x==1\n"})

    _, entry = scan(client)

    assert entry.file_versions["dags/constraints.txt"] == "v-dags/constraints.txt-0"
    assert entry.file_versions["dags/constraints-datadog.txt"] is None


def test_an_unapplied_requirements_upload_drops_every_package_change():
    client = FakeS3Client(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP})
    client.put_object_text("my-bucket", "requirements.txt", "pandas==2.2.0\n")  # uploaded, never applied

    _, entry = scan(client)

    assert failed_checks(entry) == ["unapplied_uploads"]
    issue = next(i for i in entry.issues if i.check_id == "unapplied_uploads")
    assert issue.message == "requirements.txt has a newer upload than the environment is configured with; apply or discard it, then re-scan"
    assert entry.plan.file_changes and all(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)


def test_an_unapplied_startup_upload_drops_the_env_var_changes_only():
    client = FakeS3Client(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP})
    client.put_object_text("my-bucket", "dags/startup.sh", STARTUP + "echo newer\n")

    _, entry = scan(client)

    assert failed_checks(entry) == ["unapplied_uploads"]
    assert "dags/startup.sh has a newer upload" in entry.issues[0].message
    assert entry.plan.file_changes and not any(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)
    assert entry.already_configured is False  # still not configured, just not planned


def test_an_unreadable_version_drops_the_changes_that_depend_on_it():
    client = FakeS3Client(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP}, unreadable=frozenset({"requirements.txt"}))

    _, entry = scan(client)

    assert "file_versions" in failed_checks(entry)
    assert "requirements.txt" not in entry.file_versions
    assert all(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)


def test_apply_goes_through_when_nothing_changed_and_a_second_apply_of_the_same_session_is_refused():
    client = FakeS3Client(environment("2.7.2"), {"requirements.txt": "apache-airflow-providers-openlineage==1.1.0\n", "dags/startup.sh": STARTUP})
    ctx, entry = scan(client)
    wheels = [fc for fc in entry.plan.file_changes if isinstance(fc, WheelReference)]

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), wheels)

    with pytest.raises(StaleSessionError, match="changed since this session was scanned"):
        check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)


@pytest.mark.parametrize("with_file_versions", [True, False])
def test_file_versions_round_trip_and_default_to_empty_for_older_sessions(with_file_versions):
    client = FakeS3Client(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP})
    _, entry = scan(client)
    session = build_session("s", "us-east-1", "datadoghq.com", [build_context(client, "my-env")])
    data = json.loads(json.dumps(asdict(session)))
    if not with_file_versions:
        del data["environments"][0]["file_versions"]

    loaded = session_from_dict(data)

    assert loaded.environments[0].file_versions == (entry.file_versions if with_file_versions else {})


def test_an_existing_fallback_requirements_txt_the_environment_isnt_configured_with_is_an_unapplied_upload():
    client = FakeS3Client(
        environment(RequirementsS3Path=None, RequirementsS3ObjectVersion=None),
        {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP},
    )

    _, entry = scan(client)

    assert failed_checks(entry) == ["unapplied_uploads"]
    assert entry.issues[0].message.startswith("requirements.txt has a newer upload")
    assert entry.plan.file_changes and all(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)


def test_an_existing_fallback_startup_sh_the_environment_isnt_configured_with_is_an_unapplied_upload():
    client = FakeS3Client(
        environment(StartupScriptS3Path=None, StartupScriptS3ObjectVersion=None),
        {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP},
    )

    _, entry = scan(client)

    assert failed_checks(entry) == ["unapplied_uploads"]
    assert entry.issues[0].message.startswith("dags/startup.sh has a newer upload")
    assert entry.plan.file_changes and not any(isinstance(fc, EnvVarChange) for fc in entry.plan.file_changes)


def test_a_configured_path_without_a_pinned_version_is_never_an_unapplied_upload():
    client = FakeS3Client(environment(RequirementsS3ObjectVersion=None), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP})

    _, entry = scan(client)

    assert "unapplied_uploads" not in failed_checks(entry)


class OrphanAppearsAfterFirstLook(FakeS3Client):
    """dags/constraints.txt is missing for the first HeadObject and exists from then on."""

    def latest_version_id(self, bucket, key):
        version = super().latest_version_id(bucket, key)
        if key == "dags/constraints.txt" and "dags/constraints.txt" not in self.objects:
            self.put_object_text(bucket, key, "someone-elses==1.0\n")
        return version


def test_an_orphan_appearing_during_scan_is_caught_by_the_fingerprint_its_decision_came_from():
    client = OrphanAppearsAfterFirstLook(environment(), {"requirements.txt": "pandas==2.1.4\n", "dags/startup.sh": STARTUP})

    ctx, entry = scan(client)

    assert ctx.constraints_path == "dags/constraints.txt"
    assert entry.file_versions["dags/constraints.txt"] is None  # the same look that chose constraints.txt
    with pytest.raises(StaleSessionError, match=r"dags/constraints.txt \(missing at scan"):
        check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)


def test_a_differently_spelled_referenced_wheel_that_disappears_before_apply_is_caught():
    wheel_key = "dags/wheels/Apache_Airflow_Providers_OpenLineage-1.14.0-py3-none-any.whl"
    client = FakeS3Client(
        environment("2.7.2"),
        {
            "requirements.txt": f"/usr/local/airflow/{wheel_key}\n",
            "dags/startup.sh": STARTUP,
            wheel_key: b"PK wheel",
        },
    )
    ctx, entry = scan(client)
    assert not any(isinstance(fc, WheelReference) and fc.package == "apache-airflow-providers-openlineage" for fc in entry.plan.file_changes)
    assert entry.file_versions[wheel_key] == f"v-{wheel_key}-0"

    del client.objects[wheel_key], client.versions[wheel_key]

    with pytest.raises(StaleSessionError, match="Apache_Airflow_Providers_OpenLineage"):
        check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
