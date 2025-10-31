# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import shlex
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep, time
from typing import Optional

from az_shared.az_cmd import AzCmd, execute
from az_shared.errors import (
    ExistenceCheckError,
    FatalError,
    ResourceNotFoundError,
    ResourceProviderRegistrationValidationError,
)
from az_shared.logs import log

from .configuration import Configuration
from .constants import CONTROL_PLANE_CACHE, IMAGE_REGISTRY_URL, LFO_PUBLIC_STORAGE_ACCOUNT_URL, MAX_THREAD_POOL_WORKERS

# =============================================================================
# Subscription, Resource Group, Storage Account
# =============================================================================


def create_resource_group(control_plane_rg: str, control_plane_region: str):
    """Create resource group for control plane"""
    log.info(f"Creating resource group {control_plane_rg} in {control_plane_region}")
    execute(AzCmd("group", "create").param("--name", control_plane_rg).param("--location", control_plane_region))


def create_storage_account(storage_account_name: str, control_plane_rg: str, control_plane_region: str):
    """Create storage account for control plane cache"""
    log.info(f"Creating storage account {storage_account_name}")
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
    log.info(f"Creating blob container {CONTROL_PLANE_CACHE}")
    execute(
        AzCmd("storage", "container create")
        .param("--account-name", storage_account_name)
        .param("--account-key", account_key)
        .param("--name", CONTROL_PLANE_CACHE)
    )


def create_file_share(storage_account_name: str, control_plane_rg: str):
    """Create file share for control plane cache"""
    log.info(f"Creating file share {CONTROL_PLANE_CACHE}")
    execute(
        AzCmd("storage", "share-rm create")
        .param("--storage-account", storage_account_name)
        .param("--name", CONTROL_PLANE_CACHE)
        .param("--resource-group", control_plane_rg)
    )


def wait_for_storage_account_ready(storage_account_name: str, control_plane_rg: str) -> None:
    """Waits for storage account to be in 'Succeeded' provisioning state.
    Storage accounts are created asynchronously, so we need to wait for them to be ready.
    """
    log.info(f"Waiting for storage account {storage_account_name} to be ready...")

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
        log.debug(f"Storage account {storage_account_name} provisioning state: {state}")

        if state == "Succeeded":
            log.info(f"Storage account {storage_account_name} is ready")
            return
        elif state in ["Failed", "Canceled"]:
            raise RuntimeError(f"Storage account {storage_account_name} provisioning failed with state: {state}")

        # Still provisioning, wait and check again
        sleep(5)

    raise TimeoutError(
        f"Timeout waiting for storage account {storage_account_name} to be ready after {max_wait_seconds} seconds"
    )


# =============================================================================
# Function Apps
# =============================================================================


def create_function_app(config: Configuration, name: str):
    """Create a function app for a control plane task and configure function app runtime"""
    try:
        log.info(f"Checking if Function App '{name}' already exists...")
        execute(AzCmd("functionapp", "show").param("--name", name).param("--resource-group", config.control_plane_rg))
        log.info(f"Function App '{name}' already exists - skipping creation and updating configuration")
        function_app_exists = True
    except ResourceNotFoundError:
        log.info(f"Function App '{name}' not found - creating new function app")
        function_app_exists = False
    except Exception as e:
        raise ExistenceCheckError(f"Failed to check if Function App '{name}' exists: {e}") from e

    if not function_app_exists:
        log.info(f"Creating Function App {name}")
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

        log.debug(f"Configuring Linux runtime for Function App {name}")
        execute(
            AzCmd("functionapp", "config set")
            .param("--name", name)
            .param("--resource-group", config.control_plane_rg)
            .param("--linux-fx-version", shlex.quote("Python|3.11"))
        )


def set_function_app_env_vars(config: Configuration, function_app_name: str):
    """Update the environment variables for a function app - some are exclusive to specific tasks"""
    log.info(f"Configuring app settings for function app {function_app_name}")

    common_settings = {
        "AzureWebJobsStorage": config.get_control_plane_cache_conn_string(),
        "FUNCTIONS_EXTENSION_VERSION": "~4",
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING": config.get_control_plane_cache_conn_string(),
        "WEBSITE_CONTENTSHARE": function_app_name,
        "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
        "DD_API_KEY": config.datadog_api_key,
        "DD_SITE": config.datadog_site,
        "DD_TELEMETRY": "true" if config.datadog_telemetry else "false",
        "CONTROL_PLANE_ID": config.control_plane_id,
        "LOG_LEVEL": config.log_level,
    }

    # Task-specific settings
    if function_app_name == config.resources_task_name:
        specific_settings = {
            "MONITORED_SUBSCRIPTIONS": json.dumps(config.monitored_subscriptions),
            "RESOURCE_TAG_FILTERS": config.resource_tag_filters,
        }
    elif function_app_name == config.diagnostic_settings_task_name:
        specific_settings = {
            "RESOURCE_GROUP": config.control_plane_rg,
        }
    elif function_app_name == config.scaling_task_name:
        specific_settings = {
            "RESOURCE_GROUP": config.control_plane_rg,
            "FORWARDER_IMAGE": f"{IMAGE_REGISTRY_URL}/forwarder:latest",
            "CONTROL_PLANE_REGION": config.control_plane_region,
            "PII_SCRUBBER_RULES": config.pii_scrubber_rules,
        }
    else:
        raise FatalError(f"Unknown function app task when configuring app settings: {function_app_name}")

    all_settings = {**common_settings, **specific_settings}

    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as tmpfile:
        json.dump(all_settings, tmpfile)
        tmpfile.flush()
        tmpfile_path = tmpfile.name

    try:
        log.debug(f"Configuring app settings for Function App {function_app_name}")
        execute(
            AzCmd("functionapp", "config appsettings set")
            .param("--name", function_app_name)
            .param("--resource-group", config.control_plane_rg)
            .param("--settings", f"@{tmpfile_path}")
        )
    finally:
        os.unlink(tmpfile_path)


