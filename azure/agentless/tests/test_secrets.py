# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.errors import KeyVaultError
from azure_agentless_setup.secrets import (
    create_key_vault,
    ensure_api_key_secret,
    get_key_vault_name,
)


class TestGetKeyVaultName:
    def test_deterministic(self):
        name1 = get_key_vault_name("sub-123")
        name2 = get_key_vault_name("sub-123")
        assert name1 == name2

    def test_different_subs_produce_different_names(self):
        name1 = get_key_vault_name("sub-aaa")
        name2 = get_key_vault_name("sub-bbb")
        assert name1 != name2

    def test_within_azure_length_limit(self):
        name = get_key_vault_name("a-very-long-subscription-id-that-is-a-uuid")
        assert len(name) <= 24

    def test_starts_with_letter(self):
        name = get_key_vault_name("sub-123")
        assert name[0].isalpha()


class TestEnsureApiKeySecret:
    def _make_reporter(self):
        return MagicMock()

    @patch("azure_agentless_setup.secrets.get_secret_resource_id", return_value="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/vault/secrets/datadog-api-key")
    @patch("azure_agentless_setup.secrets.set_secret", return_value="https://vault.vault.azure.net/secrets/key/v1")
    @patch("azure_agentless_setup.secrets.get_secret_value", return_value=None)
    @patch("azure_agentless_setup.secrets.wait_for_secret_access")
    @patch("azure_agentless_setup.secrets.grant_current_user_secrets_officer", return_value=True)
    @patch("azure_agentless_setup.secrets.create_key_vault")
    @patch("azure_agentless_setup.secrets.key_vault_exists", return_value=False)
    def test_creates_vault_and_secret_when_new(
        self, mock_kv_exists, mock_create_kv, mock_grant, mock_wait, mock_get_val, mock_set, mock_resource_id
    ):
        reporter = self._make_reporter()

        result = ensure_api_key_secret(
            config_api_key="my-api-key",
            vault_name="dd-al-kv-test",
            resource_group="my-rg",
            location="eastus",
            subscription="sub-123",
            reporter=reporter,
        )

        mock_create_kv.assert_called_once_with("dd-al-kv-test", "my-rg", "eastus", "sub-123")
        mock_grant.assert_called_once()
        mock_wait.assert_called_once_with("dd-al-kv-test", reporter)
        mock_set.assert_called_once_with("dd-al-kv-test", "my-api-key")
        assert "secrets/datadog-api-key" in result

    @patch("azure_agentless_setup.secrets.get_secret_resource_id", return_value="/sub/rg/vault/secrets/datadog-api-key")
    @patch("azure_agentless_setup.secrets.get_secret_value", return_value="my-api-key")
    @patch("azure_agentless_setup.secrets.wait_for_secret_access")
    @patch("azure_agentless_setup.secrets.grant_current_user_secrets_officer", return_value=False)
    @patch("azure_agentless_setup.secrets.key_vault_exists", return_value=True)
    def test_skips_update_when_unchanged(self, mock_kv_exists, mock_grant, mock_wait, mock_get_val, mock_resource_id):
        reporter = self._make_reporter()

        ensure_api_key_secret(
            config_api_key="my-api-key",
            vault_name="dd-al-kv-test",
            resource_group="my-rg",
            location="eastus",
            subscription="sub-123",
            reporter=reporter,
        )

        # Pre-existing role assignment: the orchestrator must NOT block on
        # RBAC propagation, since the user's role has been live for the
        # full propagation window already.
        mock_wait.assert_not_called()
        reporter.success.assert_called()
        assert "unchanged" in reporter.success.call_args[0][0]

    @patch("azure_agentless_setup.secrets.get_secret_resource_id", return_value="/sub/rg/vault/secrets/datadog-api-key")
    @patch("azure_agentless_setup.secrets.set_secret", return_value="https://vault/secrets/key/v2")
    @patch("azure_agentless_setup.secrets.get_secret_value", return_value="old-key")
    @patch("azure_agentless_setup.secrets.wait_for_secret_access")
    @patch("azure_agentless_setup.secrets.grant_current_user_secrets_officer", return_value=False)
    @patch("azure_agentless_setup.secrets.key_vault_exists", return_value=True)
    def test_updates_secret_when_changed(
        self, mock_kv_exists, mock_grant, mock_wait, mock_get_val, mock_set, mock_resource_id
    ):
        reporter = self._make_reporter()

        ensure_api_key_secret(
            config_api_key="new-api-key",
            vault_name="dd-al-kv-test",
            resource_group="my-rg",
            location="eastus",
            subscription="sub-123",
            reporter=reporter,
        )

        mock_set.assert_called_once_with("dd-al-kv-test", "new-api-key")
        mock_wait.assert_not_called()

    @patch("azure_agentless_setup.secrets.create_key_vault", side_effect=KeyVaultError("creation failed"))
    @patch("azure_agentless_setup.secrets.key_vault_exists", return_value=False)
    def test_raises_on_vault_creation_failure(self, mock_kv_exists, mock_create):
        reporter = self._make_reporter()

        with pytest.raises(KeyVaultError) as exc:
            ensure_api_key_secret(
                config_api_key="key",
                vault_name="vault",
                resource_group="rg",
                location="eastus",
                subscription="sub",
                reporter=reporter,
            )

        assert "creation failed" in str(exc.value)


class TestCreateKeyVaultSoftDeleteMismatch:
    """A soft-deleted Key Vault can only be recovered into its original
    resource group. We must refuse to recover into a different RG instead
    of letting az emit an opaque error."""

    @staticmethod
    def _deleted(original_rg: str) -> dict:
        return {
            "name": "datadog-vault",
            "properties": {
                "vaultId": (
                    f"/subscriptions/sub/resourceGroups/{original_rg}/"
                    "providers/Microsoft.KeyVault/vaults/datadog-vault"
                ),
            },
        }

    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault")
    def test_raises_on_rg_mismatch_with_purge_hint(self, mock_get_deleted):
        mock_get_deleted.return_value = self._deleted(original_rg="rg-original")

        with pytest.raises(KeyVaultError) as exc:
            create_key_vault(
                vault_name="datadog-vault",
                resource_group="rg-other",
                location="eastus",
                subscription="sub",
            )

        assert "rg-original" in exc.value.detail
        assert "rg-other" in exc.value.detail
        assert "az keyvault purge" in exc.value.detail

    @patch("azure_agentless_setup.secrets._recover_soft_deleted")
    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault")
    def test_recovers_when_rg_matches(self, mock_get_deleted, mock_recover):
        mock_get_deleted.return_value = self._deleted(original_rg="rg-original")

        create_key_vault(
            vault_name="datadog-vault",
            resource_group="rg-original",
            location="eastus",
            subscription="sub",
        )

        mock_recover.assert_called_once_with("datadog-vault")
