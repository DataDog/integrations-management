# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys

from gcp_shared.models import (
    ConfigurationScope,
    Project,
    from_dict_recursive,
)
from gcp_shared.gcloud import gcloud
from gcp_shared.service_accounts import find_service_account

from .issue_resolution import (
    diagnose_issues,
    resolve_issues,
)
from .models import IssueResolverConfiguration

REQUIRED_ENVIRONMENT_VARS: set[str] = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "SERVICE_ACCOUNT_ID",
    "DEFAULT_PROJECT_ID",
}


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    missing_environment_vars = REQUIRED_ENVIRONMENT_VARS - os.environ.keys()
    if missing_environment_vars:
        print(
            f"Missing required environment variables: {', '.join(missing_environment_vars)}"
        )
        sys.exit(1)
        
    if not gcloud.is_logged_in():
        print("You must be logged in to GCloud CLI to run this script.")
        sys.exit(1)
    
    service_account_email = find_service_account(os.environ["SERVICE_ACCOUNT_ID"], os.environ["DEFAULT_PROJECT_ID"])
    if not service_account_email:
        print(f"Service account '{os.environ['SERVICE_ACCOUNT_ID']}' not found in project '{os.environ['DEFAULT_PROJECT_ID']}'")
        sys.exit(1)

    # workflow_reporter.handle_login_step()

    # with workflow_reporter.report_step(OnboardingStep.SCOPES) as step_reporter:
    #     if not workflow_reporter.is_scopes_step_already_completed():
    #         collect_configuration_scopes(step_reporter)

    # with workflow_reporter.report_step(OnboardingStep.SELECTIONS):
    #     user_selections = workflow_reporter.receive_user_selections()
    # with workflow_reporter.report_step(
    #     OnboardingStep.CREATE_SERVICE_ACCOUNT
    # ) as step_reporter:
    #     service_account_email = find_or_create_service_account(
    #         step_reporter,
    #         user_selections["service_account_id"],
    #         user_selections["default_project_id"],
    #     )
    # with workflow_reporter.report_step(
    #     OnboardingStep.DIAGNOSE_ISSUES
    # ) as step_reporter:
    #     issues = diagnose_issues(
    #         step_reporter,
    #         service_account_email,
    #         IssueResolverConfiguration(**user_selections["issue_resolver_configuration"]),
    #         ConfigurationScope(
    #             projects=[
    #                 Project(**project)
    #                 for project in user_selections.get("projects", [])
    #             ],
    #             folders=[
    #                 from_dict_recursive(folder)
    #                 for folder in user_selections.get("folders", [])
    #             ],
    #         ),
    #     )
    # with workflow_reporter.report_step(
    #     OnboardingStep.RESOLVE_ISSUES
    # ) as step_reporter:
    #     resolve_issues(
    #         step_reporter,
    #         service_account_email,
    #         issues,
    #         IssueResolverConfiguration(**user_selections["issue_resolver_configuration"]),
    #     )

    print("Script succeeded. You may exit this shell.")


def sigint_handler(_, __):
    print("Script terminating.")
    sys.exit(0)


if __name__ == "__main__":
    main()
