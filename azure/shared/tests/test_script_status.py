# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import threading
import unittest
from unittest.mock import ANY, MagicMock, patch

from az_shared.errors import AccessError, AzCliNotAuthenticatedError, AzCliNotInstalledError
from az_shared.script_status import Status, StatusReporter


WORKFLOW_TYPE = "example-workflow"
WORKFLOW_ID = "Example workflow"
STEP_ID = "example_workflow_step"
FINAL_STEP = "final_step"


class TestStatusReporter(unittest.TestCase):
    def setUp(self) -> None:
        loading_patcher = patch("az_shared.script_status.loading_spinner")
        self.loading_spinner_mock: MagicMock = loading_patcher.start()
        self.addCleanup(loading_patcher.stop)

        self.status_reporter = StatusReporter(WORKFLOW_TYPE, WORKFLOW_ID)
        self.report_mock = MagicMock()
        self.status_reporter.report = self.report_mock

    def test_step_pass_no_message(self):
        with self.status_reporter.report_step(STEP_ID):
            self.report_mock.assert_called_once_with(
                STEP_ID, Status.IN_PROGRESS, f"{STEP_ID}: {Status.IN_PROGRESS}"
            )
        self.report_mock.assert_called_with(
            STEP_ID, Status.FINISHED, f"{STEP_ID}: {Status.FINISHED}", None
        )
        self.assertEqual(self.report_mock.call_count, 2)
        self.loading_spinner_mock.assert_not_called()

    def test_loading_message(self):
        with self.status_reporter.report_step(STEP_ID, "loading"):
            self.report_mock.assert_called_once_with(
                STEP_ID, Status.IN_PROGRESS, f"{STEP_ID}: {Status.IN_PROGRESS}"
            )

            self.loading_spinner_mock.assert_called_with("loading", ANY)
            done_event: threading.Event = self.loading_spinner_mock.call_args[0][1]
            self.assertFalse(done_event.is_set())

        self.report_mock.assert_called_with(
            STEP_ID, Status.FINISHED, f"{STEP_ID}: {Status.FINISHED}", None
        )
        self.assertEqual(self.report_mock.call_count, 2)

        done_event = self.loading_spinner_mock.call_args[0][1]
        self.assertTrue(done_event.is_set())

    def test_metadata(self):
        with self.status_reporter.report_step(STEP_ID) as metadata:
            self.assertDictEqual(metadata, {})
            metadata["key"] = "val"

        self.report_mock.assert_called_with(
            STEP_ID, Status.FINISHED, f"{STEP_ID}: {Status.FINISHED}", ANY
        )
        self.assertEqual(self.report_mock.call_count, 2)

        reported_metadata = self.report_mock.call_args[0][3]
        self.assertDictEqual(reported_metadata, {"key": "val"})

    def test_expired_token(self):
        error_message = f"something \n something {StatusReporter.EXPIRED_TOKEN_ERROR} something something"
        with self.assertRaises(Exception) as e:
            with self.status_reporter.report_step(STEP_ID):
                raise Exception(error_message)
        self.assertEqual(str(e.exception), error_message)
        self.report_mock.assert_called_with(
            "connection", Status.CANCELLED, f"Azure CLI token expired: {error_message}"
        )
        self.assertEqual(self.report_mock.call_count, 2)

    def test_user_actionable_error(self):
        error_message = "invalid user credentials"
        with self.assertRaises(AccessError) as e:
            with self.status_reporter.report_step(STEP_ID):
                raise AccessError(error_message)

        self.report_mock.assert_called_with(
            STEP_ID, Status.USER_ACTIONABLE_ERROR, e.exception.user_action_message
        )
        self.assertEqual(self.report_mock.call_count, 2)

    def test_user_retriable_error(self):
        error_message = "something \n something az: command not found etc"
        with self.assertRaises(AzCliNotInstalledError):
            with self.status_reporter.report_step(STEP_ID):
                raise AzCliNotInstalledError(error_message)

        self.report_mock.assert_called_with(STEP_ID, Status.WARN, ANY)
        self.assertEqual(self.report_mock.call_count, 2)

    def test_unexpected_error(self):
        error_message = "Azure has been deleted forever."
        with self.assertRaises(Exception) as e:
            with self.status_reporter.report_step(STEP_ID):
                raise Exception(error_message)

        self.assertEqual(str(e.exception), error_message)
        self.report_mock.assert_called_with(STEP_ID, Status.FAILED, ANY)
        self.assertEqual(self.report_mock.call_count, 2)


