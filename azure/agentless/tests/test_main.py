# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for main.cmd_deploy helpers, focused on tag-based RG discovery
and the existing-deployment validation that run before any infrastructure
mutation."""

from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.config import Config
from azure_agentless_setup.errors import ConfigurationError, SetupError, StorageAccountError
from azure_agentless_setup.main import (
    _check_existing_deployment,
    _resolve_resource_group_via_tags,
)
from azure_agentless_setup.metadata import (
    DeploymentMetadata,
    MetadataReadResult,
    MetadataReadStatus,
)


def _reporter():
    return MagicMock()


def _make_config(
    resource_group: str = "rg-current",
    state_storage_account=None,
    resource_group_explicit: bool = False,
) -> Config:
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
        resource_group_explicit=resource_group_explicit,
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


class TestResolveResourceGroupViaTags:
    """Decision matrix for tag-based RG discovery (zero / one / multi)."""

    @patch("azure_agentless_setup.main.find_agentless_resource_groups", return_value=[])
    def test_zero_tagged_keeps_config(self, _mock_find):
        resolved = _resolve_resource_group_via_tags(_make_config(resource_group="rg-x"))
        assert resolved.resource_group == "rg-x"

    @patch(
        "azure_agentless_setup.main.find_agentless_resource_groups",
        return_value=["rg-tagged"],
    )
    def test_one_tagged_env_unset_adopts(self, _mock_find):
        config = _make_config(resource_group="datadog-agentless-scanner")  # default, env unset
        resolved = _resolve_resource_group_via_tags(config)

        assert resolved.resource_group == "rg-tagged"
        # install_id must follow the resolved RG so downstream resource
        # naming and local paths stay consistent.
        assert resolved.install_id != config.install_id

    @patch(
        "azure_agentless_setup.main.find_agentless_resource_groups",
        return_value=["rg-tagged"],
    )
    def test_one_tagged_env_matches_passes(self, _mock_find):
        config = _make_config(resource_group="rg-tagged", resource_group_explicit=True)
        resolved = _resolve_resource_group_via_tags(config)
        assert resolved.resource_group == "rg-tagged"

    @patch(
        "azure_agentless_setup.main.find_agentless_resource_groups",
        return_value=["rg-tagged"],
    )
    def test_one_tagged_env_mismatches_raises(self, _mock_find):
        with pytest.raises(ConfigurationError) as exc:
            _resolve_resource_group_via_tags(
                _make_config(resource_group="rg-other", resource_group_explicit=True)
            )
        assert "rg-tagged" in exc.value.detail
        assert "rg-other" in exc.value.detail

    @patch(
        "azure_agentless_setup.main.find_agentless_resource_groups",
        return_value=["rg-a", "rg-b"],
    )
    def test_multiple_tagged_blocks(self, _mock_find):
        with pytest.raises(SetupError) as exc:
            _resolve_resource_group_via_tags(_make_config())
        assert "rg-a" in exc.value.detail and "rg-b" in exc.value.detail


@patch("azure_agentless_setup.main.ensure_current_user_blob_data_access")
@patch("azure_agentless_setup.main.storage_account_exists", return_value=True)
class TestCheckExistingDeployment:
    """Metadata-blob inspection when the Storage Account exists.

    Tag-based RG discovery is exercised separately by
    :class:`TestResolveResourceGroupViaTags`; the SA-missing short-circuit
    is exercised by :class:`TestCheckExistingDeploymentStorageAccountMissing`.
    """

    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_matching_rg_returns_result(
        self, mock_read, _sa_exists, mock_ensure_access
    ):
        mock_read.return_value = _present("rg-current")

        check = _check_existing_deployment(_make_config(), _reporter())

        assert check.metadata_result.status == MetadataReadStatus.PRESENT
        # Blob data plane must be granted *before* the metadata read, so
        # a second user joining an existing deployment doesn't trip over
        # an opaque "permissions" error from az storage blob show.
        mock_ensure_access.assert_called_once()
        # Storage account name is positional arg 0.
        assert mock_ensure_access.call_args.args[0].startswith("datadog")

    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_mismatched_rg_raises(
        self, mock_read, _sa_exists, _ensure_access
    ):
        """With install-id-scoped SA names, finding a metadata blob at all
        means we addressed the right install, so a recorded RG that
        disagrees with the config can only be blob corruption. We still
        fail loud rather than silently merge."""
        mock_read.return_value = _present("rg-original")

        with pytest.raises(ConfigurationError) as exc:
            _check_existing_deployment(
                _make_config(resource_group="rg-other"), _reporter()
            )

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail

    @patch("azure_agentless_setup.main.read_metadata")
    def test_error_status_raises(self, mock_read, _sa_exists, _ensure_access):
        mock_read.return_value = MetadataReadResult(
            MetadataReadStatus.ERROR, error_detail="auth boom"
        )

        with pytest.raises(SetupError) as exc:
            _check_existing_deployment(_make_config(), _reporter())

        assert "auth boom" in exc.value.detail

    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_first_deploy_returns_missing(
        self, mock_read, _sa_exists, _ensure_access
    ):
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)

        check = _check_existing_deployment(_make_config(), _reporter())

        assert check.metadata_result.status == MetadataReadStatus.MISSING

    @patch("azure_agentless_setup.main.read_metadata")
    def test_custom_sa_used_as_storage_account_name(
        self, mock_read, _sa_exists, _ensure_access
    ):
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)
        config = _make_config(state_storage_account="myacct")

        check = _check_existing_deployment(config, _reporter())

        assert check.storage_account_name == "myacct"

    @patch("azure_agentless_setup.main.read_metadata")
    def test_blob_access_failure_short_circuits_before_read(
        self, mock_read, _sa_exists, mock_ensure_access
    ):
        """When the current user lacks privileges to self-grant the
        data-plane role, the read should not be attempted at all so the
        caller sees the focused permission error rather than the opaque
        ``az storage blob show`` stderr."""
        mock_ensure_access.side_effect = StorageAccountError(
            "Cannot access existing deployment's Terraform state",
            "data-plane vs control-plane explanation",
        )

        with pytest.raises(StorageAccountError):
            _check_existing_deployment(_make_config(), _reporter())

        mock_read.assert_not_called()


class TestCheckExistingDeploymentStorageAccountMissing:
    """First-deploy short-circuit: no Storage Account → MISSING, no blob read.

    Regression guard for the case where the SA does not exist yet:
    ``read_metadata`` would otherwise surface an account-not-found / DNS
    failure that ``_classify_blob_show_failure`` cannot reliably map to
    MISSING, aborting first deploys with a misleading
    "Could not read deployment metadata" error.
    """

    @patch("azure_agentless_setup.main.ensure_current_user_blob_data_access")
    @patch("azure_agentless_setup.main.read_metadata")
    @patch("azure_agentless_setup.main.storage_account_exists", return_value=False)
    def test_missing_sa_short_circuits_without_blob_read(
        self, _sa_exists, mock_read, mock_ensure_access
    ):
        check = _check_existing_deployment(_make_config(), _reporter())

        assert check.metadata_result.status == MetadataReadStatus.MISSING
        mock_read.assert_not_called()
        # Granting blob data access for a Storage Account that doesn't
        # exist yet would fail; the short-circuit must skip it too.
        mock_ensure_access.assert_not_called()