def create_function_apps(config: Configuration):
    """Create function apps for LFO Resources Task, Scaling Task, and Diagnostic Settings Task"""

    log.info("Creating Function Apps...")
    for function_app_name in config.control_plane_function_app_names:
        create_function_app(config, function_app_name)
        set_function_app_env_vars(config, function_app_name)

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
        log.info(f"Checking if Container App environment '{control_plane_env}' already exists...")
        execute(
            AzCmd("containerapp", "env show")
            .param("--name", control_plane_env)
            .param("--resource-group", control_plane_resource_group)
        )
        log.info(f"Container App environment '{control_plane_env}' already exists - reusing existing environment")
        return
    except ResourceNotFoundError:
        log.info(f"Container App environment '{control_plane_env}' not found - creating new environment")

    log.info(f"Creating Container App environment {control_plane_env}")
    execute(
        AzCmd("containerapp", "env create")
        .param("--name", control_plane_env)
        .param("--resource-group", control_plane_resource_group)
        .param("--location", control_plane_location)
    )


def create_container_app_job(config: Configuration):
    """Create the Container App job for the deployer if it does not exist"""

    try:
        log.info(f"Checking if Container App job '{config.deployer_job_name}' already exists...")
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", config.deployer_job_name)
            .param("--resource-group", config.control_plane_rg)
        )
        log.info(f"Container App job '{config.deployer_job_name}' already exists - reusing existing job")
        return
    except ResourceNotFoundError:
        log.info(f"Container App job '{config.deployer_job_name}' not found - creating new job")

    log.info(f"Creating Container App job {config.deployer_job_name}")

    env_vars = [
        "AzureWebJobsStorage=secretref:connection-string",
        f"SUBSCRIPTION_ID={config.control_plane_sub_id}",
        f"RESOURCE_GROUP={config.control_plane_rg}",
        f"CONTROL_PLANE_ID={config.control_plane_id}",
        f"CONTROL_PLANE_REGION={config.control_plane_region}",
        "DD_API_KEY=secretref:dd-api-key",
        f"DD_SITE={config.datadog_site}",
        f"DD_TELEMETRY={'true' if config.datadog_telemetry else 'false'}",
        shlex.quote(f"STORAGE_ACCOUNT_URL={LFO_PUBLIC_STORAGE_ACCOUNT_URL}"),
        f"LOG_LEVEL={config.log_level}",
    ]

    secrets = [
        shlex.quote(f"connection-string={config.get_control_plane_cache_conn_string()}"),
        shlex.quote(f"dd-api-key={config.datadog_api_key}"),
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


# =============================================================================
# Resource Provider Registration
# =============================================================================


def register_missing_resource_providers(sub_to_unregistered_provider_list: dict[str, list[str]]):
    """Register missing resource providers in parallel using a thread pool."""

    if not sub_to_unregistered_provider_list:
        log.info("All resource providers are already registered across all subscriptions")
        return
    else:
        log.info(
            f"Registering missing resource providers in {len(sub_to_unregistered_provider_list)} subscriptions in parallel. This may take a few minutes..."
        )

    def register_provider(sub_id: str, provider: str) -> tuple[str, str, bool, Optional[Exception]]:
        """Register a single resource provider. Returns (sub_id, provider, success, error)."""

        log.debug(f"Registering resource provider {provider} in subscription {sub_id}")
        try:
            execute(
                AzCmd("provider", "register")
                .param("--subscription", sub_id)
                .param("--namespace", provider)
                .flag("--wait")
            )
            log.info(f"Successfully registered {provider} in subscription {sub_id}")
            return (sub_id, provider, True, None)
        except Exception as e:
            log.error(f"Failed to register resource provider {provider} in subscription {sub_id}: {e}")
            return (sub_id, provider, False, e)

    registration_tasks = [
        (sub_id, provider)
        for sub_id, unregistered_providers in sub_to_unregistered_provider_list.items()
        for provider in unregistered_providers
    ]

    failures = []
    with ThreadPoolExecutor(max_workers=MAX_THREAD_POOL_WORKERS) as executor:
        future_to_task = {
            executor.submit(register_provider, sub_id, provider): (sub_id, provider)
            for sub_id, provider in registration_tasks
        }

        for future in as_completed(future_to_task):
            sub_id, provider, success, error = future.result()
            if not success:
                failures.append((sub_id, provider, error))

    if failures:
        error_msg = "Error occurred while registering resource providers:\n"
        for sub_id, provider, error in failures:
            error_msg += f"  - {provider} in subscription {sub_id}: {error}\n"
        raise ResourceProviderRegistrationValidationError(error_msg.strip())

    log.info("Successfully registered missing resource providers")
