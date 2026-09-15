# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.config import ConfigError, parse_config


def test_parse_config_from_args():
    config = parse_config(["--name", "my-env", "--region", "us-east-1"])
    assert config.environment_name == "my-env"
    assert config.region == "us-east-1"


def test_parse_config_falls_back_to_env_vars(monkeypatch):
    monkeypatch.setenv("MWAA_ENVIRONMENT_NAME", "env-from-var")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    config = parse_config([])
    assert config.environment_name == "env-from-var"
    assert config.region == "eu-west-1"


def test_parse_config_args_override_env_vars(monkeypatch):
    monkeypatch.setenv("MWAA_ENVIRONMENT_NAME", "env-from-var")
    config = parse_config(["--name", "env-from-arg", "--region", "us-east-1"])
    assert config.environment_name == "env-from-arg"


def test_parse_config_raises_when_name_missing(monkeypatch):
    monkeypatch.delenv("MWAA_ENVIRONMENT_NAME", raising=False)
    with pytest.raises(ConfigError, match="Environment name is required"):
        parse_config(["--region", "us-east-1"])


def test_parse_config_raises_when_region_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ConfigError, match="Region is required"):
        parse_config(["--name", "my-env"])
