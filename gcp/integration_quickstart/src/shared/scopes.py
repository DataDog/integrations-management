# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict
from typing import Any

from .gcloud import gcloud
from .models import (
    ConfigurationScope,
    Folder,
    Project,
    ResourceContainer,
)
from .reporter import StepStatusReporter
from .requests import dd_request, request


def fetch_iam_permissions_for(
    resource_container: ResourceContainer,
    auth_token: str,
) -> tuple[ResourceContainer, str, int]:
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


def filter_configuration_scope(
    token: str,
    configuration_scope: ConfigurationScope,
) -> ConfigurationScope:
    """Filter the configuration scope to only include projects and folders with the required permissions."""
    projects: list[Project] = []
    folders: list[Folder] = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        project_futures: list[Future[tuple[Project, str, int]]] = [
            executor.submit(
                fetch_iam_permissions_for,
                project,
                token,
            )
            for project in configuration_scope.projects
        ]

        folder_futures: list[Future[tuple[Folder, str, int]]] = [
            executor.submit(
                fetch_iam_permissions_for,
                folder,
                token,
            )
            for folder in configuration_scope.folders
        ]

        all_futures: list[Future[tuple[ResourceContainer, str, int]]] = (
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
