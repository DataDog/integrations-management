# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

import pytest

from airflow_shared.mwaa_client import ObjectNotFoundError
from airflow_shared.reporter import FindingStatus
from mwaa.apply import compute_apply_actions, apply_to_environment, interpolate_api_key, real_key_for_path
from mwaa.base_constraints import BaseConstraints
from mwaa.checks import ProbeContext, check_wheel_references
from mwaa.plan import ConstraintDirectiveChange, WheelReference, compute_plan
from mwaa.probe import build_context
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER

from .conftest import FAKE_WHEEL_BYTES, OPENLINEAGE_WHEEL_URL, UPSTREAM_2_7_2_TEXT

ENVIRONMENT = {"Name": "my-env", "AirflowVersion": "2.8.1", "SourceBucketArn": "arn:aws:s3:::my-bucket"}


def make_context(**overrides) -> ProbeContext:
    defaults = {
        "environment": ENVIRONMENT,
        "requirements_text": "apache-airflow-providers-openlineage==1.4.0\n",
        "constraints_text": "apache-airflow-providers-openlineage==1.4.0\n",
        "startup_script_text": None,
        "client": None,
    }
    defaults.update(overrides)
    # same as build_context for a referenced local file: it's its own base
    if "base_constraints" not in defaults and defaults["constraints_text"] is not None:
        defaults["base_constraints"] = BaseConstraints(source="s3://my-bucket/dags/constraints.txt", text=defaults["constraints_text"])
    return ProbeContext(**defaults)


def test_compute_apply_actions_patches_requirements_and_constraints():
    ctx = make_context()
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")

    uploads = compute_apply_actions(ctx, plan)

    by_path = {u.path: u for u in uploads}
    assert "apache-airflow-providers-openlineage==1.14.0" in by_path["dags/constraints.txt"].content
    assert "apache-airflow-providers-openlineage==1.14.0" in by_path["requirements.txt"].content
    assert '--constraint "/usr/local/airflow/dags/constraints.txt"' in by_path["requirements.txt"].content
    assert by_path["dags/startup.sh"].content.startswith("#!/bin/sh")


