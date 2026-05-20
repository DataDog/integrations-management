# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for ``destroy._resolve_destroy_resource_group``.

With install-id-scoped resource naming, the storage account that holds
the metadata blob is itself addressable only after the resource group is
known. The resolver therefore consumes only tag-based discovery results
and the ``SCANNER_RESOURCE_GROUP`` env var; metadata-based reconciliation
moved upstream into deploy and is no longer involved here.
"""

from unittest.mock import patch

import pytest

from azure_agentless_setup.config import DEFAULT_RESOURCE_GROUP
from azure_agentless_setup.destroy import (
    _resolve_destroy_resource_group,
    cleanup_key_vault,
)
from azure_agentless_setup.errors import ConfigurationError, SetupError


def _call(**overrides):
    """Invoke _resolve_destroy_resource_group with sensible defaults."""
    defaults = dict(
        env_rg=None,
        tagged_rgs=[],
        scanner_subscription="sub-scanner",
    )
    defaults.update(overrides)
    return _resolve_destroy_resource_group(**defaults)


class TestResolveDestroyResourceGroup:
    def test_no_tags_no_env_uses_default(self):
        assert _call() == DEFAULT_RESOURCE_GROUP

    def test_no_tags_with_env_uses_env(self):
        """Covers the admin-pre-created-untagged-RG case: the user has to
        remember the env var on a fresh shell."""
        assert _call(env_rg="rg-from-env") == "rg-from-env"

    def test_single_tagged_adopted(self):
        """Tag discovery must override DEFAULT_RESOURCE_GROUP when env is
        unset — that's the whole point of discovery on a fresh shell."""
        assert _call(tagged_rgs=["rg-tagged"]) == "rg-tagged"

    def test_single_tagged_env_matches_passes(self):
        assert _call(tagged_rgs=["rg-tagged"], env_rg="rg-tagged") == "rg-tagged"

    def test_single_tagged_env_mismatch_raises(self):
        with pytest.raises(ConfigurationError) as exc:
            _call(tagged_rgs=["rg-tagged"], env_rg="rg-other")
        assert "rg-tagged" in exc.value.detail
        assert "rg-other" in exc.value.detail

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


class TestCleanupKeyVault:
    """Destroy always purges the vault: terraform destroy has already
    confirmed the user's intent, so the recurring ``VaultAlreadyExists``
    on re-deploy must not be re-introduced by stopping at soft-delete."""

    @patch("azure_agentless_setup.destroy.purge_key_vault", return_value=True)
    @patch("azure_agentless_setup.destroy.key_vault_exists", return_value=True)
    def test_purges_with_scanner_subscription(self, mock_exists, mock_purge):
        cleanup_key_vault(
            install_id="0123456789ab",
            resource_group="rg",
            subscription="sub-scanner",
        )

        # ``key_vault_exists`` must carry the scanner subscription too:
        # without it, Cloud Shell's default sub is used and the
        # existence check silently returns False, causing the purge
        # to be skipped (the regression we are guarding against).
        mock_exists.assert_called_once_with(
            "datadog-0123456789ab", "rg", "sub-scanner"
        )
        mock_purge.assert_called_once_with("datadog-0123456789ab", "sub-scanner")

    @patch("azure_agentless_setup.destroy.purge_key_vault")
    @patch("azure_agentless_setup.destroy.key_vault_exists", return_value=False)
    def test_skips_entirely_when_vault_already_gone(
        self, mock_exists, mock_purge
    ):
        # Idempotency: a destroy that already ran (or had the parent
        # RG nuked out-of-band) must not flood the user with az-cli
        # "vault not found" noise.
        cleanup_key_vault(
            install_id="0123456789ab",
            resource_group="rg",
            subscription="sub-scanner",
        )

        mock_purge.assert_not_called()
