import json
import os
import shlex
import tempfile
from logging import getLogger
from time import time, sleep

from .az_cmd import AzCmd, execute
from .configuration import Configuration
from .constants import (
    CONTROL_PLANE_CACHE,
    IMAGE_REGISTRY_URL,
    LFO_PUBLIC_STORAGE_ACCOUNT_URL,
)
from .errors import (
    ExistenceCheckError,
    FatalError,
    ResourceNotFoundError,
)

log = getLogger("installer")

# =============================================================================
# Subscription, Resource Group, Storage Account
# =============================================================================


def create_resource_group(control_plane_rg: str, control_plane_region: str):
    """Create resource group for control plane"""
    log.info("Creating resource group {} in {}".format(control_plane_rg, control_plane_region))
    execute(
        AzCmd("group", "create")
        .param("--name", control_plane_rg)
        .param("--location", control_plane_region)
    )


def create_storage_account(
    storage_account_name: str, control_plane_rg: str, control_plane_region: str
):
    """Create storage account for control plane cache"""
    log.info("Creating storage account {}".format(storage_account_name))
    execute(
        AzCmd("storage", "account create")
        .param("--name", storage_account_name)
        .param("--resource-group", control_plane_rg)
        .param("--location", control_plane_region)
        .param("--sku", "Standard_LRS")
        .param("--kind", "StorageV2")
        .param("--access-tier", "Hot")
        .param("--min-tls-version", "TLS1_2")
        .flag("--https-only")
    )


def create_blob_container(storage_account_name: str, account_key: str):
    """Create blob container for control plane cache"""
    log.info("Creating blob container {}".format(CONTROL_PLANE_CACHE))
    execute(
        AzCmd("storage", "container create")
        .param("--account-name", storage_account_name)
        .param("--account-key", account_key)
        .param("--name", CONTROL_PLANE_CACHE)
    )


def create_file_share(storage_account_name: str, control_plane_rg: str):
    """Create file share for control plane cache"""
    log.info("Creating file share {}".format(CONTROL_PLANE_CACHE))
    execute(
        AzCmd("storage", "share-rm create")
        .param("--storage-account", storage_account_name)
        .param("--name", CONTROL_PLANE_CACHE)
        .param("--resource-group", control_plane_rg)
    )


def wait_for_storage_account_ready(
    storage_account_name: str, control_plane_rg: str
) -> None:
    """Waits for storage account to be in 'Succeeded' provisioning state.
    Storage accounts are created asynchronously, so we need to wait for them to be ready.
    """
    log.info("Waiting for storage account {} to be ready...".format(storage_account_name))

    start_time = time()
    max_wait_seconds = 60
    while time() - start_time < max_wait_seconds:
        output = execute(
            AzCmd("storage", "account show")
            .param("--name", storage_account_name)
            .param("--resource-group", control_plane_rg)
            .param("--query", "provisioningState")
            .param("--output", "tsv")
        )

        state = output.strip()
        log.debug("Storage account {} provisioning state: {}".format(storage_account_name, state))

        if state == "Succeeded":
            log.info("Storage account {} is ready".format(storage_account_name))
            return
        elif state in ["Failed", "Canceled"]:
            raise RuntimeError(
                "Storage account {} provisioning failed with state: {}".format(storage_account_name, state)
            )

        # Still provisioning, wait and check again
        sleep(5)

    raise TimeoutError(
        "Timeout waiting for storage account {} to be ready after {} seconds".format(storage_account_name, max_wait_seconds)
    )


# =============================================================================
# App Service Plan, Function Apps
# =============================================================================