def test_compute_apply_actions_uses_prerendered_startup_script_content():
    ctx = make_context(
        requirements_text=(
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        constraints_text=(
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
    )
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")

    uploads = compute_apply_actions(ctx, plan)

    assert len(uploads) == 1
    assert uploads[0].path == "dags/startup.sh"
    assert f"OPENLINEAGE_API_KEY={DD_API_KEY_PLACEHOLDER}" in uploads[0].content


def test_interpolate_api_key_substitutes_only_the_startup_script_upload():
    ctx = make_context()
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")
    uploads = compute_apply_actions(ctx, plan)

    interpolated = interpolate_api_key(uploads, "real-dd-api-key")

    by_path = {u.path: u for u in interpolated}
    assert "OPENLINEAGE_API_KEY=real-dd-api-key" in by_path["dags/startup.sh"].content
    assert DD_API_KEY_PLACEHOLDER not in by_path["dags/startup.sh"].content
    # untouched -- the placeholder only ever appears in the startup.sh content
    assert by_path["requirements.txt"].content == next(u for u in uploads if u.path == "requirements.txt").content


UPSTREAM_URL = "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"
UPSTREAM_TEXT = "apache-airflow-providers-openlineage==1.4.0\nboto3==1.33.13\npandas==2.1.4\n"


def test_url_constraint_writes_the_full_base_and_replaces_the_url_line():
    """The common AWS-recommended shape: requirements.txt already points at the upstream URL."""
    ctx = make_context(
        requirements_text=f'--constraint "{UPSTREAM_URL}"\napache-airflow-providers-openlineage==1.4.0\n',
        constraints_text=None,
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
    )
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")

    by_path = {u.path: u for u in compute_apply_actions(ctx, plan)}

    constraints = by_path["dags/constraints.txt"]
    assert constraints.action == "create"
    assert constraints.content.startswith("apache-airflow-providers-openlineage==1.14.0\nboto3==1.33.13\npandas==2.1.4\n")
    assert "apache-airflow-providers-common-compat==1.2.1" in constraints.content

    requirements = by_path["requirements.txt"].content
    assert requirements.splitlines()[0] == '--constraint "/usr/local/airflow/dags/constraints.txt"'
    assert requirements.count("--constraint") == 1
    assert UPSTREAM_URL not in requirements
    assert real_key_for_path(ctx, "dags/constraints.txt") == "dags/constraints.txt"


def test_custom_named_local_constraints_file_is_patched_in_place():
    local_text = "apache-airflow-providers-openlineage==1.4.0\nboto3==1.33.13\n"
    ctx = make_context(
        environment={**ENVIRONMENT, "DagS3Path": "dags"},
        requirements_text='--constraint "/usr/local/airflow/dags/deps/my-constraints.txt"\napache-airflow-providers-openlineage==1.4.0\n',
        constraints_text=local_text,
    )
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")

    by_path = {u.path: u for u in compute_apply_actions(ctx, plan)}

    assert by_path["dags/constraints.txt"].action == "update"
    assert by_path["dags/constraints.txt"].old_content == local_text
    assert "boto3==1.33.13" in by_path["dags/constraints.txt"].content
    assert by_path["requirements.txt"].content.splitlines()[0] == '--constraint "/usr/local/airflow/dags/deps/my-constraints.txt"'
    assert real_key_for_path(ctx, "dags/constraints.txt") == "dags/deps/my-constraints.txt"


FULLY_PINNED_2_8_1 = (
    "apache-airflow-providers-openlineage==1.14.0\n"
    "apache-airflow-providers-common-sql==1.20.0\n"
    "apache-airflow-providers-common-compat==1.2.1\n"
    "openlineage-integration-common==1.24.2\n"
    "openlineage-python==1.24.2\n"
    "openlineage-sql==1.24.2\n"
)


def test_constraint_line_that_moved_from_url_to_a_local_file_after_scan_is_left_alone():
    at_scan = make_context(
        requirements_text=f'--constraint "{UPSTREAM_URL}"\n',
        constraints_text=None,
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
    )
    plan = compute_plan("2.8.1", at_scan.requirements_text, at_scan.base_constraints, None, "datadoghq.com", "my-env")
    assert any(isinstance(fc, ConstraintDirectiveChange) for fc in plan.file_changes)

    at_apply = make_context(
        requirements_text='--constraint "/usr/local/airflow/dags/deps/custom.txt"\n',
        constraints_text="apache-airflow-providers-openlineage==1.4.0\nboto3==1.33.13\n",
    )
    by_path = {u.path: u for u in compute_apply_actions(at_apply, plan)}

    assert by_path["requirements.txt"].content.splitlines()[0] == '--constraint "/usr/local/airflow/dags/deps/custom.txt"'
    assert "boto3==1.33.13" in by_path["dags/constraints.txt"].content
    assert real_key_for_path(at_apply, "dags/constraints.txt") == "dags/deps/custom.txt"


def test_constraint_line_that_moved_from_a_local_file_to_a_url_after_scan_gets_replaced():
    """The plan has no requirements.txt change at all, but apply still has to repoint it."""
    at_scan = make_context(
        requirements_text='--constraint "/usr/local/airflow/dags/deps/custom.txt"\n' + FULLY_PINNED_2_8_1,
        constraints_text=UPSTREAM_TEXT,
    )
    plan = compute_plan("2.8.1", at_scan.requirements_text, at_scan.base_constraints, None, "datadoghq.com", "my-env")
    assert not any(fc.path == "requirements.txt" for fc in plan.file_changes)

    at_apply = make_context(
        requirements_text=f'--constraint "{UPSTREAM_URL}"\n' + FULLY_PINNED_2_8_1,
        constraints_text=None,
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
    )
    by_path = {u.path: u for u in compute_apply_actions(at_apply, plan)}

    requirements = by_path["requirements.txt"].content
    assert requirements.splitlines()[0] == '--constraint "/usr/local/airflow/dags/constraints.txt"'
    assert UPSTREAM_URL not in requirements
    assert real_key_for_path(at_apply, "dags/constraints.txt") == "dags/constraints.txt"


def test_compute_apply_actions_refuses_constraints_if_requirements_gained_a_second_constraint_line():
    at_scan = make_context(constraints_text=None, base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT))
    plan = compute_plan("2.8.1", at_scan.requirements_text, at_scan.base_constraints, None, "datadoghq.com", "my-env")
    at_apply = make_context(
        requirements_text=f'--constraint "{UPSTREAM_URL}"\n-c https://example.invalid/c.txt\n',
        constraints_text=None,
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
    )

    with pytest.raises(RuntimeError, match="2 --constraint lines"):
        compute_apply_actions(at_apply, plan)


def test_compute_apply_actions_refuses_to_write_constraints_without_a_base():
    """Scan read the base fine, but apply's fresh fetch didn't -- never fall back to a pins-only file."""
    readable = make_context(constraints_text=None, base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT))
    plan = compute_plan("2.8.1", readable.requirements_text, readable.base_constraints, None, "datadoghq.com", "my-env")
    unreadable = make_context(constraints_text=None, base_constraints=BaseConstraints(source=UPSTREAM_URL, text=None, error="timed out"))

    with pytest.raises(RuntimeError, match="timed out"):
        compute_apply_actions(unreadable, plan)


