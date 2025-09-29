#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache 2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import ssl
import subprocess
import time
import urllib.request
import urllib.response
from urllib.error import HTTPError
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Generator, Tuple, Union

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

REQUIRED_ENVIRONMENT_VARS: set[str] = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "WORKFLOW_ID",
}


def dd_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> Tuple[str, int]:
    """Submit a request to Datadog."""
    return request(
        method,
        f"https://api.{os.environ['DD_SITE']}{path}",
        body,
        {
            "Content-Type": "application/json",
            "DD-API-KEY": os.environ["DD_API_KEY"],
            "DD-APPLICATION-KEY": os.environ["DD_APP_KEY"],
        },
    )


def request(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Tuple[str, int]:
    """Submit a request to the given URL with the specified method and body."""

    ssl_context = ssl.create_default_context()

    req = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=json.dumps(body).encode("utf-8") if body else None,
    )

    try:
        with urllib.request.urlopen(req, context=ssl_context) as response:
            data, status = response.read().decode("utf-8"), response.status
            return data, status
    except HTTPError as e:
        data, status = e.read().decode("utf-8"), e.code
        if status >= 500:
            raise RuntimeError(f"HTTP error {status}: {data}")

        return data, status


ResourceContainer = Union["Project", "Folder"]


@dataclass
class Project:
    """A GCP Project"""

    parent_id: str
    id: str
    name: str

    is_already_monitored: bool
    resource_container_type: str = "project"

    @property
    def iam_test_permission_url_path(self) -> str:
        return "v1/projects/"

    @property
    def required_permissions(self) -> list[str]:
        return [
            "resourcemanager.projects.setIamPolicy",
            "resourcemanager.projects.getIamPolicy",
            "serviceusage.services.enable",
        ]


@dataclass
class Folder:
    """A GCP Folder"""

    parent_id: str
    id: str
    name: str

    child_scopes: list[ResourceContainer] = field(
        default_factory=list[ResourceContainer]
    )
    resource_container_type: str = "folder"

    @property
    def iam_test_permission_url_path(self) -> str:
        return "v2/folders/"

    @property
    def required_permissions(self) -> list[str]:
        return [
            "resourcemanager.folders.setIamPolicy",
            "resourcemanager.folders.getIamPolicy",
        ]


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class StepStatusReporter:
    def __init__(self, status_reporter: "WorkflowReporter", step_id: str):
        self.status_reporter = status_reporter
        self.step_id = step_id

    def report(
        self, metadata: dict[str, Any] = None, message: str | None = None
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        self.status_reporter.report(
            self.step_id,
            Status.IN_PROGRESS,
            message=message,
            metadata=metadata,
        )


class WorkflowReporter:
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    def report(
        self,
        step: str,
        status: Status,
        metadata: dict[str, Any] = None,
        message: str | None = None,
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        response, status = dd_request(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": self.workflow_id,
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": status.value,
                        "step": step,
                        "metadata": metadata,
                        "message": message,
                    },
                }
            },
        )

        if status != 201:
            raise RuntimeError(f"failed to report status: {response}")

    def receive_user_selections(self) -> dict[str, Any] | None:
        """Receive user selections from the Datadog workflow."""
        with self.report_step("selections"):
            while True:
                response, status = dd_request(
                    "GET",
                    f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{self.workflow_id}",
                )

                if status == 404 or not response:
                    time.sleep(1)
                    continue

                json_response = json.loads(response)

                selections: dict[str, Any] = (
                    json_response["data"]["attributes"]
                    .get("metadata", {})
                    .get("selections")
                )

                if not selections:
                    time.sleep(1)
                    continue

                return selections

    @contextmanager
    def report_step(self, step_id: str) -> Generator[StepStatusReporter, str, None]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.IN_PROGRESS)
        try:
            yield StepStatusReporter(self, step_id)
        except Exception as e:
            self.report(
                step_id,
                Status.FAILED,
                message=str(e),
            )
            raise
        else:
            self.report(step_id, Status.FINISHED)


def gcloud(cmd: str, *keys: str) -> Any:
    """Run gcloud CLI command and produce its output. Raise an exception if it fails."""
    try:
        gcloud_output_format = "json" if len(keys) == 0 else f'"json({",".join(keys)})"'
        proc_result = subprocess.run(
            f"gcloud {cmd} --format={gcloud_output_format}",
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"could not execute gcloud command '{cmd}': {str(e.stderr)}")
    else:
        return json.loads(proc_result.stdout)