def create_app_service_plan(
    app_service_plan: str, control_plane_rg: str, control_plane_region: str
):
    """Create app service plan that the function apps slot into"""
    try:
        log.info("Checking if App Service Plan '{}' already exists...".format(app_service_plan))
        execute(
            AzCmd("appservice", "plan show")
            .param("--name", app_service_plan)
            .param("--resource-group", control_plane_rg)
        )
        log.info(
            "App Service Plan '{}' already exists - reusing existing plan".format(app_service_plan)
        )
        return
    except ResourceNotFoundError:
        log.info("App Service Plan '{}' not found - creating new plan".format(app_service_plan))
    except Exception as e:
        raise ExistenceCheckError(
            "Failed to check if App Service Plan '{}' exists: {}".format(app_service_plan, e)
        ) from e

    log.info("Creating App Service Plan {}".format(app_service_plan))

    # Use `az resource create` instead of `az appservice plan create` because of Azure CLI issue with the SKU we utilize (Y1)
    # https://github.com/Azure/azure-cli/issues/19864

    properties_json = json.dumps(
        {
            "name": app_service_plan,
            "location": control_plane_region,
            "kind": "linux",
            "sku": {"name": "Y1", "tier": "Dynamic"},
            "properties": {"reserved": True},
        }
    )

    execute(
        AzCmd("resource", "create")
        .param("--resource-group", control_plane_rg)
        .param("--name", app_service_plan)
        .param("--resource-type", "Microsoft.Web/serverfarms")
        .flag("--is-full-object")
        .param("--properties", shlex.quote(properties_json))
        .param("--api-version", "2022-09-01")
    )


def create_function_app(config: Configuration, name: str):
    """Create function app and configure settings depending on task type"""
    try:
        log.info("Checking if Function App '{}' already exists...".format(name))
        execute(
            AzCmd("functionapp", "show")
            .param("--name", name)
            .param("--resource-group", config.control_plane_rg)
        )
        log.info(
            "Function App '{}' already exists - skipping creation and updating configuration".format(name)
        )
        function_app_exists = True
    except ResourceNotFoundError:
        log.info("Function App '{}' not found - creating new function app".format(name))
        function_app_exists = False
    except Exception as e:
        raise ExistenceCheckError(
            "Failed to check if Function App '{}' exists: {}".format(name, e)
        ) from e

    if not function_app_exists:
        log.info("Creating Function App {}".format(name))
        execute(
            AzCmd("functionapp", "create")
            .param("--resource-group", config.control_plane_rg)
            .param("--consumption-plan-location", config.control_plane_region)
            .param("--runtime", "python")
            .param("--functions-version", "4")
            .param("--os-type", "Linux")
            .param("--name", name)
            .param("--storage-account", config.control_plane_cache_storage_name)
            .flag("--assign-identity")
        )

    common_settings = {
        "AzureWebJobsStorage": config.get_control_plane_cache_conn_string(),
        "FUNCTIONS_EXTENSION_VERSION": "~4",
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING": config.get_control_plane_cache_conn_string(),
        "WEBSITE_CONTENTSHARE": name,
        "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
        "DD_API_KEY": config.datadog_api_key,
        "DD_SITE": config.datadog_site,
        "DD_TELEMETRY": "true" if config.datadog_telemetry else "false",
        "CONTROL_PLANE_ID": config.control_plane_id,
        "LOG_LEVEL": config.log_level,
    }

    # Task-specific settings
    if name == config.resources_task_name:
        specific_settings = {
            "MONITORED_SUBSCRIPTIONS": ",".join(config.monitored_subscriptions),
            "RESOURCE_TAG_FILTERS": config.resource_tag_filters,
        }
    elif name == config.diagnostic_settings_task_name:
        specific_settings = {
            "RESOURCE_GROUP": config.control_plane_rg,
        }
    elif name == config.scaling_task_name:
        specific_settings = {
            "RESOURCE_GROUP": config.control_plane_rg,
            "FORWARDER_IMAGE": "{}/forwarder:latest".format(IMAGE_REGISTRY_URL),
            "CONTROL_PLANE_REGION": config.control_plane_region,
            "PII_SCRUBBER_RULES": config.pii_scrubber_rules,
        }
    else:
        raise FatalError(
            "Unknown function app task when configuring app settings: {}".format(name)
        )

    all_settings = {**common_settings, **specific_settings}

    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as tmpfile:
        json.dump(all_settings, tmpfile)
        tmpfile.flush()
        tmpfile_path = tmpfile.name

    try:
        log.debug("Configuring app settings for Function App {}".format(name))
        execute(
            AzCmd("functionapp", "config appsettings set")
            .param("--name", name)
            .param("--resource-group", config.control_plane_rg)
            .param("--settings", "@{}".format(tmpfile_path))
        )
    finally:
        os.unlink(tmpfile_path)

    log.debug("Configuring Linux runtime for Function App {}".format(name))
    execute(
        AzCmd("functionapp", "config set")
        .param("--name", name)
        .param("--resource-group", config.control_plane_rg)
        .param("--linux-fx-version", shlex.quote("Python|3.11"))
    )


