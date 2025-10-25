# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import subprocess
import unittest
from unittest.mock import Mock, patch

from shared.gcloud import gcloud


class TestGCloudFunction(unittest.TestCase):
    """Test the gcloud function."""

    @patch("shared.gcloud.subprocess.run")
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

    @patch("shared.gcloud.subprocess.run")
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

    @patch("shared.gcloud.subprocess.run")
    def test_gcloud_failure(self, mock_run):
        """Test gcloud command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", stderr="Error message"
        )

        with self.assertRaises(RuntimeError) as context:
            gcloud("invalid command")

        self.assertIn("could not execute gcloud command", str(context.exception))


if __name__ == "__main__":
    unittest.main()
