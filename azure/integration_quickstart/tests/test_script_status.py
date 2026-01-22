# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import threading
from unittest.mock import ANY, MagicMock

from az_shared.errors import AccessError, AzCliNotInstalledError
from azure_integration_quickstart.script_status import Status, StatusReporter

from integration_quickstart.tests.dd_test_case import DDTestCase
from integration_quickstart.tests.test_data import EXAMPLE_STEP_ID, EXAMPLE_WORKFLOW_ID

CREATE_APP_REG_WORKFLOW_TYPE = "azure-app-registration-setup"


class TestStatusReporter(DDTestCase):
    def setUp(self) -> None:
        self.loading_spinner_mock: MagicMock = self.patch("azure_integration_quickstart.script_status.loading_spinner")

        self.status_reporter = StatusReporter(CREATE_APP_REG_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.report_mock = MagicMock()
        self.status_reporter.report = self.report_mock

    def test_step_pass_no_message(self):
        with self.status_reporter.report_step(EXAMPLE_STEP_ID):
            self.report_mock.assert_called_once_with(
                EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
            )
        self.report_mock.assert_called_with(
            EXAMPLE_STEP_ID, Status.FINISHED, f"{EXAMPLE_STEP_ID}: {Status.FINISHED}", None
        )
        self.assertEqual(self.report_mock.call_count, 2)
        self.loading_spinner_mock.assert_not_called()

    def test_loading_message(self):
        with self.status_reporter.report_step(EXAMPLE_STEP_ID, "loading"):
            self.report_mock.assert_called_once_with(
                EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
            )

            self.loading_spinner_mock.assert_called_with("loading", ANY)
            done_event: threading.Event = self.loading_spinner_mock.call_args[0][1]
            self.assertFalse(done_event.is_set())

        self.report_mock.assert_called_with(
            EXAMPLE_STEP_ID, Status.FINISHED, f"{EXAMPLE_STEP_ID}: {Status.FINISHED}", None
        )
        self.assertEqual(self.report_mock.call_count, 2)

        self.loading_spinner_mock.assert_called_with("loading", ANY)
        done_event: threading.Event = self.loading_spinner_mock.call_args[0][1]
        self.assertTrue(done_event.is_set())

    def test_metadata(self):
        with self.status_reporter.report_step(EXAMPLE_STEP_ID) as metadata:
            self.report_mock.assert_called_once_with(
                EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
            )

            self.assertDictEqual(metadata, {})
            metadata["key"] = "val"

        self.report_mock.assert_called_with(
            EXAMPLE_STEP_ID, Status.FINISHED, f"{EXAMPLE_STEP_ID}: {Status.FINISHED}", ANY
        )
        self.assertEqual(self.report_mock.call_count, 2)

        reported_metadata = self.report_mock.call_args[0][3]
        self.assertDictEqual(reported_metadata, {"key": "val"})

    def test_expired_token(self):
        error_message = f"something \n something {StatusReporter.EXPIRED_TOKEN_ERROR} something something"
        with self.assertRaises(Exception) as e:
            with self.status_reporter.report_step(EXAMPLE_STEP_ID):
                self.report_mock.assert_called_once_with(
                    EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
                )
                raise Exception(error_message)
        self.assertEqual(str(e.exception), error_message)
        self.report_mock.assert_called_with("connection", Status.CANCELLED, f"Azure CLI token expired: {error_message}")
        self.assertEqual(self.report_mock.call_count, 2)

    def test_user_actionable_error(self):
        error_message = "invalid user credentials"
        with self.assertRaises(AccessError) as e:
            with self.status_reporter.report_step(EXAMPLE_STEP_ID):
                self.report_mock.assert_called_once_with(
                    EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
                )
                raise AccessError(error_message)

        expected_user_action_message = (
            "You don't have the necessary Azure permissions to access, create, or perform an action on a required resource."
            + "\nPlease review the Datadog documentation at https://docs.datadoghq.com/getting_started/integrations/azure/ and contact your Azure administrator if necessary."
            + f"\n\nError Details:\n{error_message}"
        )

        self.assertEqual(e.exception.user_action_message, expected_user_action_message)
        self.report_mock.assert_called_with(EXAMPLE_STEP_ID, Status.USER_ACTIONABLE_ERROR, expected_user_action_message)
        self.assertEqual(self.report_mock.call_count, 2)

    def test_user_retriable_error(self):
        error_message = "something \n something az: command not found etc"
        with self.assertRaises(AzCliNotInstalledError) as e:
            with self.status_reporter.report_step(EXAMPLE_STEP_ID):
                self.report_mock.assert_called_once_with(
                    EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
                )
                raise AzCliNotInstalledError(error_message)

        expected_user_action_message = (
            f"You must install and log in to Azure CLI to run this script\n\nError Details:\n{error_message}"
        )

        self.assertEqual(e.exception.user_action_message, expected_user_action_message)
        self.report_mock.assert_called_with(EXAMPLE_STEP_ID, Status.WARN, ANY)
        self.assertEqual(self.report_mock.call_count, 2)

    def test_unexpected_error(self):
        error_message = "Azure has been deleted forever."
        with self.assertRaises(Exception) as e:
            with self.status_reporter.report_step(EXAMPLE_STEP_ID):
                self.report_mock.assert_called_once_with(
                    EXAMPLE_STEP_ID, Status.IN_PROGRESS, f"{EXAMPLE_STEP_ID}: {Status.IN_PROGRESS}"
                )
                raise Exception(error_message)

        self.assertEqual(str(e.exception), error_message)
        self.report_mock.assert_called_with(EXAMPLE_STEP_ID, Status.FAILED, ANY)
        self.assertEqual(self.report_mock.call_count, 2)
