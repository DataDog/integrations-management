# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import uuid

import pytest

from mwaa.apply_config import parse_apply_config
from mwaa.config import ConfigError

SESSION_ID = str(uuid.uuid4())
BASE_ARGS = [
    "--session-id", SESSION_ID, "--name", "my-env", "--region", "us-east-1",
    "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com",
]  # fmt: skip


def test_parse_apply_config_defaults_to_dry_run():
    config = parse_apply_config(BASE_ARGS)
    assert config.confirmed is False
    assert config.offline is False


def test_parse_apply_config_yes_flag_sets_confirmed():
    config = parse_apply_config([*BASE_ARGS, "--yes"])
    assert config.confirmed is True


def test_parse_apply_config_offline_does_not_require_dd_site(monkeypatch):
    monkeypatch.delenv("DD_SITE", raising=False)
    config = parse_apply_config(
        ["--session-id", SESSION_ID, "--name", "my-env", "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key", "--offline"]
    )
    assert config.offline is True
    assert config.dd_site is None


def test_parse_apply_config_raises_when_dd_site_missing_and_not_offline(monkeypatch):
    monkeypatch.delenv("DD_SITE", raising=False)
    with pytest.raises(ConfigError, match="Datadog site is required"):
        parse_apply_config(["--session-id", SESSION_ID, "--name", "my-env", "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key"])


def test_parse_apply_config_raises_when_session_id_missing():
    with pytest.raises(ConfigError, match="--session-id is required"):
        parse_apply_config(["--name", "my-env", "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com"])


def test_parse_apply_config_raises_when_session_id_not_a_uuid():
    with pytest.raises(ConfigError, match="must be a valid UUID"):
        parse_apply_config(
            ["--session-id", "not-a-uuid", "--name", "my-env", "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com"]
        )


def test_parse_apply_config_raises_when_name_missing(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)
    with pytest.raises(ConfigError, match="Environment name is required"):
        parse_apply_config(["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com"])


def test_parse_apply_config_raises_when_region_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ConfigError, match="Region is required"):
        parse_apply_config(["--session-id", SESSION_ID, "--name", "my-env", "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com"])


def test_parse_apply_config_raises_when_dd_api_key_missing(monkeypatch):
    monkeypatch.delenv("DD_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="Datadog API key is required"):
        parse_apply_config(["--session-id", SESSION_ID, "--name", "my-env", "--region", "us-east-1", "--dd-site", "datadoghq.com"])


def test_parse_apply_config_still_requires_name_and_region_when_session_override_set(monkeypatch):
    """SESSION_OVERRIDE_PATH swaps out where the Session comes from, not --name/--region."""
    monkeypatch.setenv("SESSION_OVERRIDE_PATH", "/tmp/does-not-need-to-exist.json")
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)

    with pytest.raises(ConfigError, match="Environment name is required"):
        parse_apply_config(["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-api-key", "fake-dd-api-key", "--dd-site", "datadoghq.com"])
