# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.errors import StorageAccountError
from azure_agentless_setup.state_storage import (
    CONTAINER_NAME,
    get_storage_account_name,
    ensure_resource_group,
    ensure_state_storage,
)


class TestGetStorageAccountName:
    def test_deterministic(self):
        name1 = get_storage_account_name("sub-123")
        name2 = get_storage_account_name("sub-123")
        assert name1 == name2

    def test_different_subs_produce_different_names(self):
        name1 = get_storage_account_name("sub-aaa")
        name2 = get_storage_account_name("sub-bbb")
        assert name1 != name2

    def test_within_azure_length_limit(self):
        name = get_storage_account_name("a-very-long-subscription-id-that-is-a-uuid")
        assert len(name) <= 24

    def test_lowercase_alphanumeric_only(self):
        name = get_storage_account_name("sub-123")
        assert name.isalnum() or all(c.isalnum() for c in name)
        assert name == name.lower()


class TestEnsureResourceGroup:
    @patch("azure_agentless_setup.state_storage.execute")
    def test_skips_creation_when_exists(self, mock_execute):
        mock_execute.return_value = '{"name": "my-rg"}'

        ensure_resource_group("my-rg", "eastus", "sub-123")

        mock_execute.assert_called_once()
        args = mock_execute.call_args
        assert "group" in str(args) and "show" in str(args)

    @patch("azure_agentless_setup.state_storage.execute")
    def test_creates_when_not_exists(self, mock_execute):
        mock_execute.side_effect = ["", ""]

        ensure_resource_group("my-rg", "eastus", "sub-123")

        assert mock_execute.call_count == 2
        second_call = str(mock_execute.call_args_list[1])
        assert "group" in second_call and "create" in second_call

    @patch("azure_agentless_setup.state_storage.execute")
    def test_raises_on_create_failure(self, mock_execute):
        mock_execute.side_effect = ["", RuntimeError("creation failed")]

        with pytest.raises(StorageAccountError) as exc:
            ensure_resource_group("my-rg", "eastus", "sub-123")

        assert "Failed to create resource group" in exc.value.message


class TestEnsureStateStorage:
    def _make_config(self, state_storage_account=None):
        config = MagicMock()
        config.scanner_subscription = "sub-scanner"
        config.locations = ["eastus"]
        config.resource_group = "my-rg"
        config.state_storage_account = state_storage_account
        return config

    def _make_reporter(self):
        reporter = MagicMock()
        return reporter

    @patch("azure_agentless_setup.state_storage.create_container")
    @patch("azure_agentless_setup.state_storage.container_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.ensure_resource_group")
    def test_existing_account_reused(self, mock_rg, mock_sa_exists, mock_c_exists, mock_create_c):
        config = self._make_config()
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        assert result == get_storage_account_name("sub-scanner")
        mock_rg.assert_called_once()
        mock_create_c.assert_not_called()

    @patch("azure_agentless_setup.state_storage.create_container")
    @patch("azure_agentless_setup.state_storage.container_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.create_storage_account")
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.ensure_resource_group")
    def test_creates_account_and_container(self, mock_rg, mock_sa_exists, mock_sa_create, mock_c_exists, mock_create_c):
        config = self._make_config()
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        mock_sa_create.assert_called_once()
        mock_create_c.assert_called_once()
        assert result == get_storage_account_name("sub-scanner")

    @patch("azure_agentless_setup.state_storage.container_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=True)
    def test_custom_account_used(self, mock_sa_exists, mock_c_exists):
        config = self._make_config(state_storage_account="mycustomacct")
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        assert result == "mycustomacct"
        mock_sa_exists.assert_called_once_with("mycustomacct", "my-rg")

    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=False)
    def test_custom_account_not_found_raises(self, mock_sa_exists):
        config = self._make_config(state_storage_account="missing-acct")
        reporter = self._make_reporter()
        reporter.fatal.side_effect = StorageAccountError("not found")

        with pytest.raises(StorageAccountError):
            ensure_state_storage(config, reporter)

        reporter.fatal.assert_called_once()
