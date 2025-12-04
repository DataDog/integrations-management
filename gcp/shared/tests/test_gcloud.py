# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import subprocess
import unittest
from unittest.mock import Mock, patch

from gcp_shared.gcloud import gcloud, is_logged_in


class TestGCloudFunction(unittest.TestCase):
    """Test the gcloud function."""

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_gcloud_success(self, mock_run):
        """Test successful gcloud command execution."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = gcloud("projects list")

        mock_run.assert_called_once_with(
            "gcloud projects list --format=json",
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result, {"test": "data"})

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_gcloud_with_keys(self, mock_run):
        """Test gcloud command with specific keys."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = gcloud("projects list", "name", "projectId")

        mock_run.assert_called_once_with(
            'gcloud projects list --format="json(name,projectId)"',
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result, {"test": "data"})

    @patch("gcp_shared.gcloud.subprocess.run")
    def test_gcloud_failure(self, mock_run):
        """Test gcloud command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", stderr="Error message"
        )

        with self.assertRaises(RuntimeError) as context:
            gcloud("invalid command")

        self.assertIn("could not execute gcloud command", str(context.exception))


class TestIsLoggedIn(unittest.TestCase):
    """Test the is_logged_in function."""

    @patch("gcp_shared.gcloud.gcloud")
    def test_is_logged_in_success(self, mock_gcloud):
        """Test is_logged_in when user is logged in."""
        mock_gcloud.return_value = "ya29.a0AfH6SMBx..."

        result = is_logged_in()

        self.assertTrue(result)
        mock_gcloud.assert_called_once_with("auth print-access-token")

    @patch("gcp_shared.gcloud.gcloud")
    def test_is_logged_in_not_logged_in(self, mock_gcloud):
        """Test is_logged_in when user is not logged in."""
        mock_gcloud.side_effect = Exception(
            "You do not currently have an active account selected."
        )

        with self.assertRaises(SystemExit) as context:
            is_logged_in()

        self.assertEqual(context.exception.code, 1)

    @patch("gcp_shared.gcloud.gcloud")
    @patch("builtins.print")
    def test_is_logged_in_gcloud_not_found(
        self, mock_print, mock_gcloud
    ):
        """Test is_logged_in when gcloud command is not found."""
        mock_gcloud.side_effect = Exception("gcloud: command not found")

        with self.assertRaises(SystemExit) as context:
            is_logged_in()

        self.assertEqual(context.exception.code, 1)
        mock_print.assert_called_once()
        self.assertIn(
            "You must install the GCloud CLI",
            mock_print.call_args[0][0]
        )

    @patch("gcp_shared.gcloud.gcloud")
    @patch("builtins.print")
    def test_is_logged_in_other_exception(
        self, mock_print, mock_gcloud
    ):
        """Test is_logged_in with other exceptions."""
        mock_gcloud.side_effect = Exception("Some other error")

        with self.assertRaises(SystemExit) as context:
            is_logged_in()

        self.assertEqual(context.exception.code, 1)
        mock_print.assert_called_once()
        self.assertIn(
            "You must be logged in to GCloud CLI",
            mock_print.call_args[0][0]
        )

    @patch("gcp_shared.gcloud.gcloud")
    def test_is_logged_in_returns_none(self, mock_gcloud):
        """Test is_logged_in when gcloud returns None."""
        mock_gcloud.return_value = None

        result = is_logged_in()

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
