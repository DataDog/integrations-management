# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import re

from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.reporter import StepStatusReporter
from gcp_shared.service_accounts import find_or_create_service_account

SERVICE_ACCOUNT_EMAIL_PATTERN = re.compile(r"^[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com$")


def is_valid_service_account_email(email: str) -> bool:
    return bool(SERVICE_ACCOUNT_EMAIL_PATTERN.match(email))


def validate_service_account_in_project(
    step_reporter: StepStatusReporter, email: str, project_id: str
) -> None:
    step_reporter.report(message=f"Verifying service account '{email}' exists in project '{project_id}'...")
    results = gcloud(
        GcloudCmd("iam service-accounts", "list")
        .param("--project", project_id)
        .param_equals("--filter", f"email='{email}'"),
        "email",
    )
    if not results:
        raise RuntimeError(f"Service account '{email}' not found in project '{project_id}'")


def _bind_role_to_project(
    step_reporter: StepStatusReporter,
    service_account_email: str,
    project_id: str,
    role: str,
) -> None:
    step_reporter.report(
        message=f"Assigning role [{role}] to '{service_account_email}' in project '{project_id}'"
    )
    gcloud(
        GcloudCmd("projects", "add-iam-policy-binding")
        .arg(project_id)
        .param("--member", f"serviceAccount:{service_account_email}")
        .param("--role", role)
        .param("--condition", "None")  # required by GCP even when no conditions are used
        .flag("--quiet")
    )


def ensure_service_account_permissions(
    step_reporter: StepStatusReporter,
    project_id: str,
    service_account_email: str,
    required_roles: list[str],
) -> None:
    validate_service_account_in_project(step_reporter, service_account_email, project_id)
    for role in required_roles:
        _bind_role_to_project(step_reporter, service_account_email, project_id, role)


def create_service_account_with_permissions(
    step_reporter: StepStatusReporter,
    project_id: str,
    sa_name: str,
    required_roles: list[str],
    display_name: str = "Datadog Service Account",
) -> str:
    email = find_or_create_service_account(step_reporter, sa_name, project_id, display_name)
    for role in required_roles:
        _bind_role_to_project(step_reporter, email, project_id, role)
    return email
