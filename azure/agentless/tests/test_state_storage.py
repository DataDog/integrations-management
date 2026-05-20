# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from az_shared.errors import AccessError, ResourceNotFoundError

from azure_agentless_setup.errors import StorageAccountError
from azure_agentless_setup.state_storage import (
    RBAC_PROPAGATION_RETRIES,
    ensure_resource_group,
    find_agentless_resource_groups,
    get_storage_account_name,
    grant_current_user_blob_data_contributor,
    storage_account_exists,
    wait_for_blob_access,
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


class TestStorageAccountExistsErrorClassification:
    """``storage_account_exists`` used to swallow every exception as
    "doesn't exist", which let auth / network failures masquerade as
    "first deploy" - meaning the wizard would try to create a colliding
    SA, or destroy would skip the metadata read entirely. Only the two
    ``*NotFound`` errors should map to False; anything else must
    propagate so the caller surfaces the real problem."""

    @patch("azure_agentless_setup.state_storage.execute")
    def test_resource_not_found_maps_to_false(self, mock_execute):
        mock_execute.side_effect = ResourceNotFoundError("not found")
        assert storage_account_exists("sa", "rg", "sub") is False

    @patch("azure_agentless_setup.state_storage.execute")
    def test_access_error_propagates(self, mock_execute):
        # The whole point of B2: an AccessError must NOT degrade to
        # "no SA found"; the caller has to see the real RBAC issue.
        mock_execute.side_effect = AccessError("no permission")
        with pytest.raises(AccessError):
            storage_account_exists("sa", "rg", "sub")


class TestGrantCurrentUserBlobDataContributor:
    """The grant must target the scanner subscription on every az call,
    not the Cloud Shell user's default sub. Cloud Shell picks a default
    subscription at startup which is frequently different from the
    scanner sub; without ``--subscription``, ``az storage account show``
    hits the wrong sub and 404s with ``ResourceGroupNotFound``, which the
    wizard mis-translates as a data-plane RBAC failure.

    Since the grant flow was extracted into :func:`rbac.grant_role_to_current_user`,
    the resource lookup runs in ``state_storage`` while signed-in-user
    lookup, role list, and role create run in ``rbac``. Both modules'
    ``execute`` are mocked here so the threading is asserted across the
    whole flow.
    """

    @patch("azure_agentless_setup.rbac.execute")
    @patch("azure_agentless_setup.state_storage.execute")
    def test_threads_subscription_through_all_az_calls(
        self, mock_state_execute, mock_rbac_execute
    ):
        mock_state_execute.return_value = (
            '{"id": "/subscriptions/sub-scanner/resourceGroups/rg/'
            'providers/Microsoft.Storage/storageAccounts/sa"}'
        )
        mock_rbac_execute.side_effect = ["user-object-id", "0", ""]

        grant_current_user_blob_data_contributor(
            account_name="sa",
            resource_group="rg",
            subscription="sub-scanner",
        )

        show_cmd = str(mock_state_execute.call_args.args[0])
        assert "storage account show" in show_cmd
        assert "--subscription sub-scanner" in show_cmd

        # Role list / create must also carry the scanner subscription,
        # otherwise the role would be queried/created in the wrong sub
        # and the wait_for_blob_access probe would never see it.
        list_cmd = str(mock_rbac_execute.call_args_list[1].args[0])
        assert "role assignment list" in list_cmd
        assert "--subscription sub-scanner" in list_cmd

        create_cmd = str(mock_rbac_execute.call_args_list[2].args[0])
        assert "role assignment create" in create_cmd
        assert "--subscription sub-scanner" in create_cmd


class TestWaitForBlobAccess:
    """Probe behaviour for RBAC-propagation detection.

    The fix for the second-user-joining flow depends on the probe
    mirroring the exact ``az storage blob show`` call ``read_metadata``
    will run: only the BlobNotFound / ContainerNotFound family of
    errors counts as "data plane reachable, blob just doesn't exist
    yet"; anything else (typically AuthorizationPermissionMismatch)
    has to be retried. Without this, an over-permissive probe would
    let the wait return immediately and the subsequent metadata read
    fail with the opaque Azure "permissions" error.

    Probe semantics live in :func:`metadata.probe_blob`; these tests
    mock that function so the wait-loop logic is exercised in isolation
    from the subprocess-and-classifier internals.
    """

    @patch("azure_agentless_setup.metadata.probe_blob")
    def test_returns_immediately_on_probe_success(self, mock_probe):
        from azure_agentless_setup.metadata import BlobProbeResult, MetadataReadStatus

        mock_probe.return_value = BlobProbeResult(MetadataReadStatus.PRESENT, stdout='"etag"')
        reporter = MagicMock()

        wait_for_blob_access("acct", reporter)

        mock_probe.assert_called_once()
        reporter.info.assert_not_called()

    @patch("azure_agentless_setup.metadata.probe_blob")
    def test_returns_on_blob_not_found(self, mock_probe):
        """First-deploy paths: SA was just created, config.json doesn't
        exist yet. A clean 404 still proves data-plane reachability,
        so the wait must not loop."""
        from azure_agentless_setup.metadata import BlobProbeResult, MetadataReadStatus

        mock_probe.return_value = BlobProbeResult(MetadataReadStatus.MISSING)
        reporter = MagicMock()

        wait_for_blob_access("acct", reporter)

        mock_probe.assert_called_once()
        reporter.info.assert_not_called()

    @patch("azure_agentless_setup.state_storage.time.sleep")
    @patch("azure_agentless_setup.metadata.probe_blob")
    def test_raises_on_persistent_authorization_permission_mismatch(
        self, mock_probe, _mock_sleep
    ):
        """The bug we're fixing: this stderr used to come back from
        ``az storage blob show`` after the wizard fell through a
        permissive ``container list`` probe. The probe must keep
        retrying instead of declaring success.

        Previously the wait silently returned after the retry window,
        leaving the downstream ``read_metadata`` call to surface a
        confusing ``AuthorizationPermissionMismatch``. Now we raise
        a focused ``StorageAccountError`` carrying the last probe
        stderr so the user has a single actionable failure point.
        """
        from azure_agentless_setup.metadata import BlobProbeResult, MetadataReadStatus

        permission_error_detail = (
            "ERROR: You do not have the required permissions needed to "
            "perform this operation."
        )
        mock_probe.return_value = BlobProbeResult(
            MetadataReadStatus.ERROR, error_detail=permission_error_detail
        )
        reporter = MagicMock()

        with pytest.raises(StorageAccountError) as exc:
            wait_for_blob_access("acct", reporter)

        assert mock_probe.call_count == RBAC_PROPAGATION_RETRIES
        # The raised error must carry both the offending account and
        # the last probe error detail so the user has actionable context.
        assert "acct" in exc.value.detail
        assert "required permissions" in exc.value.detail
