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


def _call(**overrides):
    """Invoke _resolve_destroy_resource_group with sensible defaults.

    Keeps the per-test body focused on the dimension under test. Every
    caller in the production code passes these arguments by keyword.
    """
    defaults = dict(
        metadata=None,
        metadata_status=MetadataReadStatus.MISSING,
        metadata_error_detail=None,
        env_rg=None,
        tagged_rgs=[],
        scanner_subscription="sub-scanner",
    )
    defaults.update(overrides)
    return _resolve_destroy_resource_group(**defaults)


class TestResolveDestroyResourceGroup:
    def test_metadata_wins(self):
        assert _call(
            metadata=_metadata("rg-from-metadata"),
            metadata_status=MetadataReadStatus.PRESENT,
        ) == "rg-from-metadata"

    def test_env_matching_metadata_passes(self):
        assert _call(
            metadata=_metadata("rg-from-metadata"),
            metadata_status=MetadataReadStatus.PRESENT,
            env_rg="rg-from-metadata",
        ) == "rg-from-metadata"

    def test_env_disagreeing_with_metadata_raises(self):
        with pytest.raises(ConfigurationError) as exc:
            _call(
                metadata=_metadata("rg-from-metadata"),
                metadata_status=MetadataReadStatus.PRESENT,
                env_rg="rg-from-env",
            )
        assert "rg-from-metadata" in exc.value.detail
        assert "rg-from-env" in exc.value.detail

    def test_legacy_metadata_without_rg_requires_env(self):
        with pytest.raises(SetupError) as exc:
            _call(
                metadata=_metadata(None),
                metadata_status=MetadataReadStatus.PRESENT,
            )
        assert "SCANNER_RESOURCE_GROUP" in exc.value.detail

    def test_legacy_metadata_with_env_uses_env(self):
        assert _call(
            metadata=_metadata(None),
            metadata_status=MetadataReadStatus.PRESENT,
            env_rg="rg-from-env",
        ) == "rg-from-env"

    def test_no_metadata_falls_back_to_env(self):
        assert _call(env_rg="rg-from-env") == "rg-from-env"

    def test_no_metadata_no_env_uses_default(self):
        assert _call() == DEFAULT_RESOURCE_GROUP

    def test_metadata_read_error_falls_back_to_env(self):
        """When the metadata blob cannot be read (auth/network), destroy must
        still pick an RG from the env var rather than aborting."""
        assert _call(
            metadata_status=MetadataReadStatus.ERROR,
            metadata_error_detail="throttled",
            env_rg="rg-from-env",
        ) == "rg-from-env"

    def test_metadata_read_error_falls_back_to_default(self):
        assert _call(
            metadata_status=MetadataReadStatus.ERROR,
            metadata_error_detail="auth failed",
        ) == DEFAULT_RESOURCE_GROUP


class TestResolveDestroyResourceGroupTagDiscovery:
    """Tag-based discovery is a secondary source of truth used when the
    metadata blob is missing or unreachable. It supplements but never
    overrides metadata when metadata is present and complete."""

    def test_single_tagged_adopted_when_metadata_missing(self):
        assert _call(tagged_rgs=["rg-tagged"]) == "rg-tagged"

    def test_tagged_overrides_default_when_env_unset(self):
        # Tagged RG must take precedence over DEFAULT_RESOURCE_GROUP; that's
        # the entire point of discovery (no env var needed on a fresh shell).
        assert _call(tagged_rgs=["rg-tagged"]) != DEFAULT_RESOURCE_GROUP

    def test_single_tagged_env_mismatch_raises(self):
        with pytest.raises(ConfigurationError) as exc:
            _call(tagged_rgs=["rg-tagged"], env_rg="rg-from-env")
        assert "rg-tagged" in exc.value.detail
        assert "rg-from-env" in exc.value.detail

    def test_multiple_tagged_without_env_raises(self):
        with pytest.raises(SetupError) as exc:
            _call(tagged_rgs=["rg-a", "rg-b"])
        assert "rg-a" in exc.value.detail and "rg-b" in exc.value.detail

    def test_multiple_tagged_with_matching_env_passes(self):
        assert _call(tagged_rgs=["rg-a", "rg-b"], env_rg="rg-a") == "rg-a"

    def test_multiple_tagged_with_unknown_env_raises(self):
        with pytest.raises(ConfigurationError) as exc:
            _call(tagged_rgs=["rg-a", "rg-b"], env_rg="rg-unknown")
        assert "rg-unknown" in exc.value.detail

    def test_metadata_present_overrides_tag_discovery(self):
        """Metadata stays authoritative even if tag discovery sees a
        different RG (e.g. tag drift / partial cleanup left a stray tag)."""
        assert _call(
            metadata=_metadata("rg-from-metadata"),
            metadata_status=MetadataReadStatus.PRESENT,
            tagged_rgs=["rg-stale-tag"],
        ) == "rg-from-metadata"
