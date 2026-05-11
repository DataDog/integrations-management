# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for main.cmd_deploy helpers, focused on tag-based RG discovery
and the existing-deployment validation that run before any infrastructure
mutation."""

from unittest.mock import patch

import pytest

from azure_agentless_setup.config import Config
from azure_agentless_setup.errors import ConfigurationError, SetupError
from azure_agentless_setup.main import (
    _check_existing_deployment,
    _resolve_resource_group_via_tags,
)
from azure_agentless_setup.metadata import (
    DeploymentMetadata,
    MetadataReadResult,
    MetadataReadStatus,
)


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


class TestCheckExistingDeployment:
    """Metadata-blob + legacy SA-RG fallback. Tag discovery is exercised
    separately above; here we hold it fixed at 'no tagged RGs' so the
    surface under test is just the metadata branch."""

    @patch("azure_agentless_setup.main.find_storage_account_rg", return_value=None)
    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_matching_rg_returns_result(self, mock_read, mock_find):
        mock_read.return_value = _present("rg-current")

        check = _check_existing_deployment(_make_config())

        assert check.metadata_result.status == MetadataReadStatus.PRESENT
        mock_find.assert_not_called()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_present_mismatched_rg_raises(self, mock_read, mock_find):
        mock_read.return_value = _present("rg-original")

        with pytest.raises(ConfigurationError) as exc:
            _check_existing_deployment(_make_config(resource_group="rg-other"))

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail
        mock_find.assert_not_called()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_error_status_raises(self, mock_read, mock_find):
        mock_read.return_value = MetadataReadResult(
            MetadataReadStatus.ERROR, error_detail="auth boom"
        )

        with pytest.raises(SetupError) as exc:
            _check_existing_deployment(_make_config())

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
            _check_existing_deployment(_make_config(resource_group="rg-other"))

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail

    @patch("azure_agentless_setup.main.find_storage_account_rg", return_value=None)
    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_first_deploy_returns_missing(self, mock_read, mock_find):
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)

        check = _check_existing_deployment(_make_config())

        assert check.metadata_result.status == MetadataReadStatus.MISSING
        mock_find.assert_called_once()

    @patch("azure_agentless_setup.main.find_storage_account_rg")
    @patch("azure_agentless_setup.main.read_metadata")
    def test_missing_with_custom_sa_skips_find(self, mock_read, mock_find):
        # Custom SA: ensure_state_storage already validates the SA's RG, so
        # the MISSING branch must NOT call find_storage_account_rg.
        mock_read.return_value = MetadataReadResult(MetadataReadStatus.MISSING)
        config = _make_config(state_storage_account="myacct")

        check = _check_existing_deployment(config)

        assert check.metadata_result.status == MetadataReadStatus.MISSING
        assert check.storage_account_name == "myacct"
        mock_find.assert_not_called()
