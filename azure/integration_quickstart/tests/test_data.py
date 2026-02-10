# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from email.message import Message
from urllib.error import HTTPError

from azure_integration_quickstart.permissions import FlatPermission
from azure_integration_quickstart.scopes import ASSIGN_ROLES_ACTION, ManagementGroup, Subscription
from azure_integration_quickstart.user_selections import (
    AppRegistrationUserSelections,
    LogForwardingUserSelections,
)

ERROR_404 = HTTPError(url="", code=404, msg="resource does not exist", hdrs=Message(), fp=None)
ERROR_403 = HTTPError(url="", code=403, msg="you don't have permission", hdrs=Message(), fp=None)

EXAMPLE_WORKFLOW_ID = "Example quickstart workflow"
EXAMPLE_STEP_ID = "example_workflow_step"

EXAMPLE_SUBSCRIPTIONS = [{"id": f"example-subscription-id-{i}", "name": f"Example Subscription {i}"} for i in range(4)]
EXAMPLE_MANAGEMENT_GROUP = {
    "id": "/providers/Microsoft.Management/managementGroups/Azure-Integrations-Mg",
    "name": "Azure Integrations group of subscriptions",
    "subscriptions": [EXAMPLE_SUBSCRIPTIONS[0], EXAMPLE_SUBSCRIPTIONS[1]],
}
EXAMPLE_MANAGEMENT_GROUP_EMPTY = {
    "id": "/providers/Microsoft.Management/managementGroups/Azure-Integrations-Mg2",
    "name": "Empty management group",
    "subscriptions": [],
}
EXAMPLE_MANAGEMENT_GROUP_OVERLAP = {
    "id": "/providers/Microsoft.Management/managementGroups/Azure-Integrations-Mg3",
    "name": "Empty management group",
    "subscriptions": [EXAMPLE_SUBSCRIPTIONS[2], EXAMPLE_SUBSCRIPTIONS[1]],
}

EXAMPLE_SUBSCRIPTION_SCOPES = [Subscription(**sub) for sub in EXAMPLE_SUBSCRIPTIONS]
EXAMPLE_MANAGEMENT_GROUP_SCOPE = ManagementGroup.from_dict(EXAMPLE_MANAGEMENT_GROUP)
EXAMPLE_MANAGEMENT_GROUP_EMPTY_SCOPE = ManagementGroup.from_dict(EXAMPLE_MANAGEMENT_GROUP_EMPTY)
EXAMPLE_MANAGEMENT_GROUP_OVERLAP_SCOPE = ManagementGroup.from_dict(EXAMPLE_MANAGEMENT_GROUP_OVERLAP)


DEFAULT_CONFIG_OPTIONS_JSON = '{"automute":false,"metrics_enabled":false,"metrics_enabled_default":true,"custom_metrics_enabled":false,"usage_metrics_enabled":true,"resource_provider_configs":[],"cspm_enabled":false,"resource_collection_enabled":false,"source":"datadog_web_ui","validate":true}'
DEFAULT_CONFIG_OPTIONS = {
    "automute": False,
    "metrics_enabled": False,
    "metrics_enabled_default": True,
    "custom_metrics_enabled": False,
    "usage_metrics_enabled": True,
    "resource_provider_configs": [],
    "cspm_enabled": False,
    "resource_collection_enabled": False,
    "source": "datadog_web_ui",
    "validate": True,
}

EXAMPLE_LOG_FORWARDER_RESOURCE_NAME = "example-lfo-control-plane"
EXAMPLE_LOG_FORWARDER_JSON = f'{{"resourceGroupName": "{EXAMPLE_LOG_FORWARDER_RESOURCE_NAME}", "controlPlaneSubscriptionId": "{EXAMPLE_SUBSCRIPTIONS[1]["id"]}", "controlPlaneSubscriptionName": "{EXAMPLE_SUBSCRIPTIONS[1]["name"]}", "controlPlaneRegion": "eastus"}}'
EXAMPLE_LOG_FORWARDER = {
    "resourceGroupName": EXAMPLE_LOG_FORWARDER_RESOURCE_NAME,
    "controlPlaneSubscriptionId": EXAMPLE_SUBSCRIPTIONS[1]["id"],
    "controlPlaneSubscriptionName": EXAMPLE_SUBSCRIPTIONS[1]["name"],
    "controlPlaneRegion": "eastus",
}


