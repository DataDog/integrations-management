# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from typing import Any

from gcp_shared.gcloud import gcloud
from gcp_shared.models import ConfigurationScope
from gcp_shared.reporter import StepStatusReporter
from gcp_shared.requests import dd_request

from .models import IssueResolverConfiguration


def diagnose_issues(
    step_reporter: StepStatusReporter,
    service_account_email: str,
    issue_resolver_configuration: IssueResolverConfiguration,
    configuration_scope: ConfigurationScope,
) -> list[dict[str, Any]]:
    """Diagnose issues in the GCP integration."""

    step_reporter.report(
        message=(
            f"Diagnosing issues for service account '{service_account_email}'..."
        )
    )

    issues: list[dict[str, Any]] = []


    # Check permissions for folders
    for folder in configuration_scope.folders:
        step_reporter.report(
            message=f"Checking permissions for folder '{folder.name}'"
        )
        # TODO: Add actual issue detection logic here
        # This is a placeholder for the actual implementation
        pass

    # Check permissions for projects
    for project in configuration_scope.projects:
        step_reporter.report(
            message=f"Checking permissions for project '{project.name}'"
        )
        # TODO: Add actual issue detection logic here
        # This is a placeholder for the actual implementation
        pass

    step_reporter.report(
        message=f"Found {len(issues)} issue(s)",
        metadata={"issues": issues}
    )

    return issues


def resolve_issues(
    step_reporter: StepStatusReporter,
    service_account_email: str,
    issues: list[dict[str, Any]],
    issue_resolver_configuration: IssueResolverConfiguration,
) -> None:
    """Resolve identified issues in the GCP integration."""

    if not issues:
        step_reporter.report(message="No issues to resolve")
        return

    step_reporter.report(
        message=f"Resolving {len(issues)} issue(s)..."
    )

    resolved_count = 0
    failed_count = 0

    for issue in issues:
        issue_type = issue.get("type", "unknown")
        issue_id = issue.get("id", "unknown")

        try:
            if issue_resolver_configuration.dry_run:
                step_reporter.report(
                    message=f"[DRY RUN] Would resolve issue: {issue_type} ({issue_id})"
                )
            else:
                step_reporter.report(
                    message=f"Resolving issue: {issue_type} ({issue_id})"
                )
                # TODO: Add actual issue resolution logic here
                # This is a placeholder for the actual implementation
                pass

            resolved_count += 1

        except Exception as e:
            step_reporter.report(
                message=f"Failed to resolve issue {issue_id}: {str(e)}"
            )
            failed_count += 1

    step_reporter.report(
        message=f"Resolution complete: {resolved_count} resolved, {failed_count} failed",
        metadata={
            "resolved_count": resolved_count,
            "failed_count": failed_count
        }
    )

