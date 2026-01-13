# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch as mock_patch

from az_shared.errors import (
    AccessError,
    PolicyError,
    RateLimitExceededError,
    RefreshTokenError,
    ResourceNotFoundError,
    UserActionRequiredError,
)
from az_shared.execute_cmd import (
    AUTH_FAILED_ERROR,
    MAX_RETRIES,
    REFRESH_TOKEN_EXPIRED_ERROR,
    RESOURCE_NOT_FOUND_ERROR,
    execute,
)
from common.shell import Cmd

from shared.tests.test_data import EXAMPLE_POLICY_ERROR, EXAMPLE_POLICY_NAME


class CmdExecutionTestCase(TestCase):
    """Base class for command execution tests with common setup"""

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        self.sleep_mock = self.patch("az_shared.execute_cmd.sleep")
        self.az_version_mock = self.patch("az_shared.execute_cmd._get_az_version", return_value="az version")


class TestExecuteCmd(CmdExecutionTestCase):
    def test_execute_success(self):
        """Test successful command execution"""
        cmd = Cmd(["az", "functionapp", "create"]).param("--name", "test")
        mock_result = Mock()
        mock_result.stdout = "success output"
        mock_result.returncode = 0
        self.subprocess_mock.return_value = mock_result

        result = execute(cmd)

        self.assertEqual(result, "success output")
        self.subprocess_mock.assert_called_once()

    def test_execute_authorization_error(self):
        """Test execute handles authorization errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{AUTH_FAILED_ERROR}: Access denied"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(AccessError) as e:
            execute(cmd)
            self.assertIsInstance(e, UserActionRequiredError)

    def test_execute_refresh_token_error(self):
        """Test execute handles refresh token errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{REFRESH_TOKEN_EXPIRED_ERROR}: Token expired"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RefreshTokenError) as e:
            execute(cmd)
            self.assertIsInstance(e, UserActionRequiredError)

    def test_execute_resource_not_found_error(self):
        """Test execute handles resource not found errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{RESOURCE_NOT_FOUND_ERROR}: The resource was not found"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(ResourceNotFoundError):
            execute(cmd)

    def test_execute_rate_limit_error_with_retry(self):
        """Test execute retries on rate limit errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        # First call fails with rate limit, second succeeds
        error = CalledProcessError(1, "az")
        error.stderr = "TooManyRequests: Rate limit exceeded"

        mock_result_success = Mock()
        mock_result_success.stdout = "success after retry"
        mock_result_success.returncode = 0

        self.subprocess_mock.side_effect = [error, mock_result_success]

        result = execute(cmd)

        self.assertEqual(result, "success after retry")
        self.assertEqual(self.subprocess_mock.call_count, 2)
        self.sleep_mock.assert_called_once()

    def test_execute_rate_limit_max_retries(self):
        """Test execute raises exception after max retries"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = "TooManyRequests: Rate limit exceeded"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RateLimitExceededError):
            execute(cmd)

        # Should retry MAX_RETRIES times
        self.assertEqual(self.subprocess_mock.call_count, MAX_RETRIES)

    def test_execute_resource_collection_throttling(self):
        """Test execute handles resource collection throttling"""
        cmd = Cmd(["az", "functionapp", "create"])

        # First call fails with throttling, second succeeds
        error = CalledProcessError(1, "az")
        error.stderr = "ResourceCollectionRequestsThrottled: Too many requests"

        mock_result_success = Mock()
        mock_result_success.stdout = "success after throttling"
        mock_result_success.returncode = 0

        self.subprocess_mock.side_effect = [error, mock_result_success]

        result = execute(cmd)

        self.assertEqual(result, "success after throttling")
        self.assertEqual(self.subprocess_mock.call_count, 2)
        self.sleep_mock.assert_called_once()

    def test_execute_policy_error(self):
        """Test execute handles policy errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        # Mock CalledProcessError
        error = CalledProcessError(1, "az")
        error.stderr = f"""Warning: something unrelated
ERROR: (RequestDisallowedByPolicy) {EXAMPLE_POLICY_ERROR}"""
        self.subprocess_mock.side_effect = error

        with self.assertRaises(PolicyError) as ctx:
            execute(cmd)
        self.assertEqual(
            ctx.exception.user_action_message,
            f"Unable to create Datadog integration due to your policy {EXAMPLE_POLICY_NAME}. In order to install the Datadog integration you will have to modify this policy or select scopes where it does not apply.\n\nError Details:\n{EXAMPLE_POLICY_ERROR}",
        )

    def test_execute_subprocess_exception(self):
        """Test execute handles subprocess exceptions"""
        cmd = Cmd(["az", "functionapp", "create"])

        # Mock CalledProcessError
        error = CalledProcessError(1, "az")
        error.stderr = "Some generic error"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RuntimeError):
            execute(cmd)
