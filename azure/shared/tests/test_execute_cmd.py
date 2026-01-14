# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from subprocess import CalledProcessError, TimeoutExpired
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch as mock_patch

from az_shared.errors import (
    AccessError,
    DisabledSubscriptionError,
    InteractiveAuthenticationRequiredError,
    PolicyError,
    RateLimitExceededError,
    RefreshTokenError,
    ResourceNotFoundError,
    UserActionRequiredError,
)
from az_shared.execute_cmd import (
    AUTH_FAILED_ERROR,
    AZ_VERS_TIMEOUT,
    MAX_RETRIES,
    PERMISSION_REQUIRED_ERROR,
    REFRESH_TOKEN_EXPIRED_ERROR,
    RESOURCE_NOT_FOUND_ERROR,
    _get_az_version,
    _update_error_and_raise,
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
        self.az_version_mock = self.patch("az_shared.execute_cmd._get_az_version", return_value="az_version")

    def assert_has_az_version(self, exc: BaseException) -> None:
        expected = "\naz version:\naz_version"
        self.assertTrue(any(isinstance(arg, str) and expected in arg for arg in exc.args))


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
        self.assert_has_az_version(e.exception)

    def test_execute_refresh_token_error(self):
        """Test execute handles refresh token errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{REFRESH_TOKEN_EXPIRED_ERROR}: Token expired"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RefreshTokenError) as e:
            execute(cmd)
            self.assertIsInstance(e, UserActionRequiredError)
        self.assert_has_az_version(e.exception)

    def test_execute_resource_not_found_error(self):
        """Test execute handles resource not found errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{RESOURCE_NOT_FOUND_ERROR}: The resource was not found"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(ResourceNotFoundError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)

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

        with self.assertRaises(RateLimitExceededError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)

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
        self.assert_has_az_version(ctx.exception)

    def test_execute_subprocess_exception(self):
        """Test execute handles subprocess exceptions"""
        cmd = Cmd(["az", "functionapp", "create"])

        # Mock CalledProcessError
        error = CalledProcessError(1, "az")
        error.stderr = "Some generic error"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RuntimeError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)

    def test_execute_permission_required_error(self):
        """Test execute handles permission required errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = f"{PERMISSION_REQUIRED_ERROR}: additional permission is needed"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(AccessError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)

    def test_execute_interactive_authentication_required(self):
        """Test execute handles interactive authentication required errors"""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = (
            "Run the command below to authenticate interactively:\n"
            "az login --scope foo\n"
            "az account set --subscription bar\n"
        )
        self.subprocess_mock.side_effect = error

        with self.assertRaises(InteractiveAuthenticationRequiredError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)

    def test_execute_disabled_subscription_error(self):
        """Test execute handles disabled subscription errors."""
        cmd = Cmd(["az", "functionapp", "create"])

        error = CalledProcessError(1, "az")
        error.stderr = "DisabledSubscription: subscription is disabled"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(DisabledSubscriptionError) as e:
            execute(cmd)
        self.assert_has_az_version(e.exception)


class TestGetAzVersion(TestCase):
    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_get_az_version_success(self):
        """Test az version returns raw JSON on success."""
        subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        result = Mock()
        result.returncode = 0
        result.stdout = '{"azure-cli": "2.0.0"}\n'
        result.stderr = ""
        subprocess_mock.return_value = result
        self.assertEqual(_get_az_version(), '{"azure-cli": "2.0.0"}')
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_version_non_zero(self):
        """Test az version returns a failure message on non-zero exit."""
        subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        subprocess_mock.side_effect = CalledProcessError(
            returncode=1,
            cmd=["az", "version", "--output", "json"],
            stderr="error",
        )
        self.assertEqual(
            _get_az_version(),
            "Could not retrieve 'az version': exit 1 stderr: error",
        )
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_version_file_not_found(self):
        """Test az version returns a message when az is missing."""
        subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        subprocess_mock.side_effect = FileNotFoundError()
        self.assertEqual(_get_az_version(), "Could not retrieve 'az version': 'az' executable not found")
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_version_timeout(self):
        """Test az version returns a message on timeout."""
        subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        subprocess_mock.side_effect = TimeoutExpired(cmd="az version", timeout=AZ_VERS_TIMEOUT)
        self.assertEqual(_get_az_version(), "Could not retrieve 'az version': timeout after 5s")
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )

    def test_get_az_version_exception(self):
        """Test az version returns a message on unexpected exceptions."""
        subprocess_mock = self.patch("az_shared.execute_cmd.subprocess.run")
        subprocess_mock.side_effect = ValueError("bad")
        self.assertEqual(_get_az_version(), "Could not retrieve 'az version': bad")
        subprocess_mock.assert_called_once_with(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZ_VERS_TIMEOUT,
        )


class TestUpdateErrorAndRaise(TestCase):
    def test_update_error_and_raise_updates_message(self):
        """Test az version is appended to the primary error message."""
        with self.assertRaises(RuntimeError) as ctx:
            _update_error_and_raise(RuntimeError, az_version="az version", exc_args=["base error"])
        self.assertEqual(ctx.exception.args[0], "base error\naz version:\naz version")

    def test_update_error_and_raise_appends_message(self):
        """Test az version message is appended when exc_args is None without raising IndexError."""
        with self.assertRaises(RuntimeError) as ctx:
            _update_error_and_raise(RuntimeError, az_version="az version")
        self.assertEqual(ctx.exception.args[0], "\naz version:\naz version")

    def test_update_error_and_raise_with_cause(self):
        """Test original exception is chained as the cause."""
        cause = ValueError("root")
        with self.assertRaises(RuntimeError) as ctx:
            _update_error_and_raise(RuntimeError, az_version="az version", exc_args=["base error"], e=cause)
        self.assertIs(ctx.exception.__cause__, cause)

    def test_update_error_and_raise_user_action_message_unchanged(self):
        """Test user_action_message does not include az version."""
        with self.assertRaises(AccessError) as ctx:
            _update_error_and_raise(AccessError, az_version="az version", exc_args=["base error"])
        self.assertNotIn("az version", ctx.exception.user_action_message)
        self.assertEqual(ctx.exception.args[0], "base error\naz version:\naz version")

    def test_update_error_and_raise_interactive_auth_msg_idx(self):
        """Test az version is appended to the message when msg_idx=1."""
        commands = ["command1", "command2"]
        with self.assertRaises(InteractiveAuthenticationRequiredError) as ctx:
            _update_error_and_raise(
                InteractiveAuthenticationRequiredError,
                az_version="az version",
                exc_args=[commands, "Interactive authentication required"],
                msg_idx=1,
            )
        self.assertEqual(
            ctx.exception.args[1],
            "Interactive authentication required\naz version:\naz version",
        )
