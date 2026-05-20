# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock, patch

import pytest

from az_shared.errors import ResourceNotFoundError

from azure_agentless_setup.errors import KeyVaultError
from azure_agentless_setup.secrets import (
    create_key_vault,
    get_key_vault_name,
    grant_current_user_secrets_officer,
    key_vault_exists,
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


class TestCreateKeyVaultPostCreatePropagation:
    """``az keyvault create`` issues a PUT then a GET to return the new
    resource. ARM frequently 404s the GET right after a purge of the
    same vault name even though the PUT succeeded - the resource is
    created, it just is not visible yet. ``create_key_vault`` must
    swallow that 404 and confirm via :func:`key_vault_exists` rather
    than surfacing a misleading "Failed to create" error to the user."""

    @patch("azure_agentless_setup.secrets.sleep")
    @patch("azure_agentless_setup.secrets.key_vault_exists")
    @patch("azure_agentless_setup.secrets.execute")
    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault", return_value=None)
    def test_treats_post_create_404_as_success_when_vault_eventually_visible(
        self, mock_get_deleted, mock_execute, mock_exists, mock_sleep
    ):
        mock_execute.side_effect = ResourceNotFoundError(
            "Resource not found when executing 'az keyvault create ...'"
        )
        # Three GETs miss before ARM catches up, then the vault appears.
        # Pins that the helper polls (does not give up on the first miss).
        mock_exists.side_effect = [False, False, False, True]

        create_key_vault(
            vault_name="datadog-vault",
            resource_group="rg",
            location="westus2",
            subscription="sub-scanner",
        )

        assert mock_exists.call_count == 4

    @patch("azure_agentless_setup.secrets.sleep")
    @patch("azure_agentless_setup.secrets.key_vault_exists", return_value=False)
    @patch("azure_agentless_setup.secrets.execute")
    @patch("azure_agentless_setup.secrets._get_soft_deleted_vault", return_value=None)
    def test_raises_with_diagnostic_when_vault_never_appears(
        self, mock_get_deleted, mock_execute, mock_exists, mock_sleep
    ):
        mock_execute.side_effect = ResourceNotFoundError(
            "Resource not found when executing 'az keyvault create ...'"
        )

        with pytest.raises(KeyVaultError) as exc:
            create_key_vault(
                vault_name="datadog-vault",
                resource_group="rg",
                location="westus2",
                subscription="sub-scanner",
            )

        # The user must get the manual recovery hint - without it the
        # raw "Resource not found" is easily misread as a permissions
        # problem.
        assert "az keyvault show" in exc.value.detail
        assert "datadog-vault" in exc.value.detail


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


class TestKeyVaultExistsSubscriptionThreading:
    """``key_vault_exists`` is the only thing standing between destroy
    and a misleading "VaultAlreadyExists" / "ResourceNotFound" loop:
    when the Cloud Shell user's default subscription differs from the
    scanner sub (the wizard never calls ``set_subscription`` on the
    destroy path), the lookup must explicitly target the scanner sub
    or it will silently report the vault as missing and try to recreate."""

    @patch("azure_agentless_setup.secrets.execute")
    def test_passes_subscription_to_az_when_provided(self, mock_execute):
        mock_execute.return_value = '{"name": "datadog-vault"}'

        key_vault_exists("datadog-vault", "rg", "sub-scanner")

        cmd_str = str(mock_execute.call_args.args[0])
        assert "keyvault show" in cmd_str
        assert "--subscription sub-scanner" in cmd_str


class TestGrantCurrentUserSecretsOfficerSubscriptionThreading:
    """Mirror the Storage Blob Data Contributor fix: every inner az
    call must carry ``--subscription``. The Cloud Shell user's default
    is unreliable, and the destroy path doesn't call ``set_subscription``,
    so without the threading these calls would hit the wrong sub and
    surface as opaque ResourceNotFound / AuthorizationFailed errors.

    Since the grant flow was extracted into :func:`rbac.grant_role_to_current_user`,
    the vault lookup runs in ``secrets`` (via ``execute_json``) while
    signed-in-user, role list, and role create run in ``rbac`` (via
    ``execute``). Both modules' commands are asserted here.
    """

    @patch("azure_agentless_setup.secrets.execute_json")
    @patch("azure_agentless_setup.rbac.execute")
    def test_threads_subscription_through_all_az_calls(
        self, mock_rbac_execute, mock_execute_json
    ):
        # signed-in-user → role list (0 = need create) → role create
        mock_rbac_execute.side_effect = [
            "user-object-id",
            "0",
            "",
        ]
        mock_execute_json.return_value = {
            "id": "/subscriptions/sub-scanner/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/v"
        }

        grant_current_user_secrets_officer("v", "sub-scanner")

        show_cmd = str(mock_execute_json.call_args.args[0])
        assert "keyvault show" in show_cmd
        assert "--subscription sub-scanner" in show_cmd

        list_cmd = str(mock_rbac_execute.call_args_list[1].args[0])
        assert "role assignment list" in list_cmd
        assert "--subscription sub-scanner" in list_cmd

        create_cmd = str(mock_rbac_execute.call_args_list[2].args[0])
        assert "role assignment create" in create_cmd
        assert "--subscription sub-scanner" in create_cmd
