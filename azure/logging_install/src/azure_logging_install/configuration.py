# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from enum import Enum
import json
import uuid
from dataclasses import dataclass

from az_shared.errors import FatalError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from .az_cmd import AzCmd
from .constants import DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS, DEPLOYER_IMAGE_FOR_FUNCTION_APPS, DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX, DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_PREFIX, DIAGNOSTIC_SETTINGS_TASK_IMAGE, IMAGE_REGISTRY_URL, NIL_UUID, RESOURCES_TASK_IMAGE, RESOURCES_TASK_PREFIX, SCALING_TASK_IMAGE, SCALING_TASK_PREFIX, STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS


class ControlPlaneType(str, Enum):
    FunctionApps = "FunctionApps"
    ContainerAppJobs = "ContainerAppJobs"


@dataclass
class LfoControlPlane:
    id: str
    sub_id: str
    sub_name: str
    resource_group: str
    region: str
    type: ControlPlaneType

    def __post_init__(self):
        self.resources_task_name = _get_resources_task_name(self.id)
        self.scaling_task_name = _get_scaling_task_name(self.id)
        self.diagnostic_settings_task_name = _get_diagnostic_settings_task_name(self.type, self.id)



@dataclass
class LfoControlPlane:
    id: str
    sub_id: str
    sub_name: str
    resource_group: str
    region: str
    type: ControlPlaneType

    def __post_init__(self):
        self.resources_task_name = _get_resources_task_name(self.id)
        self.scaling_task_name = _get_scaling_task_name(self.id)
        self.diagnostic_settings_task_name = _get_diagnostic_settings_task_name(self.type, self.id)


@dataclass
class Configuration:
    """User-specified configuration parameters and derivations necessary for deployment"""

    # Required user-specified params
    control_plane_region: str
    control_plane_sub_id: str
    control_plane_rg: str
    monitored_subs: str
    datadog_api_key: str
    control_plane_type: ControlPlaneType

    # Optional user-specified params with defaults
    datadog_site: str = "datadoghq.com"
    resource_tag_filters: str = ""
    pii_scrubber_rules: str = ""
    datadog_telemetry: bool = False
    log_level: str = "INFO"

    def generate_control_plane_id(self) -> str:
        """Returns a 12-character unique ID based on user input parameters.
        This ID is suffixed on Azure resources we create to identify their relationship to the control plane.
        """

        combined = f"{self.control_plane_sub_id}{self.control_plane_rg}{self.control_plane_region}"

        namespace = uuid.UUID(NIL_UUID)
        guid = str(uuid.uuid5(namespace, combined)).lower()
        return guid[:8] + guid[9:13]

    def get_control_plane_cache_key(self) -> str:
        """Returns the storage account key for the control plane cache storage account."""

        if self.control_plane_cache_storage_key:
            return self.control_plane_cache_storage_key

        log.debug(f"Retrieving storage account key for {self.control_plane_cache_storage_name}")

        try:
            output = execute(
                AzCmd("storage", "account keys list")
                .param("--account-name", self.control_plane_cache_storage_name)
                .param("--resource-group", self.control_plane_rg)
            )
            keys_json = json.loads(output)

            if not isinstance(keys_json, list) or len(keys_json) == 0:
                raise FatalError(f"Failed to retrieve storage account keys for {self.control_plane_cache_storage_name}")

            for key_entry in keys_json:
                if key_entry.get("permissions") == STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS and key_entry.get("value"):
                    self.control_plane_cache_storage_key = key_entry["value"]
                    break
            else:
                raise FatalError(
                    f"No storage account keys with full read/write permissions found for {self.control_plane_cache_storage_name}"
                )
        except json.JSONDecodeError as e:
            raise FatalError(
                f"Failed to parse storage account keys for {self.control_plane_cache_storage_name}: {e}"
            ) from e
        except KeyError as e:
            raise FatalError(
                f"Failed to retrieve storage account keys for {self.control_plane_cache_storage_name}: {e}"
            ) from e

        return self.control_plane_cache_storage_key

    def get_control_plane_cache_conn_string(self) -> str:
        return f"DefaultEndpointsProtocol=https;AccountName={self.control_plane_cache_storage_name};EndpointSuffix=core.windows.net;AccountKey={self.get_control_plane_cache_key()}"

    def __post_init__(self):
        """Calculates derived values from user-specified params."""

        self.monitored_subscriptions = [sub.strip() for sub in self.monitored_subs.split(",") if sub.strip()]
        self.all_subscriptions = {
            self.control_plane_sub_id,
            *self.monitored_subscriptions,
        }

        # Control plane
        self.control_plane_id = self.generate_control_plane_id()
        log.info(f"Generated control plane ID: {self.control_plane_id}")
        self.control_plane_cache_storage_name = f"lfostorage{self.control_plane_id}"
        self.control_plane_cache_storage_url = f"https://{self.control_plane_cache_storage_name}.blob.core.windows.net"
        self.control_plane_cache_storage_key = None  # lazy-loaded
        self.control_plane_sub_scope = f"/subscriptions/{self.control_plane_sub_id}"
        self.control_plane_rg_scope = f"{self.control_plane_sub_scope}/resourceGroups/{self.control_plane_rg}"
        self.control_plane_env_name = f"dd-log-forwarder-env-{self.control_plane_id}-{self.control_plane_region}"

        # Deployer
        self.deployer_job_name = f"deployer-task-{self.control_plane_id}"
        self.deployer_image_url = _get_deployer_image(self.control_plane_type)
        self.container_app_start_role_name = f"ContainerAppStartRole{self.control_plane_id}"

        # Control plane tasks
        self.resources_task_name = _get_resources_task_name(self.control_plane_id)
        self.resources_task_image = fully_qualified_image(RESOURCES_TASK_IMAGE)

        self.scaling_task_name = _get_scaling_task_name(self.control_plane_id)
        self.scaling_task_image = fully_qualified_image(SCALING_TASK_IMAGE)

        self.diagnostic_settings_task_name = _get_diagnostic_settings_task_name(self.control_plane_type, self.control_plane_id)
        self.diagnostic_settings_task_image = fully_qualified_image(DIAGNOSTIC_SETTINGS_TASK_IMAGE)
        self.control_plane_task_names = [
            self.resources_task_name,
            self.scaling_task_name,
            self.diagnostic_settings_task_name,
        ]


def _get_diagnostic_settings_task_name(control_plane_type: str, control_plane_id: str) -> str:
    if control_plane_type == ControlPlaneType.FunctionApps:
        return f"{DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_PREFIX}{control_plane_id}"
    if control_plane_type == ControlPlaneType.ContainerAppJobs:
        return f"{DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX}{control_plane_id}"

def _get_resources_task_name(control_plane_id: str) -> str:
    return f"{RESOURCES_TASK_PREFIX}{control_plane_id}"


def _get_scaling_task_name(control_plane_id: str) -> str:
    return f"{SCALING_TASK_PREFIX}{control_plane_id}"

def _get_deployer_image(control_plane_type: str) -> str:
    if control_plane_type == ControlPlaneType.FunctionApps:
        return fully_qualified_image(DEPLOYER_IMAGE_FOR_FUNCTION_APPS)
    if control_plane_type == ControlPlaneType.ContainerAppJobs:
        return fully_qualified_image(DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS)

def fully_qualified_image(repo_and_tag: str) -> str:
    """Return the full qualified image name with the registry URL"""
    return f"{IMAGE_REGISTRY_URL}/{repo_and_tag}"
