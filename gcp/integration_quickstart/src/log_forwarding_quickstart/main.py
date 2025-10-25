#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys

from .dataflow_configuration import (
    create_secret_manager_entry,
    create_topics_with_subscription,
    assign_required_dataflow_roles,
    create_log_sinks,
    create_dataflow_job,
)
from ..gcp_integration_quickstart.reporter import WorkflowReporter
from ..shared.models import (
    ConfigurationScope,
    Project,
    from_dict_recursive,
)
from ..shared.requests import dd_request
from ..shared.scopes import collect_configuration_scopes
from ..shared.service_accounts import find_or_create_service_account
from ..shared.workflow import (
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
        default_project_id = user_selections["default_project_id"]

    with workflow_reporter.report_step(
        "create_topic_with_subscription"
    ) as step_reporter:
        create_topics_with_subscription(
            default_project_id,
        )
    with workflow_reporter.report_step("create_service_account") as step_reporter:
        datadog_dataflow_service_account_id = "datadog-dataflow"
        service_account_email = find_or_create_service_account(
            step_reporter,
            datadog_dataflow_service_account_id,
            default_project_id,
            display_name="Datadog Dataflow Service Account",
        )

    with workflow_reporter.report_step(
        "assign_required_dataflow_roles"
    ) as step_reporter:
        assign_required_dataflow_roles(service_account_email, default_project_id)

    with workflow_reporter.report_step("create_secret_manager_entry") as step_reporter:
        create_secret_manager_entry(
            default_project_id,
            service_account_email,
        )

    with workflow_reporter.report_step("create_log_sinks") as step_reporter:
        create_log_sinks(
            default_project_id,
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

    with workflow_reporter.report_step("create_dataflow_job") as step_reporter:
        create_dataflow_job(
            default_project_id,
            service_account_email,
            user_selections["region"],
        )

    print("Script succeeded. You may exit this shell.")


def sigint_handler(_, __):
    print("Script terminating.")
    sys.exit(0)


if __name__ == "__main__":
    main()
