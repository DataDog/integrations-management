# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from dataclasses import asdict

from .models import IntegrationConfiguration
from .reporter import StepStatusReporter
from ..shared.gcloud import gcloud
from ..shared.models import ConfigurationScope
from ..shared.requests import dd_request
from ..shared.service_accounts import find_or_create_service_account

ROLE_TO_REQUIRED_API: dict[str, str] = {
    "roles/cloudasset.viewer": "cloudasset.googleapis.com",
    "roles/compute.viewer": "compute.googleapis.com",
    "roles/monitoring.viewer": "monitoring.googleapis.com",
    "roles/browser": "cloudresourcemanager.googleapis.com",
}

ROLES_TO_ADD: list[str] = [
    "roles/cloudasset.viewer",
    "roles/browser",
    "roles/compute.viewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
]


def assign_delegate_permissions(
    step_reporter: StepStatusReporter, project_id: str
) -> None:
    """Assign the roles/iam.serviceAccountTokenCreator role to the Datadog service account in the specified project."""

    step_reporter.report(
        message=f"Fetching Datadog STS delegate for project '{project_id}'..."
    )

    response, status = dd_request("GET", "/api/v2/integration/gcp/sts_delegate")
    if status != 200 or not response:
        raise RuntimeError("failed to get sts delegate")

    json_response = json.loads(response)
    datadog_principal = json_response["data"]["id"]

    step_reporter.report(
        message=f"Assigning role [roles/iam.serviceAccountTokenCreator] to principal '{datadog_principal}' in project '{project_id}'"
    )

    gcloud(
        f'projects add-iam-policy-binding "{project_id}" \
                --member="serviceAccount:{datadog_principal}" \
                --role="roles/iam.serviceAccountTokenCreator" \
                --condition=None \
                --quiet \
                '
    )


def create_integration_with_permissions(
    step_reporter: StepStatusReporter,
    service_account_email: str,
    integration_configuration: IntegrationConfiguration,
    configuration_scope: ConfigurationScope,
):
    """Create the GCP integration in Datadog with the specified permissions."""

    services_to_enable = " ".join(ROLE_TO_REQUIRED_API.values())
    for folder in configuration_scope.folders:
        for child_project in filter(
            lambda c: c.resource_container_type == "project", folder.child_scopes
        ):
            step_reporter.report(
                message=f"Enabling required APIs [{', '.join(ROLE_TO_REQUIRED_API.values())}] for project '{child_project.name}'"
            )

            gcloud(
                f"services enable {services_to_enable} \
                --project={child_project.id} \
                --quiet"
            )

        for role in ROLES_TO_ADD:
            step_reporter.report(
                message=f"Assigning role [{role}] to service account '{service_account_email}' in folder '{folder.name}'"
            )

            gcloud(
                f'resource-manager folders add-iam-policy-binding "{folder.id}" \
                --member="serviceAccount:{service_account_email}" \
                --role="{role}" \
                --condition=None \
                --quiet \
                '
            )

    for project in configuration_scope.projects:
        step_reporter.report(
            message=f"Enabling required APIs [{', '.join(ROLE_TO_REQUIRED_API.values())}] for project '{project.name}'"
        )

        gcloud(
            f"services enable {services_to_enable} \
               --project={project.id} \
               --quiet"
        )

        for role in ROLES_TO_ADD:
            step_reporter.report(
                message=f"Assigning role [{role}] to service account '{service_account_email}' in project '{project.name}'"
            )

            gcloud(
                f'projects add-iam-policy-binding "{project.id}" \
                --member="serviceAccount:{service_account_email}" \
                --role="{role}" \
                --condition=None \
                --quiet \
                '
            )

    step_reporter.report(message="Creating GCP integration in Datadog...")

    response, status = dd_request(
        "POST",
        "/api/v2/integration/gcp/accounts?source=script",
        {
            "data": {
                "type": "gcp_service_account",
                "attributes": {
                    "client_email": service_account_email,
                    "is_per_project_quota_enabled": True,
                    **asdict(integration_configuration),
                },
            }
        },
    )

    data = json.loads(response)
    if status >= 400:
        errors = data.get("errors", [])
        if len(errors) > 0:
            error_message = ", ".join(map(lambda e: e.get("detail", ""), errors))
            raise RuntimeError(error_message)

        raise RuntimeError(f"failed to create service account: {response}")

    step_reporter.report(
        metadata={"created_service_account_id": data.get("data", {}).get("id")}
    )
