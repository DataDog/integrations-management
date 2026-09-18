# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import uuid

import pytest

from mwaa.config import ConfigError
from mwaa.scan_config import parse_scan_config

SESSION_ID = str(uuid.uuid4())
DD_API_KEY_ARGS = ["--dd-api-key", "fake-dd-api-key"]
BASE_ARGS = ["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-site", "datadoghq.com"] + DD_API_KEY_ARGS


def test_parse_scan_config_from_args():
    config = parse_scan_config(
        ["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-site", "datad0g.com"] + DD_API_KEY_ARGS
    )
    assert config.session_id == SESSION_ID
    assert config.region == "us-east-1"
    assert config.dd_site == "datad0g.com"
    assert config.dd_api_key == "fake-dd-api-key"
    assert config.offline is False


def test_parse_scan_config_offline_does_not_require_dd_site(monkeypatch):
    monkeypatch.delenv("DD_SITE", raising=False)
    config = parse_scan_config(["--session-id", SESSION_ID, "--region", "us-east-1", "--offline"] + DD_API_KEY_ARGS)
    assert config.offline is True
    assert config.dd_site == "datadoghq.com"  # only ever rendered into a local preview


def test_parse_scan_config_raises_when_dd_site_missing_and_not_offline(monkeypatch):
    monkeypatch.delenv("DD_SITE", raising=False)
    with pytest.raises(ConfigError, match="Datadog site is required"):
        parse_scan_config(["--session-id", SESSION_ID, "--region", "us-east-1"] + DD_API_KEY_ARGS)


def test_parse_scan_config_falls_back_to_region_env_var(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("DD_SITE", "datad0g.com")
    config = parse_scan_config(["--session-id", SESSION_ID] + DD_API_KEY_ARGS)
    assert config.region == "eu-west-1"
    assert config.dd_site == "datad0g.com"


def test_parse_scan_config_dd_api_key_falls_back_to_env_var(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "env-dd-api-key")
    config = parse_scan_config(["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-site", "datadoghq.com"])
    assert config.dd_api_key == "env-dd-api-key"


def test_parse_scan_config_interactive_and_dry_run_flags():
    config = parse_scan_config(BASE_ARGS + ["--interactive", "--dry-run"])
    assert config.interactive is True
    assert config.dry_run is True


def test_parse_scan_config_interactive_defaults_false():
    config = parse_scan_config(BASE_ARGS)
    assert config.interactive is False
    assert config.dry_run is False


def test_parse_scan_config_raises_when_region_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ConfigError, match="Region is required"):
        parse_scan_config(["--session-id", SESSION_ID, "--dd-site", "datadoghq.com"] + DD_API_KEY_ARGS)


def test_parse_scan_config_raises_when_session_id_missing():
    with pytest.raises(ConfigError, match="--session-id is required"):
        parse_scan_config(["--region", "us-east-1", "--dd-site", "datadoghq.com"] + DD_API_KEY_ARGS)


def test_parse_scan_config_raises_when_session_id_not_a_uuid():
    with pytest.raises(ConfigError, match="must be a valid UUID"):
        parse_scan_config(["--session-id", "not-a-uuid", "--region", "us-east-1", "--dd-site", "datadoghq.com"] + DD_API_KEY_ARGS)


def test_parse_scan_config_raises_when_dd_api_key_missing(monkeypatch):
    monkeypatch.delenv("DD_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="Datadog API key is required"):
        parse_scan_config(["--session-id", SESSION_ID, "--region", "us-east-1", "--dd-site", "datadoghq.com"])
