# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import uuid
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from airflow_shared.reporter import Reporter
from mwaa.apply_command import run_apply
from mwaa.apply_config import ApplyConfig
from mwaa.plan import FileChange, Plan, PinDiff
from mwaa.session import AppliedStatus, EnvironmentEntry, ScannedStatus, Session
from mwaa.session_override import SESSION_OVERRIDE_ENV_VAR
from mwaa.session_store import SessionStore

SESSION_ID = str(uuid.uuid4())

ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.8.1",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": None,
}

NEEDS_UPGRADE_PLAN = Plan(
    upgrade_needed=True,
    rationale="Airflow 2.8.1 is flagged",
    source="flagged_version_table",
    matched_table_entry=None,
    source_doc="",
    file_changes=[
        FileChange(
            path="requirements.txt",
            action="update",
            pin_diff=[PinDiff("apache-airflow-providers-openlineage", "1.4.0", "1.14.0")],
        )
    ],
)

ALREADY_CONFIGURED_PLAN = Plan(
    upgrade_needed=False, rationale="already configured", source="flagged_version_table", matched_table_entry=None, source_doc="", file_changes=[]
)


def make_client() -> MagicMock:
    client = MagicMock()
    client.get_environment.return_value = ENVIRONMENT
    client.get_object_text.return_value = "apache-airflow-providers-openlineage==1.4.0\n"
    client.put_object_text.return_value = "v2"
    return client


def make_session(plan: Plan = NEEDS_UPGRADE_PLAN) -> Session:
    return Session(
        session_id=SESSION_ID,
        region="us-east-1",
        environments=[EnvironmentEntry(name="my-env", airflow_version="2.8.1", already_configured=False, plan=plan)],
    )


def make_store(session: Session = None) -> MagicMock:
    store = MagicMock(spec=SessionStore)
    if session is not None:
        store.load.return_value = session
    return store


def test_run_apply_without_yes_does_not_call_put_object(capsys):
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=False)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store(make_session())

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=store),
    ):
        result = run_apply(config, reporter)

    client.put_object_text.assert_not_called()
    client.update_environment.assert_not_called()
    store.save.assert_not_called()  # a dry run never seals anything
    assert result["applied"] is False
    assert "Dry run only" in capsys.readouterr().out


def test_run_apply_with_yes_uploads_files(capsys):
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store(make_session())

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=store),
    ):
        result = run_apply(config, reporter)

    assert client.put_object_text.call_count == len(result["uploads"])
    client.update_environment.assert_called_once()
    assert result["applied"] is True
    assert "UpdateEnvironment called" in capsys.readouterr().out

    store.save.assert_called_once()
    sealed_session = store.save.call_args.args[0]
    assert sealed_session.find("my-env").status == AppliedStatus()


def test_run_apply_seals_only_the_applied_environment(capsys):
    """A session can cover several environments -- sealing one must not touch the others."""
    session = Session(
        session_id=SESSION_ID,
        region="us-east-1",
        environments=[
            EnvironmentEntry(name="my-env", airflow_version="2.8.1", already_configured=False, plan=NEEDS_UPGRADE_PLAN),
            EnvironmentEntry(name="other-env", airflow_version="2.8.1", already_configured=False, plan=NEEDS_UPGRADE_PLAN),
        ],
    )
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store(session)

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=store),
    ):
        run_apply(config, reporter)

    sealed_session = store.save.call_args.args[0]
    assert sealed_session.find("my-env").status == AppliedStatus()
    assert sealed_session.find("other-env").status == ScannedStatus()


def test_run_apply_reports_nothing_to_do_when_already_configured(capsys):
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store(make_session(ALREADY_CONFIGURED_PLAN))

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=store),
    ):
        result = run_apply(config, reporter)

    assert result["applied"] is False
    assert result["uploads"] == []
    client.put_object_text.assert_not_called()
    store.save.assert_not_called()
    assert "already fully configured" in capsys.readouterr().out


def test_run_apply_reports_when_name_not_in_session(capsys):
    config = ApplyConfig(session_id=SESSION_ID, environment_name="not-in-session", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    store = make_store(make_session())

    with patch("mwaa.apply_command.select_session_store", return_value=store):
        result = run_apply(config, reporter)

    assert result["applied"] is False
    assert "No plan for 'not-in-session'" in capsys.readouterr().out


def test_run_apply_uses_session_override_when_env_var_set(capsys, tmp_path, monkeypatch):
    override_session = make_session()
    override_path = tmp_path / "override.json"
    override_path.write_text(json.dumps(asdict(override_session)))
    monkeypatch.setenv(SESSION_OVERRIDE_ENV_VAR, str(override_path))

    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store()

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=store),
    ):
        result = run_apply(config, reporter)

    store.load.assert_not_called()  # the override file is read instead
    assert result["applied"] is True
    store.save.assert_called_once()  # sealing still goes through the selected store
    out = capsys.readouterr().out
    assert f"{SESSION_OVERRIDE_ENV_VAR} is set" in out
