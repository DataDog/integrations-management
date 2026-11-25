# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""No Datadog API key is ever printed in full -- see diff_preview.mask_secrets."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from airflow_shared.reporter import Reporter
from mwaa import main as cli
from mwaa.apply_command import run_apply
from mwaa.apply_config import ApplyConfig
from mwaa.diff_preview import mask_secrets
from mwaa.probe import build_context
from mwaa.scan import run_scan
from mwaa.scan_config import ScanConfig
from mwaa.session import build_session
from mwaa.session_store import SessionStore

from .conftest import FakeS3Client

SESSION_ID = str(uuid.uuid4())
NEW_KEY = "aaaabbbbccccddddeeeeffff00001111"  # synthetic, the key passed to the CLI
OLD_KEY = "0123456789abcdef0123456789abcdef"  # synthetic, the stale one already in the script
ENVIRONMENT = {
    "Name": "my-env",
    "AirflowVersion": "2.10.3",
    "SourceBucketArn": "arn:aws:s3:::my-bucket",
    "DagS3Path": "dags",
    "RequirementsS3Path": "requirements.txt",
    "StartupScriptS3Path": "dags/startup.sh",
    "ExecutionRoleArn": "arn:aws:iam::123456789012:role/r",
    "AirflowConfigurationOptions": {},
}
STARTUP = (
    "#!/bin/sh\n"
    "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.eu\n"  # another site's: the key gets replaced
    f"export OPENLINEAGE_API_KEY={OLD_KEY}  # the old one\n"
)


def client() -> FakeS3Client:
    fake = FakeS3Client(ENVIRONMENT, {"requirements.txt": "apache-airflow-providers-openlineage\n", "dags/startup.sh": STARTUP})
    fake.list_environment_names = lambda: ["my-env"]
    return fake


def store_with_session(fake: FakeS3Client) -> MagicMock:
    store = MagicMock(spec=SessionStore)
    store.load.return_value = build_session(SESSION_ID, "us-east-1", "datadoghq.com", [build_context(fake, "my-env")])
    return store


def apply_config(confirmed: bool) -> ApplyConfig:
    return ApplyConfig(
        session_id=SESSION_ID, environment_name="my-env", region="us-east-1", dd_api_key=NEW_KEY, dd_site="datadoghq.com", confirmed=confirmed
    )


def assert_no_full_key(capsys):
    captured = capsys.readouterr()
    for key in (NEW_KEY, OLD_KEY):
        assert key not in captured.out and key not in captured.err
    return captured


ESCAPED_TRANSPORT_STARTUP = (
    "#!/bin/sh\n"
    'export AIRFLOW__OPENLINEAGE__TRANSPORT="{\\"type\\": \\"http\\", \\"url\\": \\"https://data-obs-intake.datadoghq.eu\\", '
    f'\\"auth\\": {{\\"type\\": \\"api_key\\", \\"apiKey\\": \\"{OLD_KEY}\\"}}}}"\n'
    f"export DD_API_KEY={OLD_KEY}\n"  # unchanged, but a diff's context line
)


def test_apply_preview_masks_an_escaped_json_transport_key_and_context_lines(capsys):
    fake = client()
    fake.objects["dags/startup.sh"] = ESCAPED_TRANSPORT_STARTUP
    with patch("mwaa.apply_command.MwaaClient", return_value=fake), patch("mwaa.apply_command.select_session_store", return_value=(store_with_session(fake), False)):
        run_apply(apply_config(confirmed=False), Reporter(workflow_type="mwaa-setup"), input_func=lambda _: "n", is_terminal=lambda: True)

    out = assert_no_full_key(capsys).out
    assert '\\"apiKey\\": \\"****cdef\\"' in out  # the old transport on the diff's - line
    assert '"apiKey": "****1111"' in out  # the corrected one on its + line
    assert "export DD_API_KEY=****cdef" in out


def test_apply_preview_masks_the_new_and_old_key_but_writes_the_real_one(capsys):
    fake = client()
    with patch("mwaa.apply_command.MwaaClient", return_value=fake), patch("mwaa.apply_command.select_session_store", return_value=(store_with_session(fake), False)):
        run_apply(apply_config(confirmed=False), Reporter(workflow_type="mwaa-setup"), input_func=lambda _: "n", is_terminal=lambda: True)

    out = assert_no_full_key(capsys).out
    assert "-export OPENLINEAGE_API_KEY=****cdef  # the old one" in out
    assert "+export OPENLINEAGE_API_KEY=****1111  # the old one" in out
    assert OLD_KEY in fake.objects["dags/startup.sh"]  # nothing was written


def test_apply_success_prints_no_key_and_uploads_the_real_one(capsys):
    fake = client()
    with patch("mwaa.apply_command.MwaaClient", return_value=fake), patch("mwaa.apply_command.select_session_store", return_value=(store_with_session(fake), False)):
        run_apply(apply_config(confirmed=True), Reporter(workflow_type="mwaa-setup"))

    out = assert_no_full_key(capsys).out
    assert f"export OPENLINEAGE_API_KEY={NEW_KEY}  # the old one" in fake.objects["dags/startup.sh"]
    assert out.endswith(
        "UpdateEnvironment called -- the environment will restart (usually 20-30 minutes).\n"
        "The update continues in AWS; you can close CloudShell.\n"
        "Return to the Configure Airflow tab to watch for your first events, or open:\n"
        f"  https://app.datadoghq.com/data-obs/configure/airflow?session_id={SESSION_ID}&step=run-a-dag&env=my-env\n"
    )


