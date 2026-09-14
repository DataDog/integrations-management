# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from az_shared.errors import MissingExternalIdError
from azure_integration_quickstart.app_registration_quickstart import (
    APP_REGISTRATION_UNSTORED_FIELDS,
    FEDERATED_AUTH_SUBJECT_PREFIX,
    AppRegistration,
    create_app_registration_with_permissions,
    submit_integration_config,
)

from integration_quickstart.tests.dd_test_case import DDTestCase

_APP_REG = AppRegistration(
    tenant_id="tenant-1",
    client_id="client-1",
    client_secret="secret-1",
    display_name="datadog-azure-integration-test",
)
_SCOPE = MagicMock(scope="/subscriptions/sub-1")


class TestCreateAppRegistrationWithPermissions(DDTestCase):
    def setUp(self):
        self.run_cmd = self.patch(
            "azure_integration_quickstart.app_registration_quickstart.run_app_reg_create_cmd",
            return_value={"appId": "app-1", "tenant": "tenant-1", "password": "pw"},
        )
        self.execute = self.patch("azure_integration_quickstart.app_registration_quickstart.execute")
        self.get_app_registration_name = self.patch(
            "azure_integration_quickstart.app_registration_quickstart.get_app_registration_name",
            return_value="datadog-azure-integration-test",
        )

    def test_secretless_auth_missing_external_id_raises(self):
        with self.assertRaises(MissingExternalIdError):
            create_app_registration_with_permissions([_SCOPE], use_secretless_auth=True, external_id=None)

    def test_secretless_auth_empty_external_id_raises(self):
        with self.assertRaises(MissingExternalIdError):
            create_app_registration_with_permissions([_SCOPE], use_secretless_auth=True, external_id="")

    def test_secretless_auth_embeds_external_id_in_subject(self):
        app_registration = create_app_registration_with_permissions(
            [_SCOPE], use_secretless_auth=True, external_id="ext-abc"
        )

        cmd_args = " ".join(self.execute.call_args[0][0])
        self.assertIn(f"{FEDERATED_AUTH_SUBJECT_PREFIX}ext-abc", cmd_args)
        self.assertEqual(app_registration.display_name, "datadog-azure-integration-test")
        self.assertIn("--name datadog-azure-integration-test", " ".join(self.run_cmd.call_args[0][0]))
        self.get_app_registration_name.assert_called_once_with()

    def test_non_secretless_auth_does_not_call_federated_credential(self):
        execute_json = self.patch(
            "azure_integration_quickstart.app_registration_quickstart.execute_json",
            return_value={"appId": "app-1", "tenant": "tenant-1", "password": "pw"},
        )
        app_registration = create_app_registration_with_permissions(
            [_SCOPE], use_secretless_auth=False, external_id=None
        )
        self.execute.assert_not_called()
        self.assertEqual(app_registration.display_name, "datadog-azure-integration-test")
        self.assertIn("--name datadog-azure-integration-test", " ".join(execute_json.call_args[0][0]))
        self.get_app_registration_name.assert_called_once_with()


class TestSubmitIntegrationConfig(DDTestCase):
    def setUp(self):
        self.dd_request = self.patch("azure_integration_quickstart.app_registration_quickstart.dd_request")

    def test_external_id_stripped_from_payload(self):
        config = {"tenant_name": "tenant-1", "external_id": "ext-abc", "host_filters": "env:prod"}
        submit_integration_config(_APP_REG, config)

        posted = self.dd_request.call_args[0][2]
        for field in APP_REGISTRATION_UNSTORED_FIELDS:
            self.assertNotIn(field, posted)

    def test_other_config_fields_included_in_payload(self):
        config = {"host_filters": "env:prod", "external_id": "ext-abc"}
        submit_integration_config(_APP_REG, config)

        posted = self.dd_request.call_args[0][2]
        self.assertEqual(posted["host_filters"], "env:prod")
        self.assertEqual(posted["client_id"], _APP_REG.client_id)
        self.assertEqual(posted["client_secret"], _APP_REG.client_secret)
        self.assertEqual(posted["tenant_name"], _APP_REG.tenant_id)
        self.assertEqual(posted["display_name"], _APP_REG.display_name)
