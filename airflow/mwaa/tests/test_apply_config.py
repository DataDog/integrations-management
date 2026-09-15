# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.apply_config import parse_apply_config
from mwaa.config import ConfigError


def test_parse_apply_config_defaults_to_dry_run():
    config = parse_apply_config(["--name", "my-env", "--region", "us-east-1"])
    assert config.confirmed is False


def test_parse_apply_config_yes_flag_sets_confirmed():
    config = parse_apply_config(["--name", "my-env", "--region", "us-east-1", "--yes"])
    assert config.confirmed is True


def test_parse_apply_config_raises_when_name_missing(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("PLAN_OVERRIDE_PATH", raising=False)
    with pytest.raises(ConfigError, match="Environment name is required"):
        parse_apply_config(["--region", "us-east-1"])


def test_parse_apply_config_skips_name_and_region_check_when_plan_override_set(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("PLAN_OVERRIDE_PATH", "/tmp/does-not-need-to-exist.json")

    config = parse_apply_config(["--yes"])

    assert config.environment_name is None
    assert config.region is None
    assert config.confirmed is True


def test_parse_apply_config_interactive_flag(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)

    config = parse_apply_config(["--region", "us-east-1", "--interactive"])

    assert config.interactive is True
    assert config.dry_run is False


def test_parse_apply_config_interactive_dry_run_flag():
    config = parse_apply_config(["--region", "us-east-1", "--interactive", "--dry-run"])

    assert config.interactive is True
    assert config.dry_run is True


def test_parse_apply_config_does_not_require_name_when_interactive(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("PLAN_OVERRIDE_PATH", raising=False)

    config = parse_apply_config(["--region", "us-east-1", "--interactive"])

    assert config.environment_name is None


def test_parse_apply_config_still_requires_region_when_interactive(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("PLAN_OVERRIDE_PATH", raising=False)

    with pytest.raises(ConfigError, match="Region is required"):
        parse_apply_config(["--interactive"])
