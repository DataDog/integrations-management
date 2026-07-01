# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared test data constants for azure's logging_install tests."""

import copy
import json
from unittest.mock import patch

from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType

# Azure env test subscriptions
SUB_1_ID = "11111111-1111-4111-a111-111111111111"
SUB_2_ID = "22222222-2222-4222-a222-222222222222"
SUB_3_ID = "33333333-3333-4333-a333-333333333333"
SUB_4_ID = "44444444-4444-4444-a444-444444444444"

# Control plane user settings
CONTROL_PLANE_SUBSCRIPTION_ID = "cccccccc-cccc-4ccc-accc-cccccccccccc"
CONTROL_PLANE_SUBSCRIPTION_NAME = "Test Control Plane Subscription"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = [SUB_1_ID, SUB_2_ID]
RESOURCE_TAG_FILTERS = "env:prod,team:infra"
PII_SCRUBBER_RULES = "rule1:\n  pattern: 'sensitive data'\n  replacement: 'test'"

# Control plane internal settings
CONTROL_PLANE_ID = "abcdef123456"
RESOURCE_TASK_NAME = f"resources-task-{CONTROL_PLANE_ID}"
SCALING_TASK_NAME = f"scaling-task-{CONTROL_PLANE_ID}"
DIAGNOSTIC_SETTINGS_TASK_NAME = f"diagnostic-settings-task-{CONTROL_PLANE_ID}"
DEPLOYER_JOB_NAME = f"deployer-task-{CONTROL_PLANE_ID}"
TEST_STORAGE_KEY = "test-storage-key"

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


def make_control_plane(
    id: str = CONTROL_PLANE_ID,
    region: str = CONTROL_PLANE_REGION,
    subscription_id: str = CONTROL_PLANE_SUBSCRIPTION_ID,
    resource_group: str = CONTROL_PLANE_RESOURCE_GROUP,
    type: ControlPlaneType = ControlPlaneType.FunctionApps,
) -> ControlPlane:
    """Construct a ControlPlane for tests, mocking the eager cache-key fetch (`execute`)
    that ControlPlane.__init__ performs so no real Azure CLI call is made."""
    mock_keys_response = json.dumps([{"keyName": "key1", "value": TEST_STORAGE_KEY, "permissions": "FULL"}])
    with patch("azure_logging_install.configuration.execute", return_value=mock_keys_response):
        return ControlPlane(
            id=id,
            region=region,
            subscription_id=subscription_id,
            resource_group=resource_group,
            type=type,
        )


def get_test_config() -> Configuration:
    """Return a fresh Configuration (with a fresh ControlPlane) for use in tests,
    so test mutations do not affect other tests."""
    return Configuration(
        control_plane=make_control_plane(),
        monitored_subs=copy.copy(MONITORED_SUBSCRIPTIONS),
        datadog_api_key=DATADOG_API_KEY,
        datadog_site=DATADOG_SITE,
        resource_tag_filters=RESOURCE_TAG_FILTERS,
        pii_scrubber_rules=PII_SCRUBBER_RULES,
        datadog_telemetry=True,
        log_level="INFO",
    )
