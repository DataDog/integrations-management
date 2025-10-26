#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys
from enum import Enum

from gcp_shared.models import (
    ConfigurationScope,
    Project,
    from_dict_recursive,
)
from gcp_shared.reporter import WorkflowReporter
from gcp_shared.scopes import collect_configuration_scopes
from gcp_shared.service_accounts import find_or_create_service_account

from .dataflow_configuration import (
    assign_required_dataflow_roles,
    create_dataflow_job,
    create_log_sinks,
    create_secret_manager_entry,
    create_topics_with_subscription,
)
from .models import ExclusionFilter

REQUIRED_ENVIRONMENT_VARS: set[str] = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "WORKFLOW_ID",
}

WORKFLOW_TYPE: str = "gcp-log-forwarding-setup"


class GCPLogForwardingQuickstartSteps(str, Enum):
    SCOPES = "scopes"
    SELECTIONS = "selections"
    CREATE_TOPIC_WITH_SUBSCRIPTION = "create_topic_with_subscription"
    CREATE_SERVICE_ACCOUNT = "create_service_account"
    ASSIGN_REQUIRED_DATAFLOW_ROLES = "assign_required_dataflow_roles"
    CREATE_SECRET_MANAGER_ENTRY = "create_secret_manager_entry"
    CREATE_LOG_SINKS = "create_log_sinks"
    CREATE_DATAFLOW_JOB = "create_dataflow_job"


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
        GCPLogForwardingQuickstartSteps.CREATE_DATAFLOW_JOB
    ):
        print(
            f"Workflow ID {workflow_id} has already been used. Please start a new workflow."
        )
        exit(1)

    workflow_reporter.handle_login_step()

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.SCOPES
    ) as step_reporter:
        if not workflow_reporter.is_scopes_step_already_completed():
            collect_configuration_scopes(step_reporter)

    with workflow_reporter.report_step(GCPLogForwardingQuickstartSteps.SELECTIONS):
        user_selections = workflow_reporter.receive_user_selections()
        default_project_id = user_selections["default_project_id"]

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.CREATE_TOPIC_WITH_SUBSCRIPTION
    ) as step_reporter:
        create_topics_with_subscription(
            step_reporter,
            default_project_id,
        )
    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.CREATE_SERVICE_ACCOUNT
    ) as step_reporter:
        datadog_dataflow_service_account_id = "datadog-dataflow"
        service_account_email = find_or_create_service_account(
            step_reporter,
            datadog_dataflow_service_account_id,
            default_project_id,
            display_name="Datadog Dataflow Service Account",
        )

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.ASSIGN_REQUIRED_DATAFLOW_ROLES
    ) as step_reporter:
        assign_required_dataflow_roles(
            step_reporter, service_account_email, default_project_id
        )

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.CREATE_SECRET_MANAGER_ENTRY
    ) as step_reporter:
        create_secret_manager_entry(
            step_reporter,
            default_project_id,
            service_account_email,
        )

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.CREATE_LOG_SINKS
    ) as step_reporter:
        create_log_sinks(
            step_reporter,
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
            inclusion_filter=user_selections.get("inclusion_filter", ""),
            exclusion_filters=[
                ExclusionFilter(**exclusion)
                for exclusion in user_selections.get("exclusion_filters", [])
            ],
        )

    with workflow_reporter.report_step(
        GCPLogForwardingQuickstartSteps.CREATE_DATAFLOW_JOB
    ) as step_reporter:
        create_dataflow_job(
            step_reporter,
            default_project_id,
            service_account_email,
            user_selections["region"],
            user_selections["is_dataflow_prime_enabled"],
        )

    print("Script succeeded. You may exit this shell.")


def sigint_handler(_, __):
    print("Script terminating.")
    sys.exit(0)


if __name__ == "__main__":
    main()
