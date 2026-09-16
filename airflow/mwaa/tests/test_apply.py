# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

import pytest

from mwaa.apply import compute_apply_actions, apply_to_environment, real_key_for_path
from mwaa.checks import ProbeContext
from mwaa.plan import compute_plan

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
    return ProbeContext(**defaults)


def test_compute_apply_actions_patches_requirements_and_constraints():
    ctx = make_context()
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.constraints_text, ctx.startup_script_text, "datadoghq.com", "fake-dd-api-key")

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
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.constraints_text, ctx.startup_script_text, "datadoghq.com", "fake-dd-api-key")

    uploads = compute_apply_actions(ctx, plan)

    assert len(uploads) == 1
    assert uploads[0].path == "dags/startup.sh"
    assert "OPENLINEAGE_API_KEY=fake-dd-api-key" in uploads[0].content


def test_compute_apply_actions_rejects_unknown_path():
    from mwaa.plan import FileChange, Plan

    plan = Plan(
        upgrade_needed=True,
        rationale="",
        source="flagged_version_table",
        matched_table_entry=None,
        source_doc="",
        file_changes=[FileChange(path="somewhere/else.txt", action="update")],
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
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
    )
    plan = compute_plan("3.0.6", ctx.requirements_text, ctx.constraints_text, ctx.startup_script_text, "datadoghq.com", "fake-dd-api-key")
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
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.constraints_text, ctx.startup_script_text, "datadoghq.com", "fake-dd-api-key")
    uploads = compute_apply_actions(ctx, plan)

    result = apply_to_environment(client, ctx, uploads)

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

    result = apply_to_environment(client, ctx, uploads)

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
    plan = compute_plan("2.8.1", ctx.requirements_text, ctx.constraints_text, ctx.startup_script_text, "datadoghq.com", "fake-dd-api-key")
    uploads = compute_apply_actions(ctx, plan)

    result = apply_to_environment(client, ctx, uploads)

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