ARGV = ["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-site", "datadoghq.com", "--dd-api-key", NEW_KEY]
KEY_CARRYING_ERROR = RuntimeError(f"intake said no to DD-API-KEY {NEW_KEY}")


def test_an_apply_step_failing_with_the_key_prints_it_masked_everywhere(capsys):
    fake = client()
    with (
        patch("mwaa.apply_command.MwaaClient", return_value=fake),
        patch("mwaa.apply_command.select_session_store", return_value=(store_with_session(fake), False)),
        patch("mwaa.apply_command.apply_to_environment", side_effect=KEY_CARRYING_ERROR),
        pytest.raises(SystemExit),
    ):
        cli._run_apply(ARGV + ["--name", "my-env", "--yes"])

    captured = assert_no_full_key(capsys)
    assert "[apply_changes] failed: intake said no to DD-API-KEY ****1111" in captured.out
    assert "Apply failed: intake said no to DD-API-KEY ****1111" in captured.err


def test_a_scan_step_failing_with_the_key_prints_it_masked_everywhere(capsys):
    with (
        patch("mwaa.scan.MwaaClient", return_value=client()),
        patch("mwaa.scan.select_session_store", return_value=(MagicMock(spec=SessionStore), False)),
        patch("mwaa.scan.build_session", side_effect=KEY_CARRYING_ERROR),
        pytest.raises(SystemExit),
    ):
        cli._run_scan(ARGV)

    captured = assert_no_full_key(capsys)
    assert "[build_session] failed: intake said no to DD-API-KEY ****1111" in captured.out


def test_interactive_scan_preview_masks_both_keys(capsys):
    config = ScanConfig(session_id=SESSION_ID, region="us-east-1", dd_site="datadoghq.com", dd_api_key=NEW_KEY, interactive=True)
    answers = iter(["1", "n"])

    with patch("mwaa.scan.MwaaClient", return_value=client()), patch("mwaa.scan.select_session_store", return_value=(MagicMock(spec=SessionStore), False)):
        run_scan(config, Reporter(workflow_type="mwaa-setup"), input_func=lambda _: next(answers))

    out = assert_no_full_key(capsys).out
    assert "+export OPENLINEAGE_API_KEY=****1111" in out


def test_mask_secrets_masks_keys_in_exports_and_transport_json_and_leaves_the_rest():
    text = (
        "+export OPENLINEAGE_API_KEY='0123456789abcdef0123456789abcdef'\n"
        """+export AIRFLOW__OPENLINEAGE__TRANSPORT='{"url": "https://x", "auth": {"type": "api_key", "apiKey": "fedcba9876543210fedcba9876543210"}}'\n"""
        "-export OPENLINEAGE_API_KEY=$(aws secretsmanager get-secret-value --secret-id dd)\n"
        "-export OPENLINEAGE_API_KEY=${DD_KEY}\n"
        "+export OPENLINEAGE_API_KEY=<DD_API_KEY>\n"
        "+export OPENLINEAGE_URL=https://data-obs-intake.datad0g.com\n"
        '-export AIRFLOW__OPENLINEAGE__TRANSPORT="{\\"auth\\":{\\"type\\":\\"api_key\\",\\"apiKey\\":\\"abcdef0123456789abcdef0123456789\\"}}"\n'
        " export DD_API_KEY=abcdef0123456789abcdef0123456789\n"
    )

    assert mask_secrets(text, None) == (
        "+export OPENLINEAGE_API_KEY='****cdef'\n"
        """+export AIRFLOW__OPENLINEAGE__TRANSPORT='{"url": "https://x", "auth": {"type": "api_key", "apiKey": "****3210"}}'\n"""
        "-export OPENLINEAGE_API_KEY=$(aws secretsmanager get-secret-value --secret-id dd)\n"
        "-export OPENLINEAGE_API_KEY=${DD_KEY}\n"
        "+export OPENLINEAGE_API_KEY=<DD_API_KEY>\n"
        "+export OPENLINEAGE_URL=https://data-obs-intake.datad0g.com\n"
        '-export AIRFLOW__OPENLINEAGE__TRANSPORT="{\\"auth\\":{\\"type\\":\\"api_key\\",\\"apiKey\\":\\"****6789\\"}}"\n'
        " export DD_API_KEY=****6789\n"
    )


def test_mask_secrets_masks_the_given_key_anywhere():
    assert mask_secrets(f"failed with key {NEW_KEY}.", NEW_KEY) == "failed with key ****1111."


class _Pipe:
    """A stream that, like a pipe, only shows what's written once it's flushed."""

    def __init__(self, name, shown):
        self.name, self.shown, self.buffer = name, shown, ""

    def write(self, text):
        self.buffer += text
        return len(text)

    def flush(self):
        if self.buffer:
            self.shown.append((self.name, self.buffer))
            self.buffer = ""


def test_not_applied_comes_after_the_preview_even_when_stdout_is_buffered(monkeypatch):
    shown = []
    out, err = _Pipe("out", shown), _Pipe("err", shown)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    fake = client()
    monkeypatch.setattr("mwaa.apply_command.MwaaClient", lambda region: fake)
    monkeypatch.setattr("mwaa.apply_command.select_session_store", lambda *args: (store_with_session(fake), False))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    with pytest.raises(SystemExit):
        cli._run_apply(ARGV + ["--name", "my-env"])
    err.flush()
    out.flush()

    assert [name for name, _ in shown][:2] == ["out", "err"]
    assert "Planned changes:" in shown[0][1]
    assert "Not applied: confirm interactively or pass --yes." in shown[1][1]
