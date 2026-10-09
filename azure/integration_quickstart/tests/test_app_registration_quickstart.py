# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import shlex
from datetime import datetime
from unittest.mock import MagicMock, patch

from az_shared.errors import MissingExternalIdError
from azure_integration_quickstart.app_registration_quickstart import (
    APP_REGISTRATION_UNSTORED_FIELDS,
    FEDERATED_AUTH_SUBJECT_PREFIX,
    AppRegistration,
    create_app_registration_with_permissions,
    main,
    submit_integration_config,
)

from integration_quickstart.tests.dd_test_case import DDTestCase
from integration_quickstart.tests.test_data import SUBSCRIPTION_SELECTION_RESPONSE

_APP_REG = AppRegistration(
    tenant_id="tenant-1",
    client_id="client-1",
    client_secret="secret-1",
    display_name="datadog-azure-integration-test",
)
_SCOPE = MagicMock(scope="/subscriptions/sub-1")
_DISPLAY_NAME = "datadog-azure-integration-test"


class TestCreateAppRegistrationWithPermissions(DDTestCase):
    def setUp(self):
        self.run_cmd = self.patch(
            "azure_integration_quickstart.app_registration_quickstart.run_app_reg_create_cmd",
            return_value={"appId": "app-1", "tenant": "tenant-1", "password": "pw"},
        )
        self.execute = self.patch("azure_integration_quickstart.app_registration_quickstart.execute")

    def test_secretless_auth_missing_external_id_raises(self):
        with self.assertRaises(MissingExternalIdError):
            create_app_registration_with_permissions(
                [_SCOPE], _DISPLAY_NAME, use_secretless_auth=True, external_id=None
            )

    def test_secretless_auth_empty_external_id_raises(self):
        with self.assertRaises(MissingExternalIdError):
            create_app_registration_with_permissions(
                [_SCOPE], _DISPLAY_NAME, use_secretless_auth=True, external_id=""
            )

    def test_secretless_auth_embeds_external_id_in_subject(self):
        create_app_registration_with_permissions(
            [_SCOPE], _DISPLAY_NAME, use_secretless_auth=True, external_id="ext-abc"
        )

        cmd_args = " ".join(self.execute.call_args[0][0])
        self.assertIn(f"{FEDERATED_AUTH_SUBJECT_PREFIX}ext-abc", cmd_args)

    def test_non_secretless_auth_does_not_call_federated_credential(self):
        self.patch(
            "azure_integration_quickstart.app_registration_quickstart.execute_json",
            return_value={"appId": "app-1", "tenant": "tenant-1", "password": "pw"},
        )
        create_app_registration_with_permissions(
            [_SCOPE], _DISPLAY_NAME, use_secretless_auth=False, external_id=None
        )
        self.execute.assert_not_called()

    @patch.dict("os.environ", {"WORKFLOW_ID": "workflow-1"})
    def test_workflow_issuer_used_in_federated_credential(self):
        for name in (
            "validate_environment_variables",
            "StatusReporter",
            "setup_cancellation_handlers",
            "login",
            "can_current_user_create_applications",
            "report_available_scopes",
            "submit_integration_config",
        ):
            self.patch(f"azure_integration_quickstart.app_registration_quickstart.{name}")
        self.patch(
            "azure_integration_quickstart.app_registration_quickstart.report_existing_log_forwarders",
            return_value=None,
        )
        dd_request = self.patch("azure_integration_quickstart.user_selections.dd_request")
        for issuer_config, expected_issuer in (
            (
                {"issuer_url": "https://jjmc4r9f5i.execute-api.us-east-1.amazonaws.com/pine"},
                "https://jjmc4r9f5i.execute-api.us-east-1.amazonaws.com/pine",
            ),
            ({"issuer_url": "https://oidc.datadoghq.com"}, "https://oidc.datadoghq.com"),
            ({}, "https://oidc.datadoghq.com"),
            ({"issuer_url": None}, "https://oidc.datadoghq.com"),
            ({"issuer_url": ""}, "https://oidc.datadoghq.com"),
        ):
            with self.subTest(issuer_config=issuer_config):
                response = json.loads(SUBSCRIPTION_SELECTION_RESPONSE)
                selections = response["data"]["attributes"]["metadata"]["selections"]
                selections["config_options"] = json.dumps(
                    {
                        "secretless_auth_enabled": True,
                        "external_id": "ext-abc",
                        **issuer_config,
                    }
                )
                dd_request.return_value = (json.dumps(response), 200)

                main()

                cmd_args = shlex.split(" ".join(self.execute.call_args[0][0]))
                credential = json.loads(cmd_args[cmd_args.index("--parameters") + 1])
                self.assertEqual(credential["issuer"], expected_issuer)
                self.assertEqual(credential["subject"], f"{FEDERATED_AUTH_SUBJECT_PREFIX}ext-abc")

    def test_selected_display_name_is_used_for_azure_and_returned(self):
        app_registration = create_app_registration_with_permissions(
            [_SCOPE], _DISPLAY_NAME, use_secretless_auth=True, external_id="ext-abc"
        )

        self.assertEqual(app_registration.display_name, _DISPLAY_NAME)
        self.assertIn(f"--name {_DISPLAY_NAME}", " ".join(self.run_cmd.call_args[0][0]))


    def test_absent_display_name_uses_original_timestamped_default(self):
        self.patch(
            "azure_integration_quickstart.app_registration_quickstart.execute_json",
            side_effect=RuntimeError("Requested secret TTL unavailable"),
        )
        mock_datetime = self.patch("azure_integration_quickstart.app_registration_quickstart.datetime")
        mock_datetime.now.return_value = datetime(2026, 9, 30, 12, 34, 56)
        expected_name = "datadog-azure-integration-2026-09-30-12-34-56"

        for display_name in (None, "", "   "):
            with self.subTest(display_name=display_name):
                app_registration = create_app_registration_with_permissions(
                    [_SCOPE], display_name, use_secretless_auth=False, external_id=None
                )

                self.assertEqual(app_registration.display_name, expected_name)
                self.assertIn(f"--name {expected_name}", " ".join(self.run_cmd.call_args[0][0]))


class TestSubmitIntegrationConfig(DDTestCase):
    def setUp(self):
        self.dd_request = self.patch("azure_integration_quickstart.app_registration_quickstart.dd_request")

    def test_credential_fields_stripped_from_payload(self):
        config = {
            "tenant_name": "tenant-1",
            "external_id": "ext-abc",
            "issuer_url": "https://oidc.datadoghq.com",
            "host_filters": "env:prod",
        }
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
