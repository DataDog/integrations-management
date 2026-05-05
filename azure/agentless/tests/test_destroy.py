# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for destroy._resolve_destroy_resource_group, which decides
which resource group to tear down. Metadata must always win over the
SCANNER_RESOURCE_GROUP env var to avoid silently destroying the wrong
RG; the env var is now strictly a fallback for legacy installs."""

import pytest

from azure_agentless_setup.config import DEFAULT_RESOURCE_GROUP
from azure_agentless_setup.destroy import _resolve_destroy_resource_group
from azure_agentless_setup.errors import ConfigurationError, SetupError
from azure_agentless_setup.metadata import DeploymentMetadata, MetadataReadStatus


def _metadata(resource_group):
    return DeploymentMetadata(
        scanner_subscription="sub-scanner",
        resource_group=resource_group,
        locations=["eastus"],
        subscriptions_to_scan=["sub-scanner"],
        created_at="t0",
        modified_at="t0",
    )


class TestResolveDestroyResourceGroup:
    def test_metadata_wins(self):
        rg = _resolve_destroy_resource_group(
            metadata=_metadata("rg-from-metadata"),
            metadata_status=MetadataReadStatus.PRESENT,
            metadata_error_detail=None,
            env_rg=None,
            scanner_subscription="sub-scanner",
        )
        assert rg == "rg-from-metadata"

    def test_env_matching_metadata_passes(self):
        rg = _resolve_destroy_resource_group(
            metadata=_metadata("rg-from-metadata"),
            metadata_status=MetadataReadStatus.PRESENT,
            metadata_error_detail=None,
            env_rg="rg-from-metadata",
            scanner_subscription="sub-scanner",
        )
        assert rg == "rg-from-metadata"

    def test_env_disagreeing_with_metadata_raises(self):
        with pytest.raises(ConfigurationError) as exc:
            _resolve_destroy_resource_group(
                metadata=_metadata("rg-from-metadata"),
                metadata_status=MetadataReadStatus.PRESENT,
                metadata_error_detail=None,
                env_rg="rg-from-env",
                scanner_subscription="sub-scanner",
            )
        assert "rg-from-metadata" in exc.value.detail
        assert "rg-from-env" in exc.value.detail

    def test_legacy_metadata_without_rg_requires_env(self):
        with pytest.raises(SetupError) as exc:
            _resolve_destroy_resource_group(
                metadata=_metadata(None),
                metadata_status=MetadataReadStatus.PRESENT,
                metadata_error_detail=None,
                env_rg=None,
                scanner_subscription="sub-scanner",
            )
        assert "SCANNER_RESOURCE_GROUP" in exc.value.detail

    def test_legacy_metadata_with_env_uses_env(self):
        rg = _resolve_destroy_resource_group(
            metadata=_metadata(None),
            metadata_status=MetadataReadStatus.PRESENT,
            metadata_error_detail=None,
            env_rg="rg-from-env",
            scanner_subscription="sub-scanner",
        )
        assert rg == "rg-from-env"

    def test_no_metadata_falls_back_to_env(self):
        rg = _resolve_destroy_resource_group(
            metadata=None,
            metadata_status=MetadataReadStatus.MISSING,
            metadata_error_detail=None,
            env_rg="rg-from-env",
            scanner_subscription="sub-scanner",
        )
        assert rg == "rg-from-env"

    def test_no_metadata_no_env_uses_default(self):
        rg = _resolve_destroy_resource_group(
            metadata=None,
            metadata_status=MetadataReadStatus.MISSING,
            metadata_error_detail=None,
            env_rg=None,
            scanner_subscription="sub-scanner",
        )
        assert rg == DEFAULT_RESOURCE_GROUP

    def test_metadata_read_error_falls_back_to_env(self):
        """When the metadata blob cannot be read (auth/network), destroy must
        still pick an RG from the env var rather than aborting."""
        rg = _resolve_destroy_resource_group(
            metadata=None,
            metadata_status=MetadataReadStatus.ERROR,
            metadata_error_detail="throttled",
            env_rg="rg-from-env",
            scanner_subscription="sub-scanner",
        )
        assert rg == "rg-from-env"

    def test_metadata_read_error_falls_back_to_default(self):
        rg = _resolve_destroy_resource_group(
            metadata=None,
            metadata_status=MetadataReadStatus.ERROR,
            metadata_error_detail="auth failed",
            env_rg=None,
            scanner_subscription="sub-scanner",
        )
        assert rg == DEFAULT_RESOURCE_GROUP
