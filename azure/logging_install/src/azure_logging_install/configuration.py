import json
import uuid
from dataclasses import dataclass
from logging import getLogger

from .az_cmd import AzCmd, execute
from .constants import (
    IMAGE_REGISTRY_URL,
    NIL_UUID,
    STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS,
)
from .errors import FatalError

log = getLogger("installer")


@dataclass
class Configuration:
    """User-specified configuration parameters and derivations necessary for deployment"""

    # Required user-specified params
    management_group_id: str
    control_plane_region: str
    control_plane_sub_id: str
    control_plane_rg: str
    monitored_subs: str
    datadog_api_key: str

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

        combined = "{}{}{}{}".format(self.management_group_id, self.control_plane_sub_id, self.control_plane_rg, self.control_plane_region)

        namespace = uuid.UUID(NIL_UUID)
        guid = str(uuid.uuid5(namespace, combined)).lower()
        return guid[:8] + guid[9:13]

    def get_control_plane_cache_key(self) -> str:
        """Returns the storage account key for the control plane cache storage account."""

        if self.control_plane_cache_storage_key:
            return self.control_plane_cache_storage_key

        log.debug(
            "Retrieving storage account key for {}".format(self.control_plane_cache_storage_name)
        )

        try:
            output = execute(
                AzCmd("storage", "account keys list")
                .param("--account-name", self.control_plane_cache_storage_name)
                .param("--resource-group", self.control_plane_rg)
            )
            keys_json = json.loads(output)

            if not isinstance(keys_json, list) or len(keys_json) == 0:
                raise FatalError(
                    "Failed to retrieve storage account keys for {}".format(self.control_plane_cache_storage_name)
                )

            for key_entry in keys_json:
                if key_entry.get(
                    "permissions"
                ) == STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS and key_entry.get("value"):
                    self.control_plane_cache_storage_key = key_entry["value"]
                    break
            else:
                raise FatalError(
                    "No storage account keys with full read/write permissions found for {}".format(self.control_plane_cache_storage_name)
                )
        except json.JSONDecodeError as e:
            raise FatalError(
                "Failed to parse storage account keys for {}: {}".format(self.control_plane_cache_storage_name, e)
            ) from e
        except KeyError as e:
            raise FatalError(
                "Failed to retrieve storage account keys for {}: {}".format(self.control_plane_cache_storage_name, e)
            ) from e

        return self.control_plane_cache_storage_key

    def get_control_plane_cache_conn_string(self) -> str:
        return "DefaultEndpointsProtocol=https;AccountName={};EndpointSuffix=core.windows.net;AccountKey={}".format(self.control_plane_cache_storage_name, self.get_control_plane_cache_key())

    def __post_init__(self):
        """Calculates derived values from user-specified params."""

        self.monitored_subscriptions = [
            sub.strip() for sub in self.monitored_subs.split(",") if sub.strip()
        ]
        self.all_subscriptions = {
            self.control_plane_sub_id,
            *self.monitored_subscriptions,
        }

        # Control plane
        self.control_plane_id = self.generate_control_plane_id()
        log.info("Generated control plane ID: {}".format(self.control_plane_id))
        self.control_plane_cache_storage_name = "lfostorage{}".format(self.control_plane_id)
        self.control_plane_cache_storage_url = (
            "https://{}.blob.core.windows.net".format(self.control_plane_cache_storage_name)
        )
        self.control_plane_cache_storage_key = None  # lazy-loaded
        self.control_plane_sub_scope = "/subscriptions/{}".format(self.control_plane_sub_id)
        self.control_plane_rg_scope = (
            "{}/resourceGroups/{}".format(self.control_plane_sub_scope, self.control_plane_rg)
        )
        self.control_plane_env_name = (
            "dd-log-forwarder-env-{}-{}".format(self.control_plane_id, self.control_plane_region)
        )

        # Deployer
        self.deployer_job_name = "deployer-task-{}".format(self.control_plane_id)
        self.deployer_image_url = "{}/deployer:latest".format(IMAGE_REGISTRY_URL)
        self.container_app_start_role_name = (
            "ContainerAppStartRole{}".format(self.control_plane_id)
        )

        # Function apps (control plane tasks)
        self.app_service_plan_name = "control-plane-asp-{}".format(self.control_plane_id)
        self.resources_task_name = "resources-task-{}".format(self.control_plane_id)
        self.scaling_task_name = "scaling-task-{}".format(self.control_plane_id)
        self.diagnostic_settings_task_name = (
            "diagnostic-settings-task-{}".format(self.control_plane_id)
        )
        self.control_plane_function_app_names = [
            self.resources_task_name,
            self.scaling_task_name,
            self.diagnostic_settings_task_name,
        ]
