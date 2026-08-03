# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared test data constants for azure's caj_migration tests."""

from azure_logging_install.configuration import ControlPlaneType, LfoControlPlane

SUB_1_ID = "11111111-1111-4111-a111-111111111111"
SUB_2_ID = "22222222-2222-4222-a222-222222222222"

CONTROL_PLANE_ID = "abcdef123456"
CONTROL_PLANE_SUBSCRIPTION_ID = "cccccccc-cccc-4ccc-accc-cccccccccccc"
CONTROL_PLANE_SUBSCRIPTION_NAME = "Test Control Plane Subscription"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"

RESOURCES_TASK_NAME = f"resources-task-{CONTROL_PLANE_ID}"
SCALING_TASK_NAME = f"scaling-task-{CONTROL_PLANE_ID}"
DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_NAME = f"diagnostic-settings-task-{CONTROL_PLANE_ID}"
DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_NAME = f"diag-settings-task-{CONTROL_PLANE_ID}"
DEPLOYER_JOB_NAME = f"deployer-task-{CONTROL_PLANE_ID}"
CONTROL_PLANE_ENV_NAME = f"dd-log-forwarder-env-{CONTROL_PLANE_ID}-{CONTROL_PLANE_REGION}"

SUB_ID_TO_NAME = {
    CONTROL_PLANE_SUBSCRIPTION_ID: CONTROL_PLANE_SUBSCRIPTION_NAME,
    SUB_1_ID: "Test Subscription 1",
    SUB_2_ID: "Test Subscription 2",
}


def make_function_app_control_plane() -> LfoControlPlane:
    return LfoControlPlane(
        id=CONTROL_PLANE_ID,
        sub_id=CONTROL_PLANE_SUBSCRIPTION_ID,
        sub_name=CONTROL_PLANE_SUBSCRIPTION_NAME,
        resource_group=CONTROL_PLANE_RESOURCE_GROUP,
        region=CONTROL_PLANE_REGION,
        type=ControlPlaneType.FunctionApps,
    )
