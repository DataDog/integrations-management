# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from typing import Final

# ---------------------------------------------------------------------------
# Image placeholders. Replace with real Container App Job images before release.
# ---------------------------------------------------------------------------
RESOURCES_TASK_IMAGE: Final = "datadoghq.azurecr.io/resources-task:latest"
SCALING_TASK_IMAGE: Final = "datadoghq.azurecr.io/scaling-task:latest"
DIAGNOSTIC_SETTINGS_TASK_IMAGE: Final = "datadoghq.azurecr.io/diagnostic-settings-task:latest"
NEW_DEPLOYER_IMAGE: Final = "datadoghq.azurecr.io/deployer:latest"

# ---------------------------------------------------------------------------
# Resource naming
# ---------------------------------------------------------------------------
RESOURCES_TASK_PREFIX: Final = "resources-task-"
SCALING_TASK_PREFIX: Final = "scaling-task-"
DIAGNOSTIC_SETTINGS_TASK_PREFIX: Final = "diagnostic-settings-task-"
DEPLOYER_TASK_PREFIX: Final = "deployer-task-"

# New Container App Job suffix - keeps new jobs in a distinct namespace from
# the still-living function apps during the migration window.
JOB_NAME_SUFFIX: Final = "-job"


def resources_job_name(control_plane_id: str) -> str:
    return f"{RESOURCES_TASK_PREFIX}{control_plane_id}{JOB_NAME_SUFFIX}"


def scaling_job_name(control_plane_id: str) -> str:
    return f"{SCALING_TASK_PREFIX}{control_plane_id}{JOB_NAME_SUFFIX}"


def diagnostic_settings_job_name(control_plane_id: str) -> str:
    return f"{DIAGNOSTIC_SETTINGS_TASK_PREFIX}{control_plane_id}{JOB_NAME_SUFFIX}"


def resources_task_name(control_plane_id: str) -> str:
    return f"{RESOURCES_TASK_PREFIX}{control_plane_id}"


def scaling_task_name(control_plane_id: str) -> str:
    return f"{SCALING_TASK_PREFIX}{control_plane_id}"


def diagnostic_settings_task_name(control_plane_id: str) -> str:
    return f"{DIAGNOSTIC_SETTINGS_TASK_PREFIX}{control_plane_id}"


def deployer_job_name(control_plane_id: str) -> str:
    return f"{DEPLOYER_TASK_PREFIX}{control_plane_id}"


def control_plane_env_name(control_plane_id: str, region: str) -> str:
    return f"dd-log-forwarder-env-{control_plane_id}-{region}"


# ---------------------------------------------------------------------------
# Job sizing + schedule. Crons match the historical Function App schedule.
# ---------------------------------------------------------------------------
JOB_CPU: Final = "0.5"
JOB_MEMORY: Final = "1Gi"
JOB_REPLICA_TIMEOUT: Final = "1800"
JOB_REPLICA_RETRY_LIMIT: Final = "1"
JOB_PARALLELISM: Final = "1"
JOB_REPLICA_COMPLETION_COUNT: Final = "1"

RESOURCES_TASK_CRON: Final = "*/5 * * * *"
SCALING_TASK_CRON: Final = "*/5 * * * *"
DIAGNOSTIC_SETTINGS_TASK_CRON: Final = "*/5 * * * *"

# ---------------------------------------------------------------------------
# Built-in Azure role IDs (mirrors azure/logging_install/.../constants.py).
# ---------------------------------------------------------------------------
MONITORING_READER_ID: Final = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
MONITORING_CONTRIBUTOR_ID: Final = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
STORAGE_READER_AND_DATA_ACCESS_ID: Final = "c12c1c16-33a1-487b-954d-41c89c60f349"
# "Contributor" - same role the v1 architecture used for the scaling task on
# the forwarder resource group.
SCALING_CONTRIBUTOR_ID: Final = "b24988ac-6180-42a0-ab88-20f7382dd24c"
WEBSITE_CONTRIBUTOR_ID: Final = "de139f84-1756-47ae-9be6-808fbbe84772"
# Built-in "Container Apps Jobs Contributor" role - replaces Website Contributor
# for the deployer in the new architecture.
CONTAINER_APPS_JOBS_CONTRIBUTOR_ID: Final = "b9a307c4-5aa3-4b52-ba60-2b17c136cd7b"

# ---------------------------------------------------------------------------
# Env-var keys to copy from function app appsettings (everything else either
# comes from Azure Functions runtime and is irrelevant to a Container App Job
# or is one of the explicit excludes below).
# ---------------------------------------------------------------------------
FUNCTION_RUNTIME_ENV_KEYS_TO_DROP: Final = frozenset(
    {
        "AzureWebJobsStorage",
        "FUNCTIONS_EXTENSION_VERSION",
        "FUNCTIONS_WORKER_RUNTIME",
        "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING",
        "WEBSITE_CONTENTSHARE",
        "AzureWebJobsFeatureFlags",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "APPINSIGHTS_INSTRUMENTATIONKEY",
    }
)

# Env-var keys to fetch directly off the resources-task to drive Phase 3 role
# assignments.
MONITORED_SUBSCRIPTIONS_KEY: Final = "MONITORED_SUBSCRIPTIONS"

# Storage file share the new jobs mount (delete in Phase 5).
CONTROL_PLANE_CACHE_FILE_SHARE: Final = "control-plane-cache"

# Poll interval/timeout for waiting on a manually-triggered job execution.
JOB_EXECUTION_POLL_INTERVAL_SECONDS: Final = 10
JOB_EXECUTION_TIMEOUT_SECONDS: Final = 1800