def _workflow_response(statuses: list[dict]) -> str:
    return json.dumps({"data": {"attributes": {"statuses": statuses}}})


class TestIsValidWorkflowId(unittest.TestCase):
    def setUp(self) -> None:
        self.reporter = StatusReporter(WORKFLOW_TYPE, WORKFLOW_ID)

    @patch("az_shared.script_status.dd_request")
    def test_404_is_valid(self, dd_request_mock):
        dd_request_mock.return_value = ("", 404)
        self.assertTrue(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_transient_error_is_valid(self, dd_request_mock):
        dd_request_mock.side_effect = RuntimeError("boom")
        self.assertTrue(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_unexpected_status_is_invalid(self, dd_request_mock):
        dd_request_mock.return_value = ("", 500)
        self.assertFalse(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_failed_non_login_step_is_invalid(self, dd_request_mock):
        dd_request_mock.return_value = (
            _workflow_response([{"step": "preflight_checks", "status": Status.FAILED.value}]),
            200,
        )
        self.assertFalse(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_failed_login_step_is_valid(self, dd_request_mock):
        dd_request_mock.return_value = (
            _workflow_response([{"step": "login", "status": Status.FAILED.value}]),
            200,
        )
        self.assertTrue(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_finished_final_step_is_invalid(self, dd_request_mock):
        dd_request_mock.return_value = (
            _workflow_response([{"step": FINAL_STEP, "status": Status.FINISHED.value}]),
            200,
        )
        self.assertFalse(self.reporter.is_valid_workflow_id(FINAL_STEP))

    @patch("az_shared.script_status.dd_request")
    def test_in_progress_workflow_is_valid(self, dd_request_mock):
        dd_request_mock.return_value = (
            _workflow_response([
                {"step": "login", "status": Status.FINISHED.value},
                {"step": "preflight_checks", "status": Status.IN_PROGRESS.value},
            ]),
            200,
        )
        self.assertTrue(self.reporter.is_valid_workflow_id(FINAL_STEP))


class TestHandleLoginStep(unittest.TestCase):
    def setUp(self) -> None:
        self.reporter = StatusReporter(WORKFLOW_TYPE, WORKFLOW_ID)
        self.reporter.report = MagicMock()

    @patch("az_shared.script_status.check_login")
    def test_success_reports_finished(self, check_login_mock):
        self.reporter.handle_login_step()
        check_login_mock.assert_called_once()
        statuses = [call.args[1] for call in self.reporter.report.call_args_list]
        self.assertEqual(statuses, [Status.IN_PROGRESS, Status.FINISHED])

    @patch("az_shared.script_status.check_login")
    def test_cli_not_installed_exits_after_reporting(self, check_login_mock):
        check_login_mock.side_effect = AzCliNotInstalledError("not found")
        with self.assertRaises(SystemExit) as cm:
            self.reporter.handle_login_step()
        self.assertEqual(cm.exception.code, 1)
        # AzCliNotInstalledError is a UserRetriableError -> reported as WARN.
        final_call = self.reporter.report.call_args_list[-1]
        self.assertEqual(final_call.args[0], "login")
        self.assertEqual(final_call.args[1], Status.WARN)

    @patch("az_shared.script_status.check_login")
    def test_cli_not_authenticated_exits_after_reporting(self, check_login_mock):
        check_login_mock.side_effect = AzCliNotAuthenticatedError("not logged in")
        with self.assertRaises(SystemExit) as cm:
            self.reporter.handle_login_step()
        self.assertEqual(cm.exception.code, 1)
        final_call = self.reporter.report.call_args_list[-1]
        self.assertEqual(final_call.args[0], "login")
        self.assertEqual(final_call.args[1], Status.WARN)
