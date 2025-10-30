# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass, field
from typing import Any, Union

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


@dataclass
class ConfigurationScope:
    """Container holding lists of GCP projects and folders for configuration."""

    projects: list[Project]
    folders: list[Folder]


def from_dict_recursive(data: dict[str, Any]) -> ResourceContainer:
    """Recursively convert a dict into Folder or Project depending on resource_container_type"""
    if data.get("resource_container_type") not in ("folder", "project"):
        raise ValueError("Invalid resource container type provided")

    if data.get("resource_container_type") == "project":
        return Project(**data)

    children = [from_dict_recursive(child) for child in data.get("child_scopes", [])]
    return Folder(**{**data, "child_scopes": children})