def test_compute_apply_actions_rejects_unknown_path():
    from mwaa.plan import PinChange, Plan

    plan = Plan(
        upgrade_needed=True,
        rationale="",
        source="flagged_version_table",
        matched_table_entry=None,
        source_doc="",
        file_changes=[PinChange(path="somewhere/else.txt", package="pandas", from_version=None, to_version="2.1.4")],
    )
    with pytest.raises(ValueError, match="somewhere/else.txt"):
        compute_apply_actions(make_context(), plan)


def test_compute_apply_actions_handles_unflagged_version_missing_provider():
    """Mirrors do-test-env's gus-sandbox resting state: Airflow 3.0.6 (not in the
    flagged-version table), no OpenLineage provider in requirements.txt, startup
    script already configured. `apply` has to handle this shape too, not just the
    flagged-version table's constraints.txt + requirements.txt + startup.sh case.
    """
    ctx = make_context(
        environment={"Name": "my-env", "AirflowVersion": "3.0.6", "SourceBucketArn": "arn:aws:s3:::my-bucket"},
        requirements_text="pandas==2.1.4\n",
        constraints_text=None,
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
    )
    plan = compute_plan("3.0.6", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")
    assert plan.upgrade_needed is True
    assert plan.source == "unflagged_version"

    uploads = compute_apply_actions(ctx, plan)

    assert len(uploads) == 1
    upload = uploads[0]
    assert upload.path == "requirements.txt"
    assert upload.content == "pandas==2.1.4\napache-airflow-providers-openlineage\n"
    assert "apache-airflow-providers-openlineage==" not in upload.content
    assert "--constraint" not in upload.content


def test_apply_to_environment_uploads_and_calls_update():
    client = MagicMock()
    client.put_object_text.side_effect = ["v-con", "v-req", "v-startup"]
    ctx = make_context()
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")
    uploads = compute_apply_actions(ctx, plan)

    result = apply_to_environment(client, ctx, uploads, [])

    assert client.put_object_text.call_count == len(uploads)
    client.update_environment.assert_called_once()
    call_kwargs = client.update_environment.call_args.kwargs
    assert call_kwargs["RequirementsS3ObjectVersion"] == "v-req"
    assert call_kwargs["StartupScriptS3ObjectVersion"] == "v-startup"
    assert result["update_environment_called"] is True
    assert len(result["uploaded"]) == len(uploads)


def test_apply_to_environment_skips_update_call_when_only_constraints_change():
    client = MagicMock()
    client.put_object_text.return_value = "v1"
    from mwaa.apply import FileUpload

    ctx = make_context()
    uploads = [FileUpload(path="dags/constraints.txt", old_content="", content="pandas==2.1.4\n", action="update")]

    result = apply_to_environment(client, ctx, uploads, [])

    client.update_environment.assert_not_called()
    assert result["update_environment_called"] is False


def test_apply_to_environment_writes_to_the_environments_real_prefixed_keys():
    """Reproduces a real incident: an environment sharing a bucket with another one
    under a setup-probe/<name>/ prefix got its upload written to the literal key
    "requirements.txt" -- which happened to be that OTHER environment's real file.
    """
    client = MagicMock()
    client.put_object_text.side_effect = ["v-con", "v-req", "v-startup"]
    ctx = make_context(
        environment={
            "Name": "probe-env",
            "AirflowVersion": "2.8.1",
            "SourceBucketArn": "arn:aws:s3:::shared-bucket",
            "DagS3Path": "setup-probe/probe-env/dags",
            "RequirementsS3Path": "setup-probe/probe-env/requirements.txt",
            "StartupScriptS3Path": "setup-probe/probe-env/startup/startup.sh",
        },
    )
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.base_constraints, ctx.startup_script_text, "datadoghq.com", "my-env")
    uploads = compute_apply_actions(ctx, plan)

    result = apply_to_environment(client, ctx, uploads, [])

    written_keys = {call.args[1] for call in client.put_object_text.call_args_list}
    assert written_keys == {
        "setup-probe/probe-env/requirements.txt",
        "setup-probe/probe-env/dags/constraints.txt",
        "setup-probe/probe-env/startup/startup.sh",
    }
    assert "requirements.txt" not in written_keys  # the OTHER environment's real key

    call_kwargs = client.update_environment.call_args.kwargs
    assert call_kwargs["RequirementsS3Path"] == "setup-probe/probe-env/requirements.txt"
    assert call_kwargs["StartupScriptS3Path"] == "setup-probe/probe-env/startup/startup.sh"
    assert {u["path"] for u in result["uploaded"]} == written_keys


