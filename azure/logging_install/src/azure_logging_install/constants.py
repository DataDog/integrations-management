# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

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
RESOURCE_PROVIDER_REGISTRATION_POLLING_TIMEOUT = 600  # 10 minutes

NIL_UUID = "00000000-0000-0000-0000-000000000000"
MONITORING_READER_ID = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
MONITORING_CONTRIBUTOR_ID = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
STORAGE_READER_AND_DATA_ACCESS_ID = "c12c1c16-33a1-487b-954d-41c89c60f349"
SCALING_CONTRIBUTOR_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"
WEBSITE_CONTRIBUTOR_ID = "de139f84-1756-47ae-9be6-808fbbe84772"
