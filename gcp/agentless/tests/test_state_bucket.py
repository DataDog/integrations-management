# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, patch

from gcp_agentless_setup.errors import BucketCreationError
from gcp_agentless_setup.state_bucket import (
    bucket_exists,
    create_bucket,
)


class TestBucketExists(unittest.TestCase):
    """Test bucket existence check."""

    @patch("gcp_agentless_setup.state_bucket.run_command")
    def test_returns_true_when_bucket_exists(self, mock_run):
        """Should return True when gcloud describe succeeds."""
        mock_run.return_value = Mock(success=True)

        result = bucket_exists("my-bucket")

        self.assertTrue(result)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("gs://my-bucket", call_args)

    @patch("gcp_agentless_setup.state_bucket.run_command")
    def test_returns_false_when_bucket_not_found(self, mock_run):
        """Should return False when gcloud describe fails."""
        mock_run.return_value = Mock(success=False)

        result = bucket_exists("nonexistent-bucket")

        self.assertFalse(result)


class TestCreateBucket(unittest.TestCase):
    """Test bucket creation."""

    @patch("gcp_agentless_setup.state_bucket.run_command")
    def test_raises_error_on_creation_failure(self, mock_run):
        """Should raise BucketCreationError when creation fails."""
        mock_run.return_value = Mock(success=False, stderr="permission denied")
        reporter = Mock()

        with self.assertRaises(BucketCreationError) as ctx:
            create_bucket(reporter, "test-bucket", "project", "us-central1")

        self.assertIn("permission denied", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
