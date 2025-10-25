# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, call, patch

from shared.models import Folder, Project
from shared.scopes import (
    collect_configuration_scopes,
    fetch_folders,
    fetch_iam_permissions_for,
)


class TestFetchFolders(unittest.TestCase):
    """Test the fetch_folders function."""

    @patch("shared.scopes.request")
    def test_fetch_folders_success(self, mock_request):
        """Test fetch_folders when successful."""
        mock_request.return_value = (
            '{"folders": [{"displayName": "Test Folder", "name": "folders/folder123", "parent": "folders/parent456"}]}',
            200,
        )

        result = fetch_folders("test-token")

        mock_request.assert_called_once_with(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders:search",
            {"query": "lifecycleState=ACTIVE"},
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(
            result,
            [
                {
                    "displayName": "Test Folder",
                    "name": "folders/folder123",
                    "parent": "folders/parent456",
                }
            ],
        )

    @patch("shared.scopes.request")
    def test_fetch_folders_with_pagination(self, mock_request):
        """Test fetch_folders with pagination."""
        # First call returns first page with nextPageToken
        # Second call returns second page without nextPageToken
        mock_request.side_effect = [
            (
                '{"folders": [{"displayName": "Folder 1", "name": "folders/folder1", "parent": "folders/parent1"}], "nextPageToken": "token123"}',
                200,
            ),
            (
                '{"folders": [{"displayName": "Folder 2", "name": "folders/folder2", "parent": "folders/parent2"}]}',
                200,
            ),
        ]

        result = fetch_folders("test-token")

        self.assertEqual(mock_request.call_count, 2)

        mock_request.assert_any_call(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders:search",
            {"query": "lifecycleState=ACTIVE"},
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )

        mock_request.assert_any_call(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders:search",
            {
                "query": "lifecycleState=ACTIVE",
                "pageToken": "token123",
            },
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(
            result,
            [
                {
                    "displayName": "Folder 1",
                    "name": "folders/folder1",
                    "parent": "folders/parent1",
                },
                {
                    "displayName": "Folder 2",
                    "name": "folders/folder2",
                    "parent": "folders/parent2",
                },
            ],
        )

    @patch("shared.scopes.request")
    def test_fetch_folders_api_error(self, mock_request):
        """Test fetch_folders when API returns error."""
        mock_request.return_value = ('{"error": "server error"}', 500)

        with self.assertRaises(RuntimeError) as context:
            fetch_folders("test-token")

        self.assertIn("failed to fetch folders", str(context.exception))


class TestFetchIamPermissionsFor(unittest.TestCase):
    """Test the fetch_iam_permissions_for function."""

    @patch("shared.scopes.request")
    def test_fetch_iam_permissions_for_project(self, mock_request):
        """Test fetch_iam_permissions_for for a project."""
        mock_request.return_value = ('{"permissions": ["test"]}', 200)

        project = Project(
            parent_id="parent123",
            id="project123",
            name="Test Project",
            is_already_monitored=False,
        )

        result_scope, result_response, result_status = fetch_iam_permissions_for(
            project, "test_token"
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v1/projects/project123:testIamPermissions",
            {"permissions": project.required_permissions},
            {
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(result_scope, project)
        self.assertEqual(result_response, '{"permissions": ["test"]}')
        self.assertEqual(result_status, 200)

    @patch("shared.scopes.request")
    def test_fetch_iam_permissions_for_folder(self, mock_request):
        """Test fetch_iam_permissions_for for a folder."""
        mock_request.return_value = ('{"permissions": ["test"]}', 200)

        folder = Folder(parent_id="parent123", id="folder123", name="Test Folder")

        result_scope, result_response, result_status = fetch_iam_permissions_for(
            folder, "test_token"
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders/folder123:testIamPermissions",
            {"permissions": folder.required_permissions},
            {
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(result_scope, folder)
        self.assertEqual(result_response, '{"permissions": ["test"]}')
        self.assertEqual(result_status, 200)


class TestCollectConfigurationScopes(unittest.TestCase):
    """Test the collect_configuration_scopes function."""

    @patch("shared.scopes.gcloud")
    @patch("shared.scopes.dd_request")
    @patch("shared.scopes.request")
    @patch("shared.scopes.fetch_folders")
    def test_collect_configuration_scopes_get_service_accounts_404(
        self, mock_fetch_folders, mock_request, mock_dd_request, mock_gcloud
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns 404 (no existing accounts)."""

        # Mock dd_request response for 404 (no existing accounts)
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        # Mock request responses for IAM permissions checks
        mock_request.return_value = (
            '{"permissions": ["resourcemanager.projects.setIamPolicy", "serviceusage.services.enable"]}',
            200,
        )

        # Mock gcloud responses for auth token and projects
        def gcloud_side_effect(cmd, *_):
            if "auth print-access-token" in cmd:
                return {"token": "test-token"}
            elif "projects list" in cmd:
                return [
                    {
                        "name": "Test Project",
                        "projectId": "test-project",
                        "parent": {"id": "parent123"},
                    }
                ]
            else:
                return None

        mock_gcloud.side_effect = gcloud_side_effect

        # Mock fetch_folders response
        mock_fetch_folders.return_value = [
            {
                "displayName": "Test Folder",
                "name": "folders/folder123",
                "parent": "folders/parent456",
            }
        ]

        step_reporter = Mock()

        # Should not raise an exception
        collect_configuration_scopes(step_reporter)

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )

        # Verify gcloud was called for auth token and projects
        expected_gcloud_calls = [
            call(
                'projects list         --filter="lifecycleState=ACTIVE AND NOT projectId:sys*"',
                "name",
                "projectId",
                "parent.id",
            ),
            call("auth print-access-token"),
        ]
        mock_gcloud.assert_has_calls(expected_gcloud_calls)

        # Verify fetch_folders was called
        mock_fetch_folders.assert_called_once_with("test-token")

        # Verify step_reporter.report was called with metadata
        step_reporter.report.assert_called_once()
        call_args = step_reporter.report.call_args
        self.assertIn("metadata", call_args.kwargs)
        metadata = call_args.kwargs["metadata"]
        self.assertIn("folders", metadata)
        self.assertIn("projects", metadata)

    @patch("shared.scopes.gcloud")
    @patch("shared.scopes.dd_request")
    @patch("shared.scopes.request")
    @patch("shared.scopes.fetch_folders")
    def test_collect_configuration_scopes_get_service_accounts_200(
        self, mock_fetch_folders, mock_request, mock_dd_request, mock_gcloud
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns 200 (existing accounts)."""

        # Mock dd_request response for 200 (existing accounts)
        mock_dd_request.return_value = (
            '{"data": [{"meta": {"accessible_projects": ["existing-project"]}}]}',
            200,
        )

        # Mock request responses for IAM permissions checks
        mock_request.return_value = (
            '{"permissions": ["resourcemanager.projects.setIamPolicy", "serviceusage.services.enable"]}',
            200,
        )

        # Mock gcloud responses for auth token and projects
        def gcloud_side_effect(cmd, *_):
            if "auth print-access-token" in cmd:
                return {"token": "test-token"}
            elif "projects list" in cmd:
                return [
                    {
                        "name": "Test Project",
                        "projectId": "test-project",
                        "parent": {"id": "parent123"},
                    }
                ]
            else:
                return None

        mock_gcloud.side_effect = gcloud_side_effect

        # Mock fetch_folders response
        mock_fetch_folders.return_value = [
            {
                "displayName": "Test Folder",
                "name": "folders/folder123",
                "parent": "folders/parent456",
            }
        ]

        step_reporter = Mock()

        collect_configuration_scopes(step_reporter)

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )

        # Verify gcloud was called for auth token and projects
        expected_gcloud_calls = [
            call(
                'projects list         --filter="lifecycleState=ACTIVE AND NOT projectId:sys*"',
                "name",
                "projectId",
                "parent.id",
            ),
            call("auth print-access-token"),
        ]
        mock_gcloud.assert_has_calls(expected_gcloud_calls)

        # Verify fetch_folders was called
        mock_fetch_folders.assert_called_once_with("test-token")

        # Verify step_reporter.report was called with metadata
        step_reporter.report.assert_called_once()
        call_args = step_reporter.report.call_args
        self.assertIn("metadata", call_args.kwargs)
        metadata = call_args.kwargs["metadata"]
        self.assertIn("folders", metadata)
        self.assertIn("projects", metadata)

    @patch("shared.scopes.dd_request")
    def test_collect_configuration_scopes_get_service_accounts_error(
        self, mock_dd_request
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns an error status."""

        # Mock dd_request response for error (500)
        mock_dd_request.return_value = ('{"error": "server error"}', 500)

        step_reporter = Mock()

        # Should raise an exception
        with self.assertRaises(RuntimeError) as context:
            collect_configuration_scopes(step_reporter)

        self.assertIn("failed to get service accounts", str(context.exception))

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )


if __name__ == "__main__":
    unittest.main()
