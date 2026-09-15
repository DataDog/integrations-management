# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.config import ConfigError
from mwaa.scan_config import parse_scan_config


def test_parse_scan_config_from_args():
    config = parse_scan_config(["--region", "us-east-1", "--dd-site", "datad0g.com"])
    assert config.region == "us-east-1"
    assert config.dd_site == "datad0g.com"


def test_parse_scan_config_defaults_dd_site():
    config = parse_scan_config(["--region", "us-east-1"])
    assert config.dd_site == "datadoghq.com"


def test_parse_scan_config_falls_back_to_env_vars(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("DD_SITE", "datad0g.com")
    config = parse_scan_config([])
    assert config.region == "eu-west-1"
    assert config.dd_site == "datad0g.com"


def test_parse_scan_config_raises_when_region_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ConfigError, match="Region is required"):
        parse_scan_config([])
