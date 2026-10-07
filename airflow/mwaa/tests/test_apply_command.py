# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import uuid
from dataclasses import asdict, replace
from unittest.mock import MagicMock, patch

import pytest

from airflow_shared.reporter import Finding, FindingStatus, Reporter
from mwaa.apply import StaleSessionError
from mwaa.apply_command import run_apply
from mwaa.apply_config import ApplyConfig
from mwaa.plan import PinChange, Plan
from mwaa.session import AppliedStatus, BlockingIssuesError, EnvironmentEntry, ScannedStatus, Session
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
        PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0"),
    ],
)

ALREADY_CONFIGURED_PLAN = Plan(
    upgrade_needed=False, rationale="already configured", source="flagged_version_table", matched_table_entry=None, source_doc="", file_changes=[]
)


def make_client() -> MagicMock:
    client = MagicMock()
    client.latest_version_id.return_value = None
    client.get_environment.return_value = ENVIRONMENT
    client.get_object_text.return_value = "apache-airflow-providers-openlineage==1.4.0\n"
    client.put_object_text.return_value = "v2"
    return client


# what make_client's latest_version_id (None for everything) reports at apply time
UNCHANGED_FILE_VERSIONS = {"requirements.txt": None, "dags/startup.sh": None}


def make_session(plan: Plan = NEEDS_UPGRADE_PLAN, file_versions: dict = UNCHANGED_FILE_VERSIONS) -> Session:
    return Session(
        session_id=SESSION_ID,
        region="us-east-1",
        environments=[EnvironmentEntry(name="my-env", airflow_version="2.8.1", already_configured=False, plan=plan, file_versions=file_versions)],
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
        patch("mwaa.apply_command.select_session_store", return_value=(store, False)),
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
        patch("mwaa.apply_command.select_session_store", return_value=(store, False)),
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
            EnvironmentEntry(name="my-env", airflow_version="2.8.1", already_configured=False, plan=NEEDS_UPGRADE_PLAN, file_versions=UNCHANGED_FILE_VERSIONS),
            EnvironmentEntry(name="other-env", airflow_version="2.8.1", already_configured=False, plan=NEEDS_UPGRADE_PLAN, file_versions=UNCHANGED_FILE_VERSIONS),
        ],
    )
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    reporter = Reporter(workflow_type="mwaa-setup")
    client = make_client()
    store = make_store(session)

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=(store, False)),
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
        patch("mwaa.apply_command.select_session_store", return_value=(store, False)),
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

    with patch("mwaa.apply_command.select_session_store", return_value=(store, False)):
        result = run_apply(config, reporter)

    assert result["applied"] is False
    assert "No plan for 'not-in-session'" in capsys.readouterr().out


def run_confirmed_apply(session: Session, client: MagicMock):
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=True)
    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=(make_store(session), False)),
    ):
        return run_apply(config, Reporter(workflow_type="mwaa-setup"))


@pytest.mark.parametrize(
    "scanned, now",
    [("v1", "v2"), (None, "v1"), ("v1", None)],
    ids=["changed-version", "appeared", "disappeared"],
)
def test_run_apply_writes_nothing_if_a_file_changed_since_scan(scanned, now):
    client = make_client()
    client.latest_version_id.side_effect = lambda bucket, key: now if key == "requirements.txt" else None

    with pytest.raises(StaleSessionError, match="requirements.txt"):
        run_confirmed_apply(make_session(file_versions={"requirements.txt": scanned, "dags/startup.sh": None}), client)

    client.put_object_text.assert_not_called()
    client.put_object_bytes.assert_not_called()
    client.update_environment.assert_not_called()


def test_run_apply_refuses_a_session_without_file_versions():
    client = make_client()

    with pytest.raises(StaleSessionError, match="re-run scan"):
        run_confirmed_apply(make_session(file_versions={}), client)

    client.put_object_text.assert_not_called()


def test_run_apply_refuses_a_plan_that_writes_a_file_with_no_recorded_version():
    client = make_client()

    with pytest.raises(StaleSessionError, match="no recorded version for requirements.txt"):
        run_confirmed_apply(make_session(file_versions={"dags/startup.sh": None}), client)

    client.put_object_text.assert_not_called()


def session_with_issue(status: FindingStatus) -> Session:
    entry = make_session().environments[0]
    return Session(
        session_id=SESSION_ID,
        region="us-east-1",
        environments=[replace(entry, issues=[Finding("unapplied_uploads", status, "requirements.txt has a newer upload")])],
    )


@pytest.mark.parametrize("confirmed", [True, False], ids=["--yes", "dry-run"])
def test_run_apply_refuses_an_environment_with_a_fail_issue_and_writes_nothing(confirmed, capsys):
    client = make_client()
    config = ApplyConfig(session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key="fake-dd-api-key", confirmed=confirmed)

    with (
        patch("mwaa.apply_command.MwaaClient", return_value=client),
        patch("mwaa.apply_command.select_session_store", return_value=(make_store(session_with_issue(FindingStatus.FAIL)), False)),
        pytest.raises(BlockingIssuesError, match="re-run scan"),
    ):
        run_apply(config, Reporter(workflow_type="mwaa-setup"))

    out = capsys.readouterr().out
    assert "requirements.txt has a newer upload" in out  # the issue itself was shown
    assert "Planned changes" not in out
    client.put_object_text.assert_not_called()
    client.put_object_bytes.assert_not_called()
    client.update_environment.assert_not_called()


def test_run_apply_still_applies_with_only_warn_issues(capsys):
    result = run_confirmed_apply(session_with_issue(FindingStatus.WARN), make_client())

    assert result["applied"] is True
    assert "These warnings don't block applying" in capsys.readouterr().out


def test_run_apply_refuses_a_fail_issue_in_an_override_session_too(tmp_path, monkeypatch):
    override_path = tmp_path / "override.json"
    override_path.write_text(json.dumps(asdict(session_with_issue(FindingStatus.FAIL))))
    monkeypatch.setenv(SESSION_OVERRIDE_ENV_VAR, str(override_path))
    client = make_client()

    with pytest.raises(BlockingIssuesError):
        run_confirmed_apply(make_session(), client)

    client.put_object_text.assert_not_called()


def test_run_apply_only_warns_for_an_override_session_without_file_versions(capsys, tmp_path, monkeypatch):
    override_path = tmp_path / "override.json"
    override_path.write_text(json.dumps(asdict(make_session(file_versions={}))))
    monkeypatch.setenv(SESSION_OVERRIDE_ENV_VAR, str(override_path))

    result = run_confirmed_apply(make_session(), make_client())

    assert result["applied"] is True
    assert "can't check that no file changed since it was scanned" in capsys.readouterr().out


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
        patch("mwaa.apply_command.select_session_store", return_value=(store, False)),
    ):
        result = run_apply(config, reporter)

    store.load.assert_not_called()  # the override file is read instead
    assert result["applied"] is True
    store.save.assert_called_once()  # sealing still goes through the selected store
    out = capsys.readouterr().out
    assert f"{SESSION_OVERRIDE_ENV_VAR} is set" in out
