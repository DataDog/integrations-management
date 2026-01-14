# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, patch

from gcp_shared.gcloud import CommandResult, gcloud, try_gcloud


class TestCommandResult(unittest.TestCase):
    """Test CommandResult dataclass."""

    def test_success_true_when_returncode_zero(self):
        """Should return True when returncode is 0."""
        result = CommandResult(returncode=0, data={"test": "data"}, error="")
        self.assertTrue(result.success)

    def test_success_false_when_returncode_nonzero(self):
        """Should return False when returncode is non-zero."""
        result = CommandResult(returncode=1, data=None, error="error message")
        self.assertFalse(result.success)


class TestTryGcloud(unittest.TestCase):
    """Test the try_gcloud function."""

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_returns_success_result(self, mock_run):
        """Should return CommandResult with success=True on success."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = try_gcloud("projects list")

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"test": "data"})
        self.assertEqual(result.error, "")

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_returns_failure_result(self, mock_run):
        """Should return CommandResult with success=False on failure."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = "Error message"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = try_gcloud("invalid command")

        self.assertFalse(result.success)
        self.assertIsNone(result.data)
        self.assertEqual(result.error, "Error message")

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_with_keys(self, mock_run):
        """Should format command with keys."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = try_gcloud("projects list", "name", "projectId")

        mock_run.assert_called_once_with(
            'gcloud projects list --format="json(name,projectId)"',
            shell=True,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertTrue(result.success)


class TestGcloud(unittest.TestCase):
    """Test the gcloud function."""

    @patch("gcp_shared.gcloud.try_gcloud")
    def test_returns_data_on_success(self, mock_try_gcloud):
        """Should return data when command succeeds."""
        mock_try_gcloud.return_value = CommandResult(
            returncode=0, data={"test": "data"}, error=""
        )

        result = gcloud("projects list")

        self.assertEqual(result, {"test": "data"})

    @patch("gcp_shared.gcloud.try_gcloud")
    def test_raises_on_failure(self, mock_try_gcloud):
        """Should raise RuntimeError when command fails."""
        mock_try_gcloud.return_value = CommandResult(
            returncode=1, data=None, error="Error message"
        )

        with self.assertRaises(RuntimeError) as context:
            gcloud("invalid command")

        self.assertIn("could not execute gcloud command", str(context.exception))
        self.assertIn("Error message", str(context.exception))


if __name__ == "__main__":
    unittest.main()
