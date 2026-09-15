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
    with pytest.raises(ConfigError, match="Environment name is required"):
        parse_apply_config(["--region", "us-east-1"])
