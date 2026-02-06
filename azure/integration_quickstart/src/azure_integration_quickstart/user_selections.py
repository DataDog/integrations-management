# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError

from azure_integration_quickstart.scopes import ManagementGroup, Scope, Subscription
from azure_integration_quickstart.util import dd_request


@dataclass
class UserSelections:
    """The selections the user has made in the quickstart onboarding UI"""

    scopes: Sequence[Scope]


@dataclass
class AppRegistrationUserSelections(UserSelections):
    """The selections the user has made in the quickstart onboarding UI for creating a new app registration."""

    app_registration_config: dict
    log_forwarding_config: Optional[dict] = None


@dataclass
class LFOUserSelections(UserSelections):
    """The selections the user has made in the quickstart onboarding UI for setting up a Log Forwarder."""

    log_forwarding_config: dict


def receive_user_selections(workflow_type: str, workflow_id: str) -> UserSelections:
    """Poll and wait for the user to submit their desired scopes and configuration options."""
    while True:
        try:
            status_response, _ = dd_request(
                "GET", f"/api/unstable/integration/azure/workflow/{workflow_type}/{workflow_id}"
            )
        except HTTPError as e:
            if e.code == 404:
                time.sleep(1)
                continue
            else:
                raise RuntimeError("Error retrieving user selections from Datadog") from e
        json_status_response = json.loads(status_response)
        # poll until user selections appear in workflow metadata
        if "selections" not in json_status_response["data"]["attributes"]["metadata"]:
            time.sleep(1)
            continue
        selections = json_status_response["data"]["attributes"]["metadata"]["selections"]
        subscriptions = [Subscription(**s) for s in selections["subscriptions"]]
        management_groups = [
            ManagementGroup(
                **{
                    **mg,
                    "subscriptions": [Subscription(**s) for s in mg["subscriptions"]],
                }
            )
            for mg in selections["management_groups"]
        ]
        if workflow_type == "azure-app-registration-setup":
            return AppRegistrationUserSelections(
                tuple(subscriptions + management_groups),
                json.loads(selections["config_options"]),
                json.loads(selections["log_forwarding_options"])
                if "log_forwarding_options" in selections and selections["log_forwarding_options"]
                else None,
            )
        else:  # workflow_type == "azure-log-forwarding-setup":
            return LFOUserSelections(
                tuple(subscriptions + management_groups),
                json.loads(selections["log_forwarding_options"]),
            )
