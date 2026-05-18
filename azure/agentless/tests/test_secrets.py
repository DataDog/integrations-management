# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.errors import KeyVaultError
from azure_agentless_setup.secrets import (
    create_key_vault,
    ensure_api_key_secret,
    get_key_vault_name,
    purge_key_vault,
)


class TestGetKeyVaultName:
    def test_respects_azure_constraints(self):
        # Azure Key Vault names: 3-24 chars, alphanumeric + hyphens,
        # must start with a letter, globally unique. install_id is a
        # 12-char lowercase hex; prefixed with "datadog-" we land at
        # 20 chars and stay within constraints.
        name = get_key_vault_name("0123456789ab")
        assert name == "datadog-0123456789ab"
        assert 3 <= len(name) <= 24
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

        # Recovery must target the scanner subscription so it runs against
        # the right tenant even when the user's az default subscription
        # differs from SCANNER_SUBSCRIPTION.
        mock_recover.assert_called_once_with("datadog-vault", "sub")

    @patch("azure_agentless_setup.secrets.execute")
    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault", return_value=None)
    def test_translates_vault_already_exists_to_actionable_error(
        self, mock_get_deleted, mock_execute
    ):
        """When list-deleted cannot see the soft-deleted vault (typically a
        missing ``deletedVaults/read`` permission) but Azure rejects the
        create with ``VaultAlreadyExists``, the user must get the recover /
        purge commands rather than the raw az stderr."""
        mock_execute.side_effect = Exception(
            "ERROR: (VaultAlreadyExists) The vault name 'datadog-vault' "
            "is already in use."
        )

        with pytest.raises(KeyVaultError) as exc:
            create_key_vault(
                vault_name="datadog-vault",
                resource_group="rg",
                location="eastus",
                subscription="sub-scanner",
            )

        assert "already in use" in exc.value.message
        assert "az keyvault recover" in exc.value.detail
        assert "az keyvault purge" in exc.value.detail
        assert "--subscription sub-scanner" in exc.value.detail


class TestPurgeKeyVault:
    """``purge_key_vault`` chains the soft-delete and the purge so the
    vault name is freed for immediate reuse. Both steps must target
    the scanner subscription (the user's az default may differ), and
    the purge step must carry the vault's original location because
    ``az keyvault purge`` is location-scoped."""

    @patch("azure_agentless_setup.secrets.execute")
    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault")
    def test_soft_deletes_then_purges_with_explicit_location_and_subscription(
        self, mock_get_deleted, mock_execute
    ):
        mock_get_deleted.return_value = {
            "name": "datadog-vault",
            "properties": {"location": "westeurope"},
        }

        assert purge_key_vault("datadog-vault", "sub-scanner") is True

        delete_cmd = str(mock_execute.call_args_list[0].args[0])
        assert " keyvault delete " in delete_cmd
        assert "--name datadog-vault" in delete_cmd
        assert "--subscription sub-scanner" in delete_cmd
        # ``--no-wait`` would let the purge step race the soft-delete
        # and fail with "vault not soft-deleted"; pin its absence.
        assert "--no-wait" not in delete_cmd

        purge_cmd = str(mock_execute.call_args_list[1].args[0])
        assert " keyvault purge " in purge_cmd
        assert "--name datadog-vault" in purge_cmd
        assert "--location westeurope" in purge_cmd
        assert "--subscription sub-scanner" in purge_cmd

    @patch("azure_agentless_setup.secrets.execute", side_effect=Exception("control-plane denied"))
    def test_returns_false_when_soft_delete_fails(self, mock_execute):
        # Caller in destroy.py degrades to a single-line warning
        # rather than crashing the wizard's final cleanup step.
        assert purge_key_vault("datadog-vault", "sub-scanner") is False
