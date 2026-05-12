# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.errors import StorageAccountError
from azure_agentless_setup.state_storage import (
    ensure_resource_group,
    ensure_state_storage,
    find_agentless_resource_groups,
    get_storage_account_name,
)


class TestGetStorageAccountName:
    def test_respects_azure_constraints(self):
        # Azure SA names: 3-24 chars, lowercase alphanumeric, globally
        # unique. install_id is a 12-char lowercase hex; prefixed with
        # "datadog" we land at 19 chars and stay within constraints.
        name = get_storage_account_name("0123456789ab")
        assert name == "datadog0123456789ab"
        assert 3 <= len(name) <= 24
        assert name == name.lower()
        assert name.isalnum()


class TestEnsureResourceGroup:
    @patch("azure_agentless_setup.state_storage.execute")
    def test_skips_creation_when_exists(self, mock_execute):
        mock_execute.return_value = '{"name": "my-rg"}'

        ensure_resource_group("my-rg", "eastus", "sub-123")

        mock_execute.assert_called_once()
        args = mock_execute.call_args
        assert "group" in str(args) and "show" in str(args)

    @patch("azure_agentless_setup.state_storage.execute")
    def test_creates_when_not_exists_and_tags_it(self, mock_execute):
        # First call: az group show (returns empty → does not exist).
        # Second call: az group create — must include the agentless marker
        # tag so tag-based discovery can find this install on a later run.
        mock_execute.side_effect = ["", ""]

        ensure_resource_group("my-rg", "eastus", "sub-123")

        assert mock_execute.call_count == 2
        create_call = str(mock_execute.call_args_list[1])
        assert "group" in create_call and "create" in create_call
        assert "DatadogAgentlessScanner=true" in create_call

    @patch("azure_agentless_setup.state_storage.execute")
    def test_existing_rg_is_not_retagged(self, mock_execute):
        """Pre-existing resource groups (e.g. admin-provisioned) must not be
        retagged: the user may be using them for other workloads."""
        mock_execute.return_value = '{"name": "admin-rg"}'

        ensure_resource_group("admin-rg", "eastus", "sub-123")

        assert mock_execute.call_count == 1
        only_call = str(mock_execute.call_args)
        assert "show" in only_call
        assert "create" not in only_call

    @patch("azure_agentless_setup.state_storage.execute")
    def test_raises_on_create_failure(self, mock_execute):
        mock_execute.side_effect = ["", RuntimeError("creation failed")]

        with pytest.raises(StorageAccountError) as exc:
            ensure_resource_group("my-rg", "eastus", "sub-123")

        assert "Failed to create resource group" in exc.value.message


class TestFindAgentlessResourceGroups:
    @patch("azure_agentless_setup.state_storage.execute")
    def test_returns_tagged_rg_names(self, mock_execute):
        mock_execute.return_value = "rg-a\nrg-b\n"

        rgs = find_agentless_resource_groups("sub-123")

        assert rgs == ["rg-a", "rg-b"]
        call_str = str(mock_execute.call_args)
        assert "DatadogAgentlessScanner=true" in call_str

    @patch("azure_agentless_setup.state_storage.execute")
    def test_empty_output_returns_empty(self, mock_execute):
        mock_execute.return_value = ""
        assert find_agentless_resource_groups("sub-123") == []

    @patch("azure_agentless_setup.state_storage.execute")
    def test_failure_is_swallowed_to_empty(self, mock_execute):
        """Discovery is best-effort in this release: the metadata blob and
        SA-RG fallback in main.py still catch existing installs, so a
        transient az failure must not abort deploy."""
        mock_execute.side_effect = RuntimeError("auth")
        assert find_agentless_resource_groups("sub-123") == []


class TestEnsureStateStorage:
    INSTALL_ID = "abcdef012345"

    def _make_config(self, state_storage_account=None):
        config = MagicMock()
        config.scanner_subscription = "sub-scanner"
        config.locations = ["eastus"]
        config.resource_group = "my-rg"
        config.install_id = self.INSTALL_ID
        config.state_storage_account = state_storage_account
        return config

    def _make_reporter(self):
        reporter = MagicMock()
        return reporter

    @patch("azure_agentless_setup.state_storage.create_container")
    @patch("azure_agentless_setup.state_storage.container_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.grant_current_user_blob_data_contributor", return_value=False)
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.ensure_resource_group")
    def test_existing_account_reused(self, mock_rg, mock_sa_exists, mock_grant, mock_c_exists, mock_create_c):
        config = self._make_config()
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        assert result == get_storage_account_name(self.INSTALL_ID)
        mock_rg.assert_called_once()
        mock_create_c.assert_not_called()

    @patch("azure_agentless_setup.state_storage.create_container")
    @patch("azure_agentless_setup.state_storage.container_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.grant_current_user_blob_data_contributor", return_value=False)
    @patch("azure_agentless_setup.state_storage.create_storage_account")
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.ensure_resource_group")
    def test_creates_account_and_container(self, mock_rg, mock_sa_exists, mock_sa_create, mock_grant, mock_c_exists, mock_create_c):
        config = self._make_config()
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        mock_sa_create.assert_called_once()
        mock_create_c.assert_called_once()
        assert result == get_storage_account_name(self.INSTALL_ID)

    @patch("azure_agentless_setup.state_storage.wait_for_blob_access")
    @patch("azure_agentless_setup.state_storage.create_container")
    @patch("azure_agentless_setup.state_storage.container_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.grant_current_user_blob_data_contributor", return_value=True)
    @patch("azure_agentless_setup.state_storage.create_storage_account")
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=False)
    @patch("azure_agentless_setup.state_storage.ensure_resource_group")
    def test_waits_for_rbac_propagation_on_new_role(
        self, mock_rg, mock_sa_exists, mock_sa_create, mock_grant, mock_c_exists, mock_create_c, mock_wait,
    ):
        config = self._make_config()
        reporter = self._make_reporter()

        ensure_state_storage(config, reporter)

        mock_wait.assert_called_once()

    @patch("azure_agentless_setup.state_storage.container_exists", return_value=True)
    @patch("azure_agentless_setup.state_storage.grant_current_user_blob_data_contributor", return_value=False)
    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=True)
    def test_custom_account_used(self, mock_sa_exists, mock_grant, mock_c_exists):
        config = self._make_config(state_storage_account="mycustomacct")
        reporter = self._make_reporter()

        result = ensure_state_storage(config, reporter)

        assert result == "mycustomacct"
        mock_sa_exists.assert_called_once_with("mycustomacct", "my-rg", "sub-scanner")

    @patch("azure_agentless_setup.state_storage.storage_account_exists", return_value=False)
    def test_custom_account_not_found_raises(self, mock_sa_exists):
        config = self._make_config(state_storage_account="missing-acct")
        reporter = self._make_reporter()
        reporter.fatal.side_effect = StorageAccountError("not found")

        with pytest.raises(StorageAccountError):
            ensure_state_storage(config, reporter)

        reporter.fatal.assert_called_once()
