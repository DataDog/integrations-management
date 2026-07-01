# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import uuid
from enum import IntEnum

from az_shared.errors import FatalError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from .az_cmd import AzCmd
from .constants import IMAGE_REGISTRY_URL, NIL_UUID, STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS, RESOURCES_TASK_PREFIX, SCALING_TASK_PREFIX, DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_PREFIX, DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX, DEPLOYER_TASK_PREFIX, DEPLOYER_IMAGE_FOR_FUNCTION_APPS, DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS


class ControlPlaneType(IntEnum):
    FunctionApps = 1
    ContainerAppJobs = 2

class ControlPlane:
    # TODO description

    def __init__(self, id: str, region: str, subscription_id: str, resource_group: str, type: ControlPlaneType = ControlPlaneType.FunctionApps):
        self.id = id
        self.region = region
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.type = type

        # Storage account cache
        self.cache_storage_name = f"lfostorage{self.id}"
        self.cache_storage_url = f"https://{self.cache_storage_name}.blob.core.windows.net"
        self.cache_storage_key = _get_control_plane_cache_key(self.cache_storage_name, self.resource_group)
        self.cache_conn_string = f"DefaultEndpointsProtocol=https;AccountName={self.cache_storage_name};EndpointSuffix=core.windows.net;AccountKey={self.cache_storage_key}"
       
        self.sub_scope = f"/subscriptions/{self.subscription_id}"
        self.rg_scope = f"{self.sub_scope}/resourceGroups/{self.resource_group}"
        
        self.container_app_env_name = f"dd-log-forwarder-env-{self.id}-{self.region}"

        # Deployer
        self.deployer_job_name = f"{DEPLOYER_TASK_PREFIX}{self.id}"
        self.deployer_image_url = _get_deployer_image_url(self.type)
        self.container_app_start_role_name = f"ContainerAppStartRole{self.id}"

        # Control Plane Tasks
        self.resources_task_name = f"{RESOURCES_TASK_PREFIX}{self.id}"
        self.scaling_task_name = f"{SCALING_TASK_PREFIX}{self.id}"
        self.diagnostic_settings_task_name = _get_diagnostic_settings_task_name(self.type, self.id)
        self.task_names = [
            self.resources_task_name,
            self.scaling_task_name,
            self.diagnostic_settings_task_name,
        ]


class Configuration:
    # TODO description

    def __init__(self, control_plane: ControlPlane, monitored_subs: list[str], datadog_api_key: str, datadog_site: str = "datadoghq.com", resource_tag_filters: str = "", pii_scrubber_rules: str = "", datadog_telemetry: bool = False, log_level: str = "INFO"):
        self.control_plane = control_plane
        self.datadog_api_key = datadog_api_key
        self.monitored_subscriptions = monitored_subs
        self.all_subscriptions = {
            control_plane.subscription_id,
            *self.monitored_subscriptions,
        }
        self.datadog_site = datadog_site
        self.resource_tag_filters = resource_tag_filters
        self.pii_scrubber_rules = pii_scrubber_rules
        self.datadog_telemetry = datadog_telemetry
        self.log_level = log_level

    # Alias properties preserving the pre-refactor flat attribute names, delegating to self.control_plane.

    @property
    def control_plane_id(self) -> str:
        return self.control_plane.id

    @property
    def control_plane_region(self) -> str:
        return self.control_plane.region

    @property
    def control_plane_sub_id(self) -> str:
        return self.control_plane.subscription_id

    @property
    def control_plane_rg(self) -> str:
        return self.control_plane.resource_group

    @property
    def control_plane_cache_storage_name(self) -> str:
        return self.control_plane.cache_storage_name

    @property
    def control_plane_cache_storage_url(self) -> str:
        return self.control_plane.cache_storage_url

    @property
    def control_plane_cache_storage_key(self) -> str:
        return self.control_plane.cache_storage_key

    @property
    def control_plane_sub_scope(self) -> str:
        return self.control_plane.sub_scope

    @property
    def control_plane_rg_scope(self) -> str:
        return self.control_plane.rg_scope

    @property
    def control_plane_env_name(self) -> str:
        return self.control_plane.container_app_env_name

    @property
    def deployer_job_name(self) -> str:
        return self.control_plane.deployer_job_name

    @property
    def deployer_image_url(self) -> str:
        return self.control_plane.deployer_image_url

    @property
    def container_app_start_role_name(self) -> str:
        return self.control_plane.container_app_start_role_name

    @property
    def resources_task_name(self) -> str:
        return self.control_plane.resources_task_name

    @property
    def scaling_task_name(self) -> str:
        return self.control_plane.scaling_task_name

    @property
    def diagnostic_settings_task_name(self) -> str:
        return self.control_plane.diagnostic_settings_task_name

    @property
    def control_plane_function_app_names(self) -> list[str]:
        return self.control_plane.task_names

    def get_control_plane_cache_key(self) -> str:
        return self.control_plane.cache_storage_key

    def get_control_plane_cache_conn_string(self) -> str:
        return self.control_plane.cache_conn_string


