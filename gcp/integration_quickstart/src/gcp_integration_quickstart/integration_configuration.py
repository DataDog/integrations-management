# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from dataclasses import asdict
from typing import Optional
from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.models import ConfigurationScope
from gcp_shared.reporter import StepStatusReporter
from gcp_shared.requests import dd_request

from .models import IntegrationConfiguration, ProductRequirements

REQUIRED_APIS: list[str] = [
    "cloudasset.googleapis.com",
    "compute.googleapis.com",
    "monitoring.googleapis.com",
    "cloudresourcemanager.googleapis.com",
]

REQUIRED_ROLES: list[str] = [
    "roles/cloudasset.viewer",
    "roles/browser",
    "roles/compute.viewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
]


def assign_delegate_permissions(
    step_reporter: StepStatusReporter, service_account_email: str, project_id: str
) -> None:
    """Assign the roles/iam.serviceAccountTokenCreator role to the Datadog Principal on the specified service account."""

    step_reporter.report(
        message=f"Fetching Datadog STS delegate for service account '{service_account_email}'..."
    )

    response, status = dd_request("GET", "/api/v2/integration/gcp/sts_delegate")
    if status != 200 or not response:
        raise RuntimeError("failed to get sts delegate")

    json_response = json.loads(response)
    datadog_principal = json_response["data"]["id"]

    step_reporter.report(
        message=f"Assigning role [roles/iam.serviceAccountTokenCreator] to principal '{datadog_principal}' on service account '{service_account_email}'"
    )

    gcloud(
        GcloudCmd("iam service-accounts", "add-iam-policy-binding")
        .arg(service_account_email)
        .param("--member", f"serviceAccount:{datadog_principal}")
        .param("--role", "roles/iam.serviceAccountTokenCreator")
        .param("--condition", "None")
        .param("--project", project_id)
        .flag("--quiet")
    )


def create_integration_with_permissions(
    step_reporter: StepStatusReporter,
    service_account_email: str,
    integration_configuration: IntegrationConfiguration,
    configuration_scope: ConfigurationScope,
    product_requirements: Optional[ProductRequirements] = None,
):
    """Create the GCP integration in Datadog with the specified permissions."""

    required_services = REQUIRED_APIS.copy()
    if product_requirements:
        required_services.extend(
            [
                api
                for api in product_requirements.required_apis
                if api not in REQUIRED_APIS
            ]
        )

    required_roles = REQUIRED_ROLES.copy()
    if product_requirements:
        required_roles.extend(
            [
                role
                for role in product_requirements.required_roles
                if role not in REQUIRED_ROLES
            ]
        )

    for folder in configuration_scope.folders:
        for child_project in filter(
            lambda c: c.resource_container_type == "project", folder.child_scopes
        ):
            step_reporter.report(
                message=f"Enabling required APIs [{', '.join(required_services)}] for project '{child_project.name}'"
            )

            enable_api_cmd = GcloudCmd("services", "enable")
            for service in required_services:
                enable_api_cmd.arg(service)
            enable_api_cmd.param("--project", child_project.id).flag("--quiet")
            gcloud(enable_api_cmd)

        for role in required_roles:
            step_reporter.report(
                message=f"Assigning role [{role}] to service account '{service_account_email}' in folder '{folder.name}'"
            )

            gcloud(
                GcloudCmd("resource-manager folders", "add-iam-policy-binding")
                .arg(folder.id)
                .param("--member", f"serviceAccount:{service_account_email}")
                .param("--role", role)
                .param("--condition", "None")
                .flag("--quiet")
            )

    for project in configuration_scope.projects:
        step_reporter.report(
            message=f"Enabling required APIs [{', '.join(required_services)}] for project '{project.name}'"
        )

        enable_api_cmd = GcloudCmd("services", "enable")
        for service in required_services:
            enable_api_cmd.arg(service)
        enable_api_cmd.param("--project", project.id).flag("--quiet")
        gcloud(enable_api_cmd)

        for role in required_roles:
            step_reporter.report(
                message=f"Assigning role [{role}] to service account '{service_account_email}' in project '{project.name}'"
            )

            gcloud(
                GcloudCmd("projects", "add-iam-policy-binding")
                .arg(project.id)
                .param("--member", f"serviceAccount:{service_account_email}")
                .param("--role", role)
                .param("--condition", "None")
                .flag("--quiet")
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
