# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.reporter import StepStatusReporter


def find_or_create_service_account(
    step_reporter: StepStatusReporter,
    name: str,
    project_id: str,
    display_name: str = "Datadog Service Account",
) -> str:
    """Create a service account with the given name in the specified project."""
    step_reporter.report(
        message=f"Looking for service account '{name}' in project '{project_id}'..."
    )

    service_account_search = gcloud(
        GcloudCmd("iam service-accounts", "list")
        .param("--project", project_id)
        .param_equals("--filter", f"email~'{name}'"),
        "email",
    )
    if service_account_search and len(service_account_search) > 0:
        email = service_account_search[0]["email"]
        step_reporter.report(message=f"Found existing service account '{email}'")
        return email

    step_reporter.report(
        message=f"Creating new service account '{name}' in project '{project_id}'..."
    )

    resp = gcloud(
        GcloudCmd("iam service-accounts", "create")
        .arg(name)
        .param("--display-name", display_name)
        .param("--project", project_id),
        "email",
    )

    return resp["email"]