def create_function_apps(config: Configuration):
    """Create Resources Task, Scaling Task, and Diagnostic Settings Task function apps"""
    log.info("Creating App Service Plan...")
    create_app_service_plan(
        config.app_service_plan_name,
        config.control_plane_rg,
        config.control_plane_region,
    )

    log.info("Creating Function Apps...")
    for function_app_name in config.control_plane_function_app_names:
        log.info("Creating Function App: {}".format(function_app_name))
        create_function_app(config, function_app_name)

    log.info("Function Apps created and configured")


# =============================================================================
# Deployer's Container App Environment, Job, and Identity
# =============================================================================


def create_container_app_environment(
    control_plane_env: str,
    control_plane_resource_group: str,
    control_plane_location: str,
):
    """Create the Container App environment if it does not exist"""

    try:
        log.info(
            "Checking if Container App environment '{}' already exists...".format(control_plane_env)
        )
        execute(
            AzCmd("containerapp", "env show")
            .param("--name", control_plane_env)
            .param("--resource-group", control_plane_resource_group)
        )
        log.info(
            "Container App environment '{}' already exists - reusing existing environment".format(control_plane_env)
        )
        return
    except ResourceNotFoundError:
        log.info(
            "Container App environment '{}' not found - creating new environment".format(control_plane_env)
        )

    log.info("Creating Container App environment {}".format(control_plane_env))
    execute(
        AzCmd("containerapp", "env create")
        .param("--name", control_plane_env)
        .param("--resource-group", control_plane_resource_group)
        .param("--location", control_plane_location)
    )


def create_container_app_job(config: Configuration):
    """Create the Container App job for the deployer if it does not exist"""

    try:
        log.info(
            "Checking if Container App job '{}' already exists...".format(config.deployer_job_name)
        )
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", config.deployer_job_name)
            .param("--resource-group", config.control_plane_rg)
        )
        log.info(
            "Container App job '{}' already exists - reusing existing job".format(config.deployer_job_name)
        )
        return
    except ResourceNotFoundError:
        log.info(
            "Container App job '{}' not found - creating new job".format(config.deployer_job_name)
        )

    log.info("Creating Container App job {}".format(config.deployer_job_name))

    env_vars = [
        "AzureWebJobsStorage=secretref:connection-string",
        "SUBSCRIPTION_ID={}".format(config.control_plane_sub_id),
        "RESOURCE_GROUP={}".format(config.control_plane_rg),
        "CONTROL_PLANE_ID={}".format(config.control_plane_id),
        "CONTROL_PLANE_REGION={}".format(config.control_plane_region),
        "DD_API_KEY=secretref:dd-api-key",
        "DD_SITE={}".format(config.datadog_site),
        "DD_TELEMETRY={}".format('true' if config.datadog_telemetry else 'false'),
        shlex.quote("STORAGE_ACCOUNT_URL={}".format(LFO_PUBLIC_STORAGE_ACCOUNT_URL)),
        "LOG_LEVEL={}".format(config.log_level),
    ]

    secrets = [
        shlex.quote(
            "connection-string={}".format(config.get_control_plane_cache_conn_string())
        ),
        shlex.quote("dd-api-key={}".format(config.datadog_api_key)),
    ]

    execute(
        AzCmd("containerapp", "job create")
        .param("--name", config.deployer_job_name)
        .param("--resource-group", config.control_plane_rg)
        .param("--environment", config.control_plane_env_name)
        .param("--replica-timeout", "1800")
        .param("--replica-retry-limit", "1")
        .param("--trigger-type", "Schedule")
        .param("--cron-expression", shlex.quote("*/30 * * * *"))
        .param("--image", config.deployer_image_url)
        .param("--cpu", "0.5")
        .param("--memory", "1Gi")
        .param("--parallelism", "1")
        .param("--replica-completion-count", "1")
        .flag("--mi-system-assigned")
        .param_list("--env-vars", env_vars)
        .param_list("--secrets", secrets)
    )