def test_real_key_for_path_resolves_constraints_under_the_dags_prefix_when_none_exists_yet():
    ctx = make_context(
        environment={
            "Name": "probe-env",
            "AirflowVersion": "2.8.1",
            "SourceBucketArn": "arn:aws:s3:::shared-bucket",
            "DagS3Path": "setup-probe/probe-env/dags",
        },
        requirements_text="pandas==2.1.4\n",  # no --constraint line yet
    )

    from mwaa.plan import CONSTRAINTS_PATH

    assert real_key_for_path(ctx, CONSTRAINTS_PATH) == "setup-probe/probe-env/dags/constraints.txt"


def test_real_key_for_path_falls_back_for_never_configured_requirements():
    ctx = make_context(
        environment={
            "Name": "probe-env",
            "AirflowVersion": "2.8.1",
            "SourceBucketArn": "arn:aws:s3:::shared-bucket",
            "DagS3Path": "setup-probe/probe-env/dags",
            # RequirementsS3Path deliberately absent
        },
    )

    from mwaa.plan import REQUIREMENTS_PATH

    assert real_key_for_path(ctx, REQUIREMENTS_PATH) == "setup-probe/probe-env/requirements.txt"


class FakeS3Client:
    """Just enough of MwaaClient to build a context from, apply against and re-check, backed by a dict."""

    def __init__(self, environment: dict, objects: dict):
        self.environment = environment
        self.objects = dict(objects)
        self.update_environment = MagicMock()

    def get_environment(self, name):
        return self.environment

    def get_object_text(self, bucket, key, version_id=None):
        if key not in self.objects:
            raise ObjectNotFoundError(key)
        return self.objects[key]

    def put_object_text(self, bucket, key, content):
        self.objects[key] = content
        return None

    def put_object_bytes(self, bucket, key, content):
        self.objects[key] = content
        return None

    def object_exists(self, bucket, key):
        return key in self.objects


