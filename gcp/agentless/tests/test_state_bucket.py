# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, patch

from gcp_agentless_setup.errors import BucketCreationError
from gcp_agentless_setup.state_bucket import (
    bucket_exists,
    create_bucket,
)
from gcp_shared.gcloud import CommandResult


class TestBucketExists(unittest.TestCase):
    """Test bucket existence check."""

    @patch("gcp_agentless_setup.state_bucket.try_gcloud")
    def test_returns_true_when_bucket_exists(self, mock_try_gcloud):
        """Should return True when gcloud describe succeeds."""
        mock_try_gcloud.return_value = CommandResult(
            returncode=0, data={"name": "my-bucket"}, error=""
        )

        result = bucket_exists("my-bucket")

        self.assertTrue(result)

    @patch("gcp_agentless_setup.state_bucket.try_gcloud")
    def test_returns_false_when_bucket_not_found(self, mock_try_gcloud):
        """Should return False when gcloud describe fails."""
        mock_try_gcloud.return_value = CommandResult(
            returncode=1, data=None, error="NotFound"
        )

        result = bucket_exists("nonexistent-bucket")

        self.assertFalse(result)


class TestCreateBucket(unittest.TestCase):
    """Test bucket creation."""

    @patch("gcp_agentless_setup.state_bucket.try_gcloud")
    def test_raises_error_on_creation_failure(self, mock_try_gcloud):
        """Should raise BucketCreationError when creation fails."""
        mock_try_gcloud.return_value = CommandResult(
            returncode=1, data=None, error="permission denied"
        )
        reporter = Mock()

        with self.assertRaises(BucketCreationError) as ctx:
            create_bucket(reporter, "test-bucket", "project", "us-central1")

        self.assertIn("permission denied", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
