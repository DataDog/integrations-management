# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys
from enum import Enum
from typing import Optional

from gcp_shared.models import (
    ConfigurationScope,
    Project,
    from_dict_recursive,
)
from gcp_shared.reporter import WorkflowReporter
from gcp_shared.scopes import collect_configuration_scopes
from gcp_shared.service_accounts import find_or_create_service_account

from .integration_configuration import (
    assign_delegate_permissions,
    create_integration_with_permissions,
)
from .models import IntegrationConfiguration, ProductRequirements

REQUIRED_ENVIRONMENT_VARS: set[str] = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "WORKFLOW_ID",
}

WORKFLOW_TYPE: str = "gcp-integration-setup"


class OnboardingStep(str, Enum):
    SCOPES = "scopes"
    SELECTIONS = "selections"
    CREATE_SERVICE_ACCOUNT = "create_service_account"
    ASSIGN_DELEGATE_PERMISSIONS = "assign_delegate_permissions"
    CREATE_INTEGRATION_WITH_PERMISSIONS = "create_integration_with_permissions"


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    if missing_environment_vars := REQUIRED_ENVIRONMENT_VARS - os.environ.keys():
        print(
            f"Missing required environment variables: {', '.join(missing_environment_vars)}"
        )
        exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    workflow_reporter = WorkflowReporter(workflow_id, WORKFLOW_TYPE)

    if not workflow_reporter.is_valid_workflow_id(
        OnboardingStep.CREATE_INTEGRATION_WITH_PERMISSIONS
    ):
        print(
            f"Workflow ID {workflow_id} has already been used. Please start a new workflow."
        )
        exit(1)

    workflow_reporter.handle_login_step()

    with workflow_reporter.report_step(OnboardingStep.SCOPES) as step_reporter:
        if not workflow_reporter.is_scopes_step_already_completed():
            collect_configuration_scopes(step_reporter)

    with workflow_reporter.report_step(OnboardingStep.SELECTIONS):
        user_selections = workflow_reporter.receive_user_selections()
    with workflow_reporter.report_step(
        OnboardingStep.CREATE_SERVICE_ACCOUNT
    ) as step_reporter:
        service_account_email = find_or_create_service_account(
            step_reporter,
            user_selections["service_account_id"],
            user_selections["default_project_id"],
        )
    with workflow_reporter.report_step(
        OnboardingStep.ASSIGN_DELEGATE_PERMISSIONS
    ) as step_reporter:
        assign_delegate_permissions(
            step_reporter,
            service_account_email,
            user_selections["default_project_id"],
        )
    with workflow_reporter.report_step(
        OnboardingStep.CREATE_INTEGRATION_WITH_PERMISSIONS
    ) as step_reporter:
        product_requirements: Optional[ProductRequirements] = (
            ProductRequirements(**user_selections["product_requirements"])
            if "product_requirements" in user_selections
            else None
        )

        create_integration_with_permissions(
            step_reporter,
            service_account_email,
            IntegrationConfiguration(**user_selections["integration_configuration"]),
            ConfigurationScope(
                projects=[
                    Project(**project)
                    for project in user_selections.get("projects", [])
                ],
                folders=[
                    from_dict_recursive(folder)
                    for folder in user_selections.get("folders", [])
                ],
            ),
            product_requirements,
        )

    print("Script succeeded. You may exit this shell.")


def sigint_handler(_, __):
    print("Script terminating.")
    sys.exit(0)


if __name__ == "__main__":
    main()