def make_selections_response(
    subscriptions=[], management_groups=[], config_options=DEFAULT_CONFIG_OPTIONS_JSON, log_forwarding_options=None
):
    result = {
        "data": {
            "id": "example-integration-id",
            "type": "add_azure_app_registration",
            "attributes": {
                "metadata": {
                    "selections": {
                        "config_options": config_options,
                        "management_groups": management_groups,
                        "subscriptions": subscriptions,
                    }
                }
            },
        }
    }
    if log_forwarding_options:
        result["data"]["attributes"]["metadata"]["selections"]["log_forwarding_options"] = log_forwarding_options
    return json.dumps(result)


def make_lfo_selections_response(
    subscriptions=[], management_groups=[], log_forwarding_options=EXAMPLE_LOG_FORWARDER_JSON
):
    """Create a selections response for LFO workflow (no config_options)."""
    result = {
        "data": {
            "id": "example-lfo-integration-id",
            "type": "add_azure_log_forwarding",
            "attributes": {
                "metadata": {
                    "selections": {
                        "management_groups": management_groups,
                        "subscriptions": subscriptions,
                        "log_forwarding_options": log_forwarding_options,
                    }
                }
            },
        }
    }
    return json.dumps(result)


SUBSCRIPTION_SELECTION_RESPONSE = make_selections_response(
    subscriptions=[EXAMPLE_SUBSCRIPTIONS[0], EXAMPLE_SUBSCRIPTIONS[1], EXAMPLE_SUBSCRIPTIONS[2]]
)
MGROUP_SELECTION_RESPONSE = make_selections_response(management_groups=[EXAMPLE_MANAGEMENT_GROUP])
OVERLAPPING_SELECTIONS_RESPONSE = make_selections_response(
    subscriptions=[EXAMPLE_SUBSCRIPTIONS[1], EXAMPLE_SUBSCRIPTIONS[2]], management_groups=[EXAMPLE_MANAGEMENT_GROUP]
)
SELECTIONS_WITH_LOG_FORWARDING_RESPONSE = make_selections_response(log_forwarding_options=EXAMPLE_LOG_FORWARDER_JSON)

SUBSCRIPTION_SELECTION = AppRegistrationUserSelections(
    app_registration_config=DEFAULT_CONFIG_OPTIONS,
    scopes=[EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1], EXAMPLE_SUBSCRIPTION_SCOPES[2]],
)
MGROUP_SELECTIONS = AppRegistrationUserSelections(
    app_registration_config=DEFAULT_CONFIG_OPTIONS,
    scopes=[EXAMPLE_MANAGEMENT_GROUP_SCOPE],
)
OVERLAPPING_SELECTIONS = AppRegistrationUserSelections(
    app_registration_config=DEFAULT_CONFIG_OPTIONS,
    scopes=[
        EXAMPLE_SUBSCRIPTION_SCOPES[0],
        EXAMPLE_SUBSCRIPTION_SCOPES[1],
        EXAMPLE_SUBSCRIPTION_SCOPES[2],
        EXAMPLE_MANAGEMENT_GROUP_SCOPE,
    ],
)
MGROUP_SELECTIONS = AppRegistrationUserSelections(
    app_registration_config=DEFAULT_CONFIG_OPTIONS,
    scopes=[EXAMPLE_MANAGEMENT_GROUP_SCOPE],
)
SELECTIONS_WITH_LOG_FORWARDING = AppRegistrationUserSelections(
    app_registration_config=DEFAULT_CONFIG_OPTIONS, log_forwarding_config=EXAMPLE_LOG_FORWARDER, scopes=[]
)


LFO_SELECTION_RESPONSE = make_lfo_selections_response(
    subscriptions=[EXAMPLE_SUBSCRIPTIONS[0], EXAMPLE_SUBSCRIPTIONS[1]],
    log_forwarding_options=EXAMPLE_LOG_FORWARDER_JSON,
)
LFO_SELECTION = LogForwardingUserSelections(
    log_forwarding_config=EXAMPLE_LOG_FORWARDER,
    scopes=[EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1]],
)

FLAT_PERMISSION_EMPTY = FlatPermission([], [])
FLAT_PERMISSION_NO_ASSIGN_ROLES = FlatPermission(
    ["Microsoft.Authorization/roleAssignments/read", "Microsoft.something/else"], []
)
FLAT_PERMISSION_ASSIGN_ROLES = FlatPermission([ASSIGN_ROLES_ACTION, "Microsoft.something/else"], [])
