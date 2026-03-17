# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
from unittest.mock import patch

import pytest

from azure_agentless_setup.config import (
    DEFAULT_RESOURCE_GROUP,
    MAX_SCANNER_LOCATIONS,
    parse_config,
)
from azure_agentless_setup.errors import ConfigurationError


VALID_ENV = {
    "DD_API_KEY": "test-api-key",
    "DD_APP_KEY": "test-app-key",
    "DD_SITE": "datadoghq.com",
    "WORKFLOW_ID": "workflow-123",
    "SCANNER_SUBSCRIPTION": "sub-scanner",
    "SCANNER_LOCATIONS": "eastus",
    "SUBSCRIPTIONS_TO_SCAN": "sub-a,sub-b",
}


def with_env(overrides: dict[str, str] = {}, remove: list[str] = []):
    env = {**VALID_ENV, **overrides}
    for key in remove:
        env.pop(key, None)
    return patch.dict(os.environ, env, clear=True)


class TestParseConfigValid:
    def test_minimal_valid_config(self):
        with with_env():
            config = parse_config()

        assert config.api_key == "test-api-key"
        assert config.app_key == "test-app-key"
        assert config.site == "datadoghq.com"
        assert config.workflow_id == "workflow-123"
        assert config.scanner_subscription == "sub-scanner"
        assert config.locations == ["eastus"]
        assert config.subscriptions_to_scan == ["sub-a", "sub-b"]
        assert config.resource_group == DEFAULT_RESOURCE_GROUP
        assert config.state_storage_account is None

    def test_multiple_locations(self):
        with with_env({"SCANNER_LOCATIONS": "eastus,westeurope,southeastasia"}):
            config = parse_config()

        assert config.locations == ["eastus", "westeurope", "southeastasia"]

    def test_custom_resource_group(self):
        with with_env({"SCANNER_RESOURCE_GROUP": "my-custom-rg"}):
            config = parse_config()

        assert config.resource_group == "my-custom-rg"

    def test_custom_state_storage_account(self):
        with with_env({"TF_STATE_STORAGE_ACCOUNT": "mystorageacct"}):
            config = parse_config()

        assert config.state_storage_account == "mystorageacct"

    def test_deduplicates_locations(self):
        with with_env({"SCANNER_LOCATIONS": "eastus,westeurope,eastus"}):
            config = parse_config()

        assert config.locations == ["eastus", "westeurope"]

    def test_deduplicates_subscriptions(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": "sub-a,sub-b,sub-a"}):
            config = parse_config()

        assert config.subscriptions_to_scan == ["sub-a", "sub-b"]

    def test_strips_whitespace(self):
        with with_env({
            "DD_API_KEY": "  key  ",
            "SCANNER_LOCATIONS": " eastus , westeurope ",
            "SUBSCRIPTIONS_TO_SCAN": " sub-a , sub-b ",
        }):
            config = parse_config()

        assert config.api_key == "key"
        assert config.locations == ["eastus", "westeurope"]
        assert config.subscriptions_to_scan == ["sub-a", "sub-b"]


class TestParseConfigDerived:
    def test_all_subscriptions_includes_scanner(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": "sub-a,sub-b"}):
            config = parse_config()

        all_subs = config.all_subscriptions
        assert "sub-scanner" in all_subs
        assert "sub-a" in all_subs
        assert "sub-b" in all_subs

    def test_all_subscriptions_deduplicates_scanner(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": "sub-scanner,sub-a"}):
            config = parse_config()

        assert config.all_subscriptions.count("sub-scanner") == 1

    def test_other_subscriptions_excludes_scanner(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": "sub-scanner,sub-a,sub-b"}):
            config = parse_config()

        assert "sub-scanner" not in config.other_subscriptions
        assert "sub-a" in config.other_subscriptions

    def test_scan_scopes_format(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": "sub-a"}):
            config = parse_config()

        for scope in config.scan_scopes:
            assert scope.startswith("/subscriptions/")


class TestParseConfigErrors:
    def test_missing_required_env_vars(self):
        with with_env(remove=["DD_API_KEY", "DD_SITE"]):
            with pytest.raises(ConfigurationError) as exc:
                parse_config()

        assert "DD_API_KEY" in str(exc.value.detail)
        assert "DD_SITE" in str(exc.value.detail)

    def test_empty_locations(self):
        with with_env({"SCANNER_LOCATIONS": ",,"}):
            with pytest.raises(ConfigurationError) as exc:
                parse_config()
        assert "at least one location" in str(exc.value.detail)

    def test_too_many_locations(self):
        locs = ",".join(f"loc{i}" for i in range(MAX_SCANNER_LOCATIONS + 1))
        with with_env({"SCANNER_LOCATIONS": locs}):
            with pytest.raises(ConfigurationError) as exc:
                parse_config()
        assert "cannot exceed" in str(exc.value.detail)

    def test_empty_subscriptions(self):
        with with_env({"SUBSCRIPTIONS_TO_SCAN": ",,"}):
            with pytest.raises(ConfigurationError) as exc:
                parse_config()
        assert "at least one subscription" in str(exc.value.detail)
