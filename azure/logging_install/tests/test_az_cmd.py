# stdlib
import subprocess
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock

# project
import az_cmd
from errors import (
    AccessError,
    RateLimitExceededError,
    RefreshTokenError,
    ResourceNotFoundError,
)

# Test data
TEST_SUBSCRIPTION_ID = "test-sub-id"
TEST_SERVICE = "functionapp"
TEST_ACTION = "create"
TEST_RESOURCE_GROUP = "test-rg"
TEST_LOCATION = "eastus"


class TestAzCmd(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.subprocess_mock = self.patch("az_cmd.subprocess.run")
        self.sleep_mock = self.patch("az_cmd.sleep")

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_az_cmd_initialization(self):
        """Test AzCmd builder initialization"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        self.assertEqual(cmd.cmd, [TEST_SERVICE, "create"])

    def test_az_cmd_initialization_with_multi_word_action(self):
        """Test AzCmd builder with multi-word action"""
        cmd = az_cmd.AzCmd("storage", "account create")

        self.assertEqual(cmd.cmd, ["storage", "account", "create"])

    def test_az_cmd_param(self):
        """Test adding key-value parameters"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)
        result = cmd.param("--resource-group", TEST_RESOURCE_GROUP)

        self.assertIs(result, cmd)
        self.assertEqual(
            cmd.cmd,
            [TEST_SERVICE, "create", "--resource-group", TEST_RESOURCE_GROUP],
        )

    def test_az_cmd_param_list(self):
        """Test adding list parameters"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)
        values = ["value1", "value2", "value3"]
        result = cmd.param_list("--tags", values)

        self.assertIs(result, cmd)
        expected = [
            TEST_SERVICE,
            "create",
            "--tags",
            "value1",
            "value2",
            "value3",
        ]
        self.assertEqual(cmd.cmd, expected)

    def test_az_cmd_flag(self):
        """Test adding flags"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)
        result = cmd.flag("--yes")

        self.assertIs(result, cmd)
        self.assertEqual(cmd.cmd, [TEST_SERVICE, "create", "--yes"])

    def test_az_cmd_chaining(self):
        """Test method chaining"""
        cmd = (
            az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)
            .param("--resource-group", TEST_RESOURCE_GROUP)
            .param("--location", TEST_LOCATION)
            .flag("--yes")
        )

        expected = [
            TEST_SERVICE,
            "create",
            "--resource-group",
            TEST_RESOURCE_GROUP,
            "--location",
            TEST_LOCATION,
            "--yes",
        ]
        self.assertEqual(cmd.cmd, expected)

    def test_az_cmd_str(self):
        """Test string representation of command"""
        cmd = (
            az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)
            .param("--resource-group", TEST_RESOURCE_GROUP)
            .flag("--yes")
        )

        expected = (
            f"az {TEST_SERVICE} create --resource-group {TEST_RESOURCE_GROUP} --yes"
        )
        self.assertEqual(cmd.str(), expected)

    # ===== Execute Function Tests ===== #

    def test_execute_success(self):
        """Test successful command execution"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION).param("--name", "test")
        mock_result = MagicMock()
        mock_result.stdout = "success output"
        mock_result.returncode = 0
        self.subprocess_mock.return_value = mock_result

        result = az_cmd.execute(cmd)

        self.assertEqual(result, "success output")
        self.subprocess_mock.assert_called_once()

    def test_execute_authorization_error(self):
        """Test execute handles authorization errors"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        error = subprocess.CalledProcessError(1, "az")
        error.stderr = f"{az_cmd.AUTH_FAILED_ERROR}: Access denied"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(AccessError):
            az_cmd.execute(cmd)

    def test_execute_refresh_token_error(self):
        """Test execute handles refresh token errors"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        error = subprocess.CalledProcessError(1, "az")
        error.stderr = f"{az_cmd.REFRESH_TOKEN_EXPIRED_ERROR}: Token expired"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RefreshTokenError):
            az_cmd.execute(cmd)

    def test_execute_resource_not_found_error(self):
        """Test execute handles resource not found errors"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        error = subprocess.CalledProcessError(1, "az")
        error.stderr = f"{az_cmd.RESOURCE_NOT_FOUND_ERROR}: The resource was not found"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(ResourceNotFoundError):
            az_cmd.execute(cmd)

    def test_execute_rate_limit_error_with_retry(self):
        """Test execute retries on rate limit errors"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        # First call fails with rate limit, second succeeds
        error = subprocess.CalledProcessError(1, "az")
        error.stderr = f"{az_cmd.AZURE_THROTTLING_ERROR}: Rate limit exceeded"

        mock_result_success = MagicMock()
        mock_result_success.stdout = "success after retry"
        mock_result_success.returncode = 0

        self.subprocess_mock.side_effect = [error, mock_result_success]

        result = az_cmd.execute(cmd)

        self.assertEqual(result, "success after retry")
        self.assertEqual(self.subprocess_mock.call_count, 2)
        self.sleep_mock.assert_called_once()

    def test_execute_rate_limit_max_retries(self):
        """Test execute raises exception after max retries"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        error = subprocess.CalledProcessError(1, "az")
        error.stderr = f"{az_cmd.AZURE_THROTTLING_ERROR}: Rate limit exceeded"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RateLimitExceededError):
            az_cmd.execute(cmd)

        # Should retry MAX_RETRIES times
        self.assertEqual(self.subprocess_mock.call_count, az_cmd.MAX_RETRIES)

    def test_execute_resource_collection_throttling(self):
        """Test execute handles resource collection throttling"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        # First call fails with throttling, second succeeds
        error = subprocess.CalledProcessError(1, "az")
        error.stderr = (
            f"{az_cmd.RESOURCE_COLLECTION_THROTTLING_ERROR}: Too many requests"
        )

        mock_result_success = MagicMock()
        mock_result_success.stdout = "success after throttling"
        mock_result_success.returncode = 0

        self.subprocess_mock.side_effect = [error, mock_result_success]

        result = az_cmd.execute(cmd)

        self.assertEqual(result, "success after throttling")
        self.assertEqual(self.subprocess_mock.call_count, 2)
        self.sleep_mock.assert_called_once()

    def test_execute_subprocess_exception(self):
        """Test execute handles subprocess exceptions"""
        cmd = az_cmd.AzCmd(TEST_SERVICE, TEST_ACTION)

        # Mock CalledProcessError
        error = subprocess.CalledProcessError(1, "az")
        error.stderr = "Some generic error"
        self.subprocess_mock.side_effect = error

        with self.assertRaises(RuntimeError):
            az_cmd.execute(cmd)

    # ===== Set Subscription Function Tests ===== #

    def test_set_subscription_success(self):
        """Test successful subscription setting"""
        mock_result = MagicMock()
        mock_result.stdout = "Subscription set"
        mock_result.returncode = 0
        self.subprocess_mock.return_value = mock_result

        az_cmd.set_subscription(TEST_SUBSCRIPTION_ID)

        # Verify the correct command was called
        call_args = self.subprocess_mock.call_args
        cmd_list = call_args[0][0]
        self.assertIn("account", cmd_list)
        self.assertIn("set", cmd_list)
        self.assertIn("--subscription", cmd_list)
        self.assertIn(TEST_SUBSCRIPTION_ID, cmd_list)

    def test_set_subscription_with_error(self):
        """Test set_subscription handles errors"""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Subscription not found"
        mock_result.returncode = 1
        self.subprocess_mock.return_value = mock_result

        with self.assertRaises(Exception):
            az_cmd.set_subscription(TEST_SUBSCRIPTION_ID)

    # ===== Error Pattern Recognition Tests ===== #

    def test_error_pattern_constants(self):
        """Test error pattern constants are correctly defined"""
        self.assertEqual(az_cmd.AUTH_FAILED_ERROR, "AuthorizationFailed")
        self.assertEqual(az_cmd.AZURE_THROTTLING_ERROR, "TooManyRequests")
        self.assertEqual(az_cmd.REFRESH_TOKEN_EXPIRED_ERROR, "AADSTS700082")
        self.assertEqual(
            az_cmd.RESOURCE_COLLECTION_THROTTLING_ERROR,
            "ResourceCollectionRequestsThrottled",
        )
        self.assertEqual(az_cmd.RESOURCE_NOT_FOUND_ERROR, "ResourceNotFound")
        self.assertIsInstance(az_cmd.MAX_RETRIES, int)
        self.assertGreater(az_cmd.MAX_RETRIES, 0)
