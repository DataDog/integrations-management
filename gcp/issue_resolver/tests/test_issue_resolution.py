# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from gcp_issue_resolver.issue_resolution import diagnose_issues, resolve_issues
from gcp_issue_resolver.models import IssueResolverConfiguration
from gcp_shared.models import ConfigurationScope, Project


class TestIssueResolution:
    def test_diagnose_issues_no_issues(self):
        """Test diagnose_issues when no issues are found."""
        step_reporter = MagicMock()
        service_account_email = "test@example.com"
        config = IssueResolverConfiguration(
            issue_types=["permissions"],
            auto_fix_enabled=True,
            dry_run=False,
            notification_preferences={}
        )
        scope = ConfigurationScope(
            projects=[Project(id="test-project", name="Test Project")],
            folders=[]
        )

        issues = diagnose_issues(step_reporter, service_account_email, config, scope)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_resolve_issues_no_issues(self):
        """Test resolve_issues when there are no issues."""
        step_reporter = MagicMock()
        service_account_email = "test@example.com"
        config = IssueResolverConfiguration(
            issue_types=["permissions"],
            auto_fix_enabled=True,
            dry_run=False,
            notification_preferences={}
        )
        issues = []

        resolve_issues(step_reporter, service_account_email, issues, config)

        # Verify that the "No issues to resolve" message was reported
        step_reporter.report.assert_called()

    def test_resolve_issues_dry_run(self):
        """Test resolve_issues in dry run mode."""
        step_reporter = MagicMock()
        service_account_email = "test@example.com"
        config = IssueResolverConfiguration(
            issue_types=["permissions"],
            auto_fix_enabled=True,
            dry_run=True,
            notification_preferences={}
        )
        issues = [
            {"type": "permission_missing", "id": "issue-1"},
            {"type": "api_disabled", "id": "issue-2"}
        ]

        resolve_issues(step_reporter, service_account_email, issues, config)

        # Verify that dry run messages were reported
        assert step_reporter.report.call_count > 0


