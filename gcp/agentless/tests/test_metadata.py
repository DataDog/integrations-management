# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import patch

from gcp_agentless_setup.config import Config
from gcp_agentless_setup.errors import MetadataError
from gcp_agentless_setup.metadata import (
    DeploymentMetadata,
    METADATA_VERSION,
    merge_with_config,
    read_metadata,
    write_metadata,
)


def _make_config(**overrides) -> Config:
    defaults = dict(
        api_key="key",
        app_key="app",
        site="datadoghq.com",
        workflow_id="wf-1",
        scanner_project="scanner-proj",
        regions=["us-east1"],
        projects_to_scan=["scanner-proj", "other-proj"],
    )
    defaults.update(overrides)
    return Config(**defaults)


def _make_metadata(**overrides) -> DeploymentMetadata:
    defaults = dict(
        scanner_project="scanner-proj",
        regions=["us-east1"],
        projects_to_scan=["other-proj", "scanner-proj"],
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return DeploymentMetadata(**defaults)


class TestDeploymentMetadata(unittest.TestCase):
    """Test DeploymentMetadata serialization."""

    def test_to_dict_includes_version_and_sorted_lists(self):
        meta = _make_metadata(regions=["europe-west1", "us-east1"])
        d = meta.to_dict()

        self.assertEqual(d["version"], METADATA_VERSION)
        self.assertEqual(d["regions"], ["europe-west1", "us-east1"])
        self.assertEqual(d["scanner_project"], "scanner-proj")

    def test_roundtrip(self):
        original = _make_metadata(regions=["b-region", "a-region"])
        restored = DeploymentMetadata.from_dict(original.to_dict())

        self.assertEqual(restored.scanner_project, original.scanner_project)
        self.assertEqual(restored.regions, sorted(original.regions))
        self.assertEqual(restored.projects_to_scan, sorted(original.projects_to_scan))
        self.assertEqual(restored.created_at, original.created_at)

    def test_from_dict_handles_missing_optional_fields(self):
        data = {"scanner_project": "proj"}
        meta = DeploymentMetadata.from_dict(data)

        self.assertEqual(meta.regions, [])
        self.assertEqual(meta.projects_to_scan, [])
        self.assertEqual(meta.created_at, "")


class TestMergeWithConfig(unittest.TestCase):
    """Test merge_with_config logic."""

    def test_first_deploy_creates_metadata_from_config(self):
        config = _make_config(regions=["us-east1"], projects_to_scan=["proj-a"])
        result = merge_with_config(None, config)

        self.assertEqual(result.scanner_project, "scanner-proj")
        self.assertEqual(result.regions, ["us-east1"])
        self.assertIn("scanner-proj", result.projects_to_scan)
        self.assertIn("proj-a", result.projects_to_scan)
        self.assertTrue(result.created_at)
        self.assertEqual(result.created_at, result.modified_at)

    def test_additive_merge_unions_regions(self):
        existing = _make_metadata(regions=["us-east1"])
        config = _make_config(regions=["europe-west1"])
        result = merge_with_config(existing, config)

        self.assertEqual(result.regions, ["europe-west1", "us-east1"])

    def test_additive_merge_unions_projects(self):
        existing = _make_metadata(projects_to_scan=["scanner-proj", "proj-a"])
        config = _make_config(projects_to_scan=["scanner-proj", "proj-b"])
        result = merge_with_config(existing, config)

        self.assertEqual(
            sorted(result.projects_to_scan),
            ["proj-a", "proj-b", "scanner-proj"],
        )

    def test_duplicate_regions_are_deduplicated(self):
        existing = _make_metadata(regions=["us-east1"])
        config = _make_config(regions=["us-east1"])
        result = merge_with_config(existing, config)

        self.assertEqual(result.regions, ["us-east1"])

    def test_preserves_created_at_from_existing(self):
        existing = _make_metadata(created_at="2025-06-01T00:00:00+00:00")
        config = _make_config()
        result = merge_with_config(existing, config)

        self.assertEqual(result.created_at, "2025-06-01T00:00:00+00:00")
        self.assertNotEqual(result.modified_at, result.created_at)

    def test_scanner_project_mismatch_raises(self):
        existing = _make_metadata(scanner_project="project-a")
        config = _make_config(scanner_project="project-b")

        with self.assertRaises(MetadataError) as ctx:
            merge_with_config(existing, config)
        self.assertIn("mismatch", ctx.exception.message.lower())


class TestReadMetadata(unittest.TestCase):
    """Test read_metadata with mocked GCS calls."""

    @patch("gcp_agentless_setup.metadata._download_metadata")
    @patch("gcp_agentless_setup.metadata._get_object_generation")
    def test_returns_none_when_object_does_not_exist(self, mock_gen, mock_dl):
        mock_gen.return_value = None

        meta, gen = read_metadata("bucket")

        self.assertIsNone(meta)
        self.assertEqual(gen, 0)
        mock_dl.assert_not_called()

    @patch("gcp_agentless_setup.metadata._download_metadata")
    @patch("gcp_agentless_setup.metadata._get_object_generation")
    def test_returns_parsed_metadata(self, mock_gen, mock_dl):
        mock_gen.return_value = 42
        mock_dl.return_value = json.dumps({
            "scanner_project": "proj",
            "regions": ["us-east1"],
            "projects_to_scan": ["proj"],
            "created_at": "t0",
            "modified_at": "t1",
        })

        meta, gen = read_metadata("bucket")

        self.assertEqual(gen, 42)
        self.assertEqual(meta.scanner_project, "proj")
        self.assertEqual(meta.regions, ["us-east1"])

    @patch("gcp_agentless_setup.metadata._download_metadata")
    @patch("gcp_agentless_setup.metadata._get_object_generation")
    def test_generation_fetched_before_content(self, mock_gen, mock_dl):
        """Verify generation is checked first to avoid reading newer content with stale generation."""
        call_order = []
        mock_gen.side_effect = lambda b: (call_order.append("generation"), 1)[1]
        mock_dl.side_effect = lambda b: (call_order.append("download"), '{"scanner_project":"p","regions":[],"projects_to_scan":[]}')[1]

        read_metadata("bucket")

        self.assertEqual(call_order, ["generation", "download"])

    @patch("gcp_agentless_setup.metadata._download_metadata")
    @patch("gcp_agentless_setup.metadata._get_object_generation")
    def test_corrupt_json_raises_metadata_error(self, mock_gen, mock_dl):
        mock_gen.return_value = 1
        mock_dl.return_value = "not valid json{{"

        with self.assertRaises(MetadataError) as ctx:
            read_metadata("bucket")
        self.assertIn("corrupt", ctx.exception.detail.lower())


class TestWriteMetadata(unittest.TestCase):
    """Test write_metadata with mocked GCS calls."""

    @patch("gcp_agentless_setup.metadata._upload_metadata_cas")
    def test_writes_on_first_attempt(self, mock_upload):
        mock_upload.return_value = True
        meta = _make_metadata()

        write_metadata("bucket", meta, 0)

        mock_upload.assert_called_once()
        content = mock_upload.call_args[0][1]
        self.assertIn("scanner-proj", content)

    @patch("gcp_agentless_setup.metadata.read_metadata")
    @patch("gcp_agentless_setup.metadata._upload_metadata_cas")
    def test_retries_on_generation_conflict(self, mock_upload, mock_read):
        mock_upload.side_effect = [False, True]
        mock_read.return_value = (_make_metadata(), 99)

        write_metadata("bucket", _make_metadata(), 0)

        self.assertEqual(mock_upload.call_count, 2)
        self.assertEqual(mock_upload.call_args_list[1][0][2], 99)

    @patch("gcp_agentless_setup.metadata.read_metadata")
    @patch("gcp_agentless_setup.metadata._upload_metadata_cas")
    def test_retry_re_merges_with_config(self, mock_upload, mock_read):
        """On conflict, the retry should re-merge remote metadata with our config."""
        remote = _make_metadata(regions=["asia-east1"])
        mock_upload.side_effect = [False, True]
        mock_read.return_value = (remote, 99)

        config = _make_config(regions=["europe-west1"])
        local = _make_metadata(regions=["europe-west1"])

        write_metadata("bucket", local, 0, config=config)

        final_content = mock_upload.call_args_list[1][0][1]
        written = json.loads(final_content)
        self.assertIn("asia-east1", written["regions"])
        self.assertIn("europe-west1", written["regions"])

    @patch("gcp_agentless_setup.metadata.read_metadata")
    @patch("gcp_agentless_setup.metadata._upload_metadata_cas")
    def test_raises_after_max_attempts(self, mock_upload, mock_read):
        mock_upload.return_value = False
        mock_read.return_value = (_make_metadata(), 1)

        with self.assertRaises(MetadataError) as ctx:
            write_metadata("bucket", _make_metadata(), 0)
        self.assertIn("3 attempts", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