WHEEL_ENVIRONMENT = {**ENVIRONMENT, "AirflowVersion": "2.7.2", "DagS3Path": "dags", "RequirementsS3Path": "requirements.txt"}


def scan_and_apply(client: FakeS3Client):
    ctx = build_context(client, "my-env")
    plan = compute_plan("2.7.2", ctx.requirements_text, ctx.base_constraints, None, "datadoghq.com", "my-env", ctx.present_wheel_files)
    wheels = [fc for fc in plan.file_changes if isinstance(fc, WheelReference)]
    apply_to_environment(client, ctx, compute_apply_actions(ctx, plan), wheels)
    return wheels


def assert_rescans_clean(client: FakeS3Client):
    ctx = build_context(client, "my-env")
    assert check_wheel_references(ctx).status == FindingStatus.PASS
    replan = compute_plan("2.7.2", ctx.requirements_text, ctx.base_constraints, None, "datadoghq.com", "my-env", ctx.present_wheel_files)
    assert not any(fc.path in ("requirements.txt", "dags/constraints.txt") for fc in replan.file_changes)


def test_2_7_2_apply_uploads_wheels_references_them_and_rescans_clean():
    client = FakeS3Client(WHEEL_ENVIRONMENT, {"requirements.txt": "apache-airflow-providers-openlineage==1.1.0\npandas==2.1.4\n"})

    scan_and_apply(client)

    assert client.objects["dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl"] == FAKE_WHEEL_BYTES
    assert client.objects["dags/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl"] == FAKE_WHEEL_BYTES
    assert client.objects["requirements.txt"].splitlines() == [
        '--constraint "/usr/local/airflow/dags/constraints.txt"',
        "/usr/local/airflow/dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl",
        "pandas==2.1.4",
        "openlineage-integration-common==1.24.2",
        "openlineage-python==1.24.2",
        "openlineage-sql==1.24.2",
        "/usr/local/airflow/dags/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl",
    ]
    assert_rescans_clean(client)


def test_2_7_2_apply_uploads_wheels_that_are_referenced_but_missing_from_s3():
    requirements = (
        "/usr/local/airflow/dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl\n"
        "/usr/local/airflow/dags/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl\n"
        "pandas==2.1.4\n"
    )
    client = FakeS3Client(WHEEL_ENVIRONMENT, {"requirements.txt": requirements})
    assert check_wheel_references(build_context(client, "my-env")).status == FindingStatus.FAIL

    wheels = scan_and_apply(client)

    assert len(wheels) == 2
    assert client.objects["dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl"] == FAKE_WHEEL_BYTES
    new_requirements = client.objects["requirements.txt"]
    assert new_requirements.count("apache_airflow_providers_openlineage-1.14.0") == 1  # no duplicate reference line
    assert new_requirements.count("apache_airflow_providers_common_compat-1.2.2") == 1
    assert_rescans_clean(client)


def test_apply_to_environment_writes_nothing_if_a_wheel_download_isnt_a_wheel(fake_fetch):
    fake_fetch[OPENLINEAGE_WHEEL_URL] = b"<html>not found</html>"
    client = MagicMock()
    ctx = make_context(environment={**ENVIRONMENT, "AirflowVersion": "2.7.2"}, constraints_text=None, base_constraints=BaseConstraints(source="x", text=UPSTREAM_2_7_2_TEXT))
    plan = compute_plan("2.7.2", ctx.requirements_text, ctx.base_constraints, None, "datadoghq.com", "my-env")
    wheels = [fc for fc in plan.file_changes if isinstance(fc, WheelReference)]

    with pytest.raises(RuntimeError, match="didn't return a wheel"):
        apply_to_environment(client, ctx, compute_apply_actions(ctx, plan), wheels)

    client.put_object_bytes.assert_not_called()
    client.put_object_text.assert_not_called()
