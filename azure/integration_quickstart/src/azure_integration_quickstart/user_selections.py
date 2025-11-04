# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError

from azure_integration_quickstart.scopes import ManagementGroup, Scope, Subscription, SubscriptionList
from azure_integration_quickstart.util import dd_request


@dataclass
class UserSelections:
    """The selections the user has made in the quickstart onboarding UI"""

    scopes: Sequence[Scope]
    app_registration_config: dict
    log_forwarding_config: Optional[dict] = None


def receive_user_selections(workflow_id: str) -> UserSelections:
    """Poll and wait for the user to submit their desired scopes and configuration options."""
    while True:
        try:
            response, _ = dd_request("GET", f"/api/unstable/integration/azure/setup/selections/{workflow_id}")
        except HTTPError as e:
            if e.code == 404:
                time.sleep(1)
                continue
            else:
                raise RuntimeError("Error retrieving user selections from Datadog") from e
        json_response = json.loads(response)
        attributes = json_response["data"]["attributes"]
        subscriptions = [Subscription(**s) for s in attributes["subscriptions"]["subscriptions"]]
        management_groups = [
            ManagementGroup(
                **{
                    **mg,
                    "subscriptions": SubscriptionList(
                        [Subscription(**s) for s in mg["subscriptions"]["subscriptions"]]
                    ),
                }
            )
            for mg in attributes["management_groups"]["management_groups"]
        ]
        return UserSelections(
            tuple(subscriptions + management_groups),
            json.loads(attributes["config_options"]),
            json.loads(attributes["log_forwarding_options"])
            if "log_forwarding_options" in attributes and attributes["log_forwarding_options"]
            else None,
        )
