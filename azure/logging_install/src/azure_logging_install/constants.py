# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from typing import Final


IMAGE_REGISTRY_URL = "datadoghq.azurecr.io"
LFO_PUBLIC_STORAGE_ACCOUNT_URL = "https://ddazurelfo.blob.core.windows.net"

CONTROL_PLANE_CACHE = "control-plane-cache"
INITIAL_DEPLOY_IDENTITY_NAME = "runInitialDeployIdentity"
STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS = "FULL"
REQUIRED_RESOURCE_PROVIDERS = [
    "Microsoft.CloudShell",  # Cloud Shell
    "Microsoft.Web",  # Function Apps
    "Microsoft.App",  # Container Apps + Envs
    "Microsoft.Storage",  # Storage Accounts
    "Microsoft.Authorization",  # Role Assignments
]
RESOURCE_PROVIDER_REGISTERED_STATUS = "Registered"
MAX_THREAD_POOL_WORKERS = 100

# Seconds between az group show polls while the resource group is Deleting.
RG_DELETING_POLL_INTERVAL = 20

NIL_UUID = "00000000-0000-0000-0000-000000000000"
MONITORING_READER_ID = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
MONITORING_CONTRIBUTOR_ID = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
STORAGE_READER_AND_DATA_ACCESS_ID = "c12c1c16-33a1-487b-954d-41c89c60f349"
SCALING_CONTRIBUTOR_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"
WEBSITE_CONTRIBUTOR_ID = "de139f84-1756-47ae-9be6-808fbbe84772"
CONTAINER_APPS_JOBS_CONTRIBUTOR_ID = "4e3d2b60-56ae-4dc6-a233-09c8e5a82e68"

# Cron schedules for Container App Job control plane tasks
RESOURCES_TASK_CRON: Final = "*/5 * * * *"
SCALING_TASK_CRON: Final = "3/5 * * * *"
DIAGNOSTIC_SETTINGS_TASK_CRON: Final = "*/5 * * * *"
DEPLOYER_TASK_CRON: Final = "*/30 * * * *"

# Timeouts for Container App Job tasks, in seconds
RESOURCES_TASK_TIMEOUT: Final = "300"
SCALING_TASK_TIMEOUT: Final = "500"
DIAGNOSTIC_SETTINGS_TASK_TIMEOUT: Final = "300"

RESOURCES_TASK_PREFIX: Final = "resources-task-"
SCALING_TASK_PREFIX: Final = "scaling-task-"
DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_PREFIX: Final = "diagnostic-settings-task-"
DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_PREFIX: Final = "diag-settings-task-"

DEPLOYER_IMAGE_FOR_FUNCTION_APPS :Final = "deployer:latest"
DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS: Final = "deployer-caj:latest"

RESOURCES_TASK_IMAGE = "resources-task:latest"
SCALING_TASK_IMAGE = "scaling-task:latest"
DIAGNOSTIC_SETTINGS_TASK_IMAGE = "diagnostic-settings-task:latest"

MONITORED_SUBSCRIPTIONS_KEY: Final = "MONITORED_SUBSCRIPTIONS"
RESOURCE_TAG_FILTERS_KEY: Final = "RESOURCE_TAG_FILTERS"
PII_SCRUBBER_RULES_KEY: Final = "PII_SCRUBBER_RULES"

