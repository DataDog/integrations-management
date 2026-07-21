# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import logging
import os
import sys
from enum import Enum
from typing import Any, Optional

from gcp_shared.ensure_permissions import ensure_service_account_permissions, is_valid_service_account_email
from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.reporter import WorkflowReporter
from gcp_shared.requests import dd_request

log = logging.getLogger(__name__)

# Canonical source: gcp/integration_quickstart/src/gcp_integration_quickstart/integration_configuration.py
REQUIRED_ROLES: list[str] = [
    "roles/cloudasset.viewer",
    "roles/browser",
    "roles/compute.viewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
]

REQUIRED_ENV_VARS: set[str] = {"DD_API_KEY", "DD_APP_KEY", "DD_SITE"}

WORKFLOW_TYPE: str = "gcp-permission-repair"


class RepairStep(str, Enum):
    SELECTIONS = "selections"
    ENSURE_PERMISSIONS = "ensure_permissions"
    ASSIGN_DELEGATE_PERMISSIONS = "assign_delegate_permissions"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _check_env_vars()
    if "WORKFLOW_ID" in os.environ:
        _run_ui_mode()
    else:
        _run_cli_mode()


def _run_cli_mode() -> None:
    email, project_ids = _parse_args(sys.argv)
    if not is_valid_service_account_email(email):
        raise ValueError(f"Invalid service account email: '{email}'")
    reporter = LoggingStepReporter()
    fix_permissions(reporter, email, project_ids)
    log.info("Done. All permissions applied successfully.")


def _run_ui_mode() -> None:
    workflow_id = os.environ["WORKFLOW_ID"]
    workflow_reporter = WorkflowReporter(workflow_id, WORKFLOW_TYPE)

    if not workflow_reporter.is_valid_workflow_id(RepairStep.ASSIGN_DELEGATE_PERMISSIONS):
        log.error(f"Workflow ID {workflow_id} has already been used. Please start a new workflow.")
        sys.exit(1)

    workflow_reporter.handle_login_step()

    with workflow_reporter.report_step(RepairStep.SELECTIONS):
        user_selections = workflow_reporter.receive_user_selections()

    email = user_selections["email"]
    if not is_valid_service_account_email(email):
        raise ValueError(f"Invalid service account email: '{email}'")
    project_ids = user_selections["project_ids"]

    with workflow_reporter.report_step(RepairStep.ENSURE_PERMISSIONS) as step_reporter:
        for project_id in project_ids:
            step_reporter.report(message=f"Fixing permissions for project '{project_id}'...")
            ensure_service_account_permissions(step_reporter, project_id, email, REQUIRED_ROLES)

    with workflow_reporter.report_step(RepairStep.ASSIGN_DELEGATE_PERMISSIONS) as step_reporter:
        _apply_delegate_permissions(step_reporter, email, _project_from_email(email))

    print("Script succeeded. You may exit this shell.")


def fix_permissions(reporter: Any, email: str, project_ids: list[str]) -> None:
    for project_id in project_ids:
        log.info(f"Fixing permissions for project '{project_id}'...")
        ensure_service_account_permissions(reporter, project_id, email, REQUIRED_ROLES)
    _apply_delegate_permissions(reporter, email, _project_from_email(email))


def _apply_delegate_permissions(reporter: Any, email: str, project_id: str) -> None:
    reporter.report(message=f"Fetching Datadog STS delegate for service account '{email}'...")
    response, status = dd_request("GET", "/api/v2/integration/gcp/sts_delegate")
    if status != 200 or not response:
        raise RuntimeError("Failed to get STS delegate from Datadog API")
    datadog_principal = json.loads(response)["data"]["id"]
    reporter.report(message=f"Assigning [roles/iam.serviceAccountTokenCreator] to '{datadog_principal}' on '{email}'")
    gcloud(
        GcloudCmd("iam service-accounts", "add-iam-policy-binding")
        .arg(email)
        .param("--member", f"serviceAccount:{datadog_principal}")
        .param("--role", "roles/iam.serviceAccountTokenCreator")
        .param("--condition", "None")
        .param("--project", project_id)
        .flag("--quiet")
    )


def _check_env_vars() -> None:
    missing = REQUIRED_ENV_VARS - os.environ.keys()
    if missing:
        log.error(f"Missing required environment variables: {', '.join(sorted(missing))}")
        sys.exit(1)


def _parse_args(argv: list[str]) -> tuple[str, list[str]]:
    if len(argv) < 3:
        log.error("Usage: python -m gcp_issue_resolver.main <email> <project_id> [<project_id> ...]")
        sys.exit(1)
    return argv[1], argv[2:]


def _project_from_email(email: str) -> str:
    return email.split("@")[1].split(".")[0]


class LoggingStepReporter:
    def report(self, message: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> None:
        if message:
            log.info(message)


if __name__ == "__main__":
    main()