@dataclass
class ConfigurationScope:
    """Container holding lists of GCP projects and folders for configuration."""

    projects: list[Project]
    folders: list[Folder]


@dataclass
class IntegrationConfiguration:
    """Holds configuration details for the GCP integration with Datadog."""

    metric_namespace_configs: list[dict[str, Any]]
    monitored_resource_configs: list[dict[str, list[str]]]
    account_tags: list[str]
    resource_collection_enabled: bool
    automute: bool


def fetch_iam_permissions_for(
    resource_container: ResourceContainer,
    auth_token: str,
) -> Tuple[ResourceContainer, str, int]:
    """Verify if the given resource container has the required permissions."""
    response, status = request(
        "POST",
        f"https://cloudresourcemanager.googleapis.com/{resource_container.iam_test_permission_url_path}{resource_container.id}:testIamPermissions",
        {"permissions": resource_container.required_permissions},
        {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
    )

    return resource_container, response, status


def fetch_folders(auth_token: str) -> list[dict[str, Any]]:
    """Fetch all active GCP folders."""

    response, status = request(
        "POST",
        "https://cloudresourcemanager.googleapis.com/v2/folders:search",
        {"query": "lifecycleState=ACTIVE"},
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
    )

    json_response = json.loads(response)
    if status != 200:
        raise RuntimeError(f"failed to fetch folders: {response}")

    folders = [folder for folder in json_response.get("folders", [])]

    while json_response.get("nextPageToken"):
        response, status = request(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders:search",
            {
                "query": "lifecycleState=ACTIVE",
                "pageToken": json_response.get("nextPageToken"),
            },
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
        )
        json_response = json.loads(response)
        if status != 200:
            raise RuntimeError(f"failed to fetch folders: {response}")

        folders.extend([folder for folder in json_response.get("folders", [])])

    return folders


def from_dict_recursive(data: dict[str, Any]) -> ResourceContainer:
    """Recursively convert a dict into Folder or Project depending on resource_container_type"""
    if data.get("resource_container_type") not in ("folder", "project"):
        raise ValueError("Invalid resource container type provided")

    if data.get("resource_container_type") == "project":
        return Project(**data)

    children = [from_dict_recursive(child) for child in data.get("child_scopes", [])]
    return Folder(**{**data, "child_scopes": children})


def filter_configuration_scope(
    token: str,
    configuration_scope: ConfigurationScope,
) -> ConfigurationScope:
    """Filter the configuration scope to only include projects and folders with the required permissions."""
    projects: list[Project] = []
    folders: list[Folder] = []

    with ThreadPoolExecutor(max_workers=25) as executor:
        project_futures: list[Future[Tuple[Project, str, int]]] = [
            executor.submit(
                fetch_iam_permissions_for,
                project,
                token,
            )
            for project in configuration_scope.projects
        ]

        folder_futures: list[Future[Tuple[Folder, str, int]]] = [
            executor.submit(
                fetch_iam_permissions_for,
                folder,
                token,
            )
            for folder in configuration_scope.folders
        ]

        all_futures: list[Future[Tuple[ResourceContainer, str, int]]] = (
            project_futures + folder_futures
        )

    for future in as_completed(all_futures):
        resource, response, status = future.result()

        data = json.loads(response)
        permissions = set(data.get("permissions", []))

        if status == 200 and any(
            permission not in permissions
            for permission in resource.required_permissions
        ):
            continue

        if isinstance(resource, Project):
            projects.append(resource)
        else:
            folders.append(resource)

    parent_id_to_scope: dict[str, list] = defaultdict(list[ResourceContainer])
    for resource_container in [*projects, *folders]:
        if len(resource_container.parent_id) != 0:
            parent_id_to_scope[resource_container.parent_id].append(resource_container)

    for folder in folders:
        if folder.id in parent_id_to_scope:
            folder.child_scopes = parent_id_to_scope[folder.id]

    return ConfigurationScope(projects, folders)


def ensure_login() -> None:
    """Ensure that the user is logged into the GCloud Shell. If not, raise an exception."""
    if not gcloud("auth print-access-token"):
        raise RuntimeError("not logged in to GCloud Shell")


def is_valid_workflow_id(workflow_id: str) -> bool:
    """Check if the workflow ID can be used to start a new workflow."""
    response, status = dd_request(
        "GET",
        f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{workflow_id}",
    )

    if status == 404:
        return True

    if status != 200:
        return False

    json_response = json.loads(response)
    statuses: list[dict[str, Any]] = (
        json_response.get("data", {}).get("attributes", {}).get("statuses", [])
    )

    # If any step has failed, we do not allow re-running the workflow (except for the login step, which can be retried).
    if any(
        step.get("status", "") == "failed"
        for step in statuses
        if step.get("step", "") != "login"
    ):
        return False

    # If the workflow has already finished, we do not allow re-running it.
    if any(
        step.get("step", "") == "create_integration_with_permissions"
        and step.get("status", "") == "finished"
        for step in statuses
    ):
        return False

    return True


def is_scopes_step_already_completed(
    workflow_id: str,
) -> bool:
    """Check if the scopes step has already been completed in the GCP integration workflow."""

    response, status = dd_request(
        "GET",
        f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{workflow_id}",
    )

    if status != 200 or not response:
        return False

    json_response = json.loads(response)

    statuses = json_response["data"]["attributes"].get("statuses", [])
    if any(
        step.get("step", "") == "scopes" and step.get("status", "") == "finished"
        for step in statuses
    ):
        return True

    return False


def collect_configuration_scopes(step_reporter: StepStatusReporter) -> None:
    """Collect the configuration scopes (projects and folders) for the GCP integration."""
    response, status = dd_request("GET", "/api/v2/integration/gcp/accounts")

    if status not in (200, 404) or not response:
        raise RuntimeError("failed to get service accounts")

    monitored_projects: set[str] = set()
    if status == 200:
        json_response = json.loads(response)

        monitored_projects.update(
            [
                project
                for account in json_response["data"]
                for project in account["meta"]["accessible_projects"]
            ]
        )

    list_project_output = gcloud(
        'projects list \
        --filter="lifecycleState=ACTIVE AND NOT projectId:sys*"',
        *["name", "projectId", "parent.id"],
    )

    projects = [
        Project(
            name=p["name"],
            parent_id=p.get("parent", {}).get("id", ""),
            id=p["projectId"],
            is_already_monitored=p["projectId"] in monitored_projects,
        )
        for p in list_project_output
    ]

    token = gcloud("auth print-access-token")["token"]
    list_folder_output = fetch_folders(token)

    folders = []
    for f in list_folder_output:
        parent = f["parent"]
        folder = Folder(name=f["displayName"], id=f["name"].split("/")[1], parent_id="")

        if "folders" in parent:
            folder.parent_id = parent.split("/")[1]

        folders.append(folder)

    filtered_configuration = filter_configuration_scope(
        token,
        ConfigurationScope(
            projects=projects,
            folders=folders,
        ),
    )

    step_reporter.report(
        metadata={
            "folders": list(map(asdict, filtered_configuration.folders)),
            "projects": list(map(asdict, filtered_configuration.projects)),
        },
    )


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


def find_or_create_service_account(
    step_reporter: StepStatusReporter, name: str, project_id: str
) -> str:
    """Create a service account with the given name in the specified project."""
    step_reporter.report(
        message=f"Looking for service account '{name}' in project '{project_id}'..."
    )

    service_account_search = gcloud(
        f"iam service-accounts list \
            --project={project_id}  \
            --filter=\"email~'{name}'\"",
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
        f'iam service-accounts create {name}  \
           --display-name="Datadog Service Account" \
           --project={project_id}',
        "email",
    )

    return resp["email"]


if __name__ == "__main__":
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

    workflow_reporter = WorkflowReporter(workflow_id)

    try:
        with workflow_reporter.report_step("login"):
            ensure_login()
    except Exception:
        print("You must be logged in to GCloud Shell to run this script.")
        exit(1)
    else:
        print(
            "Connected! Leave this window open and go back to the Datadog UI to continue."
        )

    with workflow_reporter.report_step("scopes") as step_reporter:
        if not is_scopes_step_already_completed(workflow_id):
            collect_configuration_scopes(step_reporter)

    user_selections = workflow_reporter.receive_user_selections()

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

    print("Script succeeded. You may close this window.")
