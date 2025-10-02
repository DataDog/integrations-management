# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared test data constants for azure's logging_install tests."""

from azure_logging_install.configuration import Configuration

# Azure env test subscriptions
SUB_1_ID = "sub-1-id"
SUB_2_ID = "sub-2-id"
SUB_3_ID = "sub-3-id"
SUB_4_ID = "sub-4-id"

# Control plane user settings
CONTROL_PLANE_SUBSCRIPTION_ID = "cp-sub-id"
CONTROL_PLANE_SUBSCRIPTION_NAME = "Test Control Plane Subscription"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = f"{SUB_1_ID},{SUB_2_ID}"
RESOURCE_TAG_FILTERS = "env:prod,team:infra"
PII_SCRUBBER_RULES = "rule1:\n  pattern: 'sensitive data'\n  replacement: 'test'"

# Control plane internal settings
CONTROL_PLANE_ID = "abcdef123456"
RESOURCE_TASK_NAME = f"resources-task-{CONTROL_PLANE_ID}"
SCALING_TASK_NAME = f"scaling-task-{CONTROL_PLANE_ID}"
DIAGNOSTIC_SETTINGS_TASK_NAME = f"diagnostic-settings-task-{CONTROL_PLANE_ID}"
DEPLOYER_JOB_NAME = f"deployer-task-{CONTROL_PLANE_ID}"

SUB_ID_TO_NAME = {
    CONTROL_PLANE_SUBSCRIPTION_ID: CONTROL_PLANE_SUBSCRIPTION_NAME,
    SUB_1_ID: "Test Subscription 1",
    SUB_2_ID: "Test Subscription 2",
    SUB_3_ID: "Test Subscription 3",
    SUB_4_ID: "Test Subscription 4",
}

# DD settings
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"


TEST_CONFIG = Configuration(
    control_plane_region=CONTROL_PLANE_REGION,
    control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION_ID,
    control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
    monitored_subs=MONITORED_SUBSCRIPTIONS,
    datadog_api_key=DATADOG_API_KEY,
    datadog_site=DATADOG_SITE,
    resource_tag_filters=RESOURCE_TAG_FILTERS,
    pii_scrubber_rules=PII_SCRUBBER_RULES,
    datadog_telemetry=True,
    log_level="INFO",
)


def get_test_config():
    test_config = TEST_CONFIG
    test_config.control_plane_function_app_names = [
        RESOURCE_TASK_NAME,
        SCALING_TASK_NAME,
        DIAGNOSTIC_SETTINGS_TASK_NAME,
    ]
    return test_config