def _get_control_plane_cache_key(control_plane_cache_storage_name: str, control_plane_rg: str) -> str:
    """Returns the storage account key for the control plane cache storage account."""
    log.debug(f"Retrieving storage account key for {control_plane_cache_storage_name}")

    try:
        output = execute(
            AzCmd("storage", "account keys list")
            .param("--account-name", control_plane_cache_storage_name)
            .param("--resource-group", control_plane_rg)
        )
        keys_json = json.loads(output)

        if not isinstance(keys_json, list) or len(keys_json) == 0:
            raise FatalError(f"Failed to retrieve storage account keys for {control_plane_cache_storage_name}")

        for key_entry in keys_json:
            if key_entry.get("permissions") == STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS and key_entry.get("value"):
                control_plane_cache_storage_key = key_entry["value"]
                break
        else:
            raise FatalError(
                f"No storage account keys with full read/write permissions found for {control_plane_cache_storage_name}"
            )
    except json.JSONDecodeError as e:
        raise FatalError(
            f"Failed to parse storage account keys for {control_plane_cache_storage_name}: {e}"
        ) from e
    except KeyError as e:
        raise FatalError(
            f"Failed to retrieve storage account keys for {control_plane_cache_storage_name}: {e}"
        ) from e

    return control_plane_cache_storage_key


def _get_diagnostic_settings_task_name(control_plane_type: ControlPlaneType, control_plane_id: str) -> str:
    if control_plane_type == ControlPlaneType.FunctionApps:
        return f"{DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_PREFIX}{control_plane_id}"
    if control_plane_type == ControlPlaneType.ContainerAppJobs:
        return f"{DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX}{control_plane_id}"
    

def _get_deployer_image_url(control_plane_type: ControlPlaneType) -> str:
    if control_plane_type == ControlPlaneType.FunctionApps:
        return f"{IMAGE_REGISTRY_URL}/{DEPLOYER_IMAGE_FOR_FUNCTION_APPS}"
    if control_plane_type == ControlPlaneType.ContainerAppJobs:
        return f"{IMAGE_REGISTRY_URL}/{DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS}"


def generate_control_plane_id(control_plane_sub_id: str, control_plane_rg: str, control_plane_region: str) -> str:
    """Returns a 12-character unique ID based on user input parameters.
    This ID is suffixed on Azure resources we create to identify their relationship to the control plane.
    """
    combined = f"{control_plane_sub_id}{control_plane_rg}{control_plane_region}"

    namespace = uuid.UUID(NIL_UUID)
    guid = str(uuid.uuid5(namespace, combined)).lower()
    id = guid[:8] + guid[9:13]
    log.info(f"Generated control plane ID: {id}")
    return id
