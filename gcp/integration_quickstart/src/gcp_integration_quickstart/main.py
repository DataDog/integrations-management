#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys

from .integration_configuration import (
    assign_delegate_permissions,
    create_integration_with_permissions,
    find_or_create_service_account,
)
from .models import (
    ConfigurationScope,
    IntegrationConfiguration,
    Project,
    from_dict_recursive,
)
from .reporter import WorkflowReporter
from .requests import dd_request
from .scopes import collect_configuration_scopes
from .workflow import (
    ensure_login,
    is_scopes_step_already_completed,
    is_valid_workflow_id,
    receive_user_selections,
)

REQUIRED_ENVIRONMENT_VARS: set[str] = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "WORKFLOW_ID",
}


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    if missing_environment_vars := REQUIRED_ENVIRONMENT_VARS - os.environ.keys():
        print(
            f"Missing required environment variables: {', '.join(missing_environment_vars)}"
        )
        exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    if not is_valid_workflow_id(workflow_id):
        print(
            f"Workflow ID {workflow_id} has already been used. Please start a new workflow."
        )
        exit(1)

    workflow_reporter = WorkflowReporter(workflow_id, dd_request)

    try:
        with workflow_reporter.report_step("login"):
            ensure_login()
    except Exception as e:
        if "gcloud: command not found" in str(e):
            print(
                "You must install the GCloud CLI and log in to run this script.\nhttps://cloud.google.com/sdk/docs/install"
            )
        else:
            print("You must be logged in to GCloud CLI to run this script.")
        exit(1)
    else:
        print(
            "Connected! Leave this shell running and go back to the Datadog UI to continue."
        )

    with workflow_reporter.report_step("scopes") as step_reporter:
        if not is_scopes_step_already_completed(workflow_id):
            collect_configuration_scopes(step_reporter)
    with workflow_reporter.report_step("selections"):
        user_selections = receive_user_selections(workflow_id)
    with workflow_reporter.report_step("create_service_account") as step_reporter:
        service_account_email = find_or_create_service_account(
            step_reporter,
            user_selections["service_account_id"],
            user_selections["default_project_id"],
        )
    with workflow_reporter.report_step("assign_delegate_permissions") as step_reporter:
        assign_delegate_permissions(
            step_reporter, user_selections["default_project_id"]
        )
    with workflow_reporter.report_step(
        "create_integration_with_permissions"
    ) as step_reporter:
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
        )

    print("Script succeeded. You may exit this shell.")


def sigint_handler(_, __):
    print("Script terminating.")
    sys.exit(0)


if __name__ == "__main__":
    main()
