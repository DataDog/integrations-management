"""Shared test data constants for azure's logging_install tests."""

CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION_ID = "cp-sub-id"
CONTROL_PLANE_SUBSCRIPTION_NAME = "Test Control Plane Subscription"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"

SUB_1_ID = "sub-1-id"
SUB_2_ID = "sub-2-id"
SUB_3_ID = "sub-3-id"
SUB_4_ID = "sub-4-id"

SUB_ID_TO_NAME = {
    CONTROL_PLANE_SUBSCRIPTION_ID: CONTROL_PLANE_SUBSCRIPTION_NAME,
    SUB_1_ID: "Test Subscription 1",
    SUB_2_ID: "Test Subscription 2",
    SUB_3_ID: "Test Subscription 3",
    SUB_4_ID: "Test Subscription 4",
}

MONITORED_SUBSCRIPTIONS = f"{SUB_1_ID},{SUB_2_ID}"

DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"

RESOURCE_TAG_FILTERS = "env:prod,team:infra"
PII_SCRUBBER_RULES = "rule1:\n  pattern: 'sensitive data'\n  replacement: 'test'"
