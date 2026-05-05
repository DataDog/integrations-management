# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for main.cmd_deploy helpers, focused on the resource-group
validation that runs before any infrastructure mutation."""

from unittest.mock import patch

import pytest

from azure_agentless_setup.config import Config
from azure_agentless_setup.errors import ConfigurationError, SetupError
from azure_agentless_setup.main import _check_existing_deployment
from azure_agentless_setup.metadata import (
    DeploymentMetadata,
    MetadataReadResult,
    MetadataReadStatus,
)


def _make_config(resource_group: str = "rg-current", state_storage_account=None) -> Config:
    return Config(
        api_key="key",
        app_key="app",
        site="datadoghq.com",
        workflow_id="wf",
        scanner_subscription="sub-scanner",
        locations=["eastus"],
        subscriptions_to_scan=["sub-a"],
        resource_group=resource_group,
        state_storage_account=state_storage_account,
    )


def _present(resource_group):
    return MetadataReadResult(
        MetadataReadStatus.PRESENT,
        metadata=DeploymentMetadata(
            scanner_subscription="sub-scanner",
            resource_group=resource_group,
            locations=["eastus"],
            subscriptions_to_scan=["sub-scanner"],
            created_at="t0",
            modified_at="t0",
        ),
        etag="etag-1",
    )


class TestCheckExistingDeployment:
    @patch("azure_agentless_setup.main.find_storage_account_rg", return_value=None)
    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_matching_rg_returns_result(self, mock_read, mock_find):
        mock_read.return_value = _present("rg-current")

        result = _check_existing_deployment(_make_config(), "datadog-acct")

        assert result.status == MetadataReadStatus.PRESENT
        mock_find.assert_not_called()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_mismatched_rg_raises(self, mock_read, mock_find):
        mock_read.return_value = _present("rg-original")

        with pytest.raises(ConfigurationError) as exc:
            _check_existing_deployment(_make_config(resource_group="rg-other"), "datadog-acct")

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail
        # short-circuits before the SA lookup
        mock_find.assert_not_called()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_error_status_raises(self, mock_read, mock_find):
        mock_read.return_value = MetadataReadResult(
            MetadataReadStatus.ERROR, error_detail="auth boom"
        )

        with pytest.raises(SetupError) as exc:
            _check_existing_deployment(_make_config(), "datadog-acct")

        assert "auth boom" in exc.value.detail
        mock_find.assert_not_called()

    @patch(
        "azure_agentless_setup.main.find_storage_account_rg",
        return_value="rg-original",
    )
    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_but_sa_in_other_rg_raises(self, mock_read, mock_find):
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)

        with pytest.raises(ConfigurationError) as exc:
            _check_existing_deployment(_make_config(resource_group="rg-other"), "datadog-acct")

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail

    @patch("azure_agentless_setup.main.find_storage_account_rg", return_value=None)
    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_first_deploy_returns_missing(self, mock_read, mock_find):
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)

        result = _check_existing_deployment(_make_config(), "datadog-acct")

        assert result.status == MetadataReadStatus.MISSING
        mock_find.assert_called_once()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_with_custom_sa_skips_find(self, mock_read, mock_find):
        # Custom SA: ensure_state_storage already validates the SA's RG, so
        # the MISSING branch must NOT call find_storage_account_rg.
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)
        config = _make_config(state_storage_account="myacct")

        result = _check_existing_deployment(config, "myacct")

        assert result.status == MetadataReadStatus.MISSING
        mock_find.assert_not_called()
