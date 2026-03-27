# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError

from azure_integration_quickstart.constants import APP_REGISTRATION_WORKFLOW_TYPE, LOG_FORWARDING_WORKFLOW_TYPE
from azure_integration_quickstart.scopes import ManagementGroup, Scope, Subscription, flatten_scopes_to_unique_subscriptions
from azure_integration_quickstart.util import dd_request


@dataclass
class AppRegistrationUserSelections:
    """The selections the user has made in the quickstart onboarding UI for creating a new app registration."""

    scopes: Sequence[Scope]
    app_registration_config: dict
    log_forwarding_config: Optional[dict] = None


@dataclass
class LogForwardingUserSelections:
    """The selections the user has made in the quickstart onboarding UI for setting up a Log Forwarder.
    Log forwarding flow uses explicit add/remove; add_subscriptions and remove_subscriptions are scopes that have been flattened and deduped."""

    add_subscriptions: set[Subscription]
    remove_subscriptions: set[Subscription]
    log_forwarding_config: dict


def _scopes_from_subscription_and_management_group_dicts(
    subscriptions: list[dict], management_groups: list[dict]
) -> list[Scope]:
    """Parse selection dicts into a combined list of subscription and management group scopes."""
    subs = [Subscription(**s) for s in subscriptions]
    mgs = [
        ManagementGroup(
            **{
                **mg,
                "subscriptions": [Subscription(**s) for s in mg["subscriptions"]],
            }
        )
        for mg in management_groups
    ]
    return subs + mgs


def _poll_and_parse_selections(workflow_type: str, workflow_id: str) -> tuple[dict, tuple[Sequence[Scope], ...]]:
    """Poll and wait for user selections, then parse and return both the selections and scopes."""
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

        scopes = tuple(
            _scopes_from_subscription_and_management_group_dicts(
                selections["subscriptions"], selections["management_groups"]
            )
        )

        return selections, scopes


def receive_app_registration_selections(workflow_id: str) -> AppRegistrationUserSelections:
    """Poll and wait for the user to submit their app registration user selections."""
    selections, scopes = _poll_and_parse_selections(APP_REGISTRATION_WORKFLOW_TYPE, workflow_id)
    return AppRegistrationUserSelections(
        scopes,
        json.loads(selections["config_options"]),
        json.loads(selections["log_forwarding_options"])
        if "log_forwarding_options" in selections and selections["log_forwarding_options"]
        else None,
    )


def _poll_and_parse_log_forwarding_selections(workflow_id: str) -> LogForwardingUserSelections:
    """Poll for log forwarding workflow and parse add_/remove_ subscriptions and management groups.
    Only used by log forwarding flow; app registration uses _poll_and_parse_selections (subscriptions + management_groups)."""
    while True:
        try:
            status_response, _ = dd_request(
                "GET", f"/api/unstable/integration/azure/workflow/{LOG_FORWARDING_WORKFLOW_TYPE}/{workflow_id}"
            )
        except HTTPError as e:
            if e.code == 404:
                time.sleep(1)
                continue
            raise RuntimeError("Error retrieving user selections from Datadog") from e
        json_status_response = json.loads(status_response)
        if "selections" not in json_status_response["data"]["attributes"]["metadata"]:
            time.sleep(1)
            continue
        selections = json_status_response["data"]["attributes"]["metadata"]["selections"]

        add_subs = selections.get("add_subscriptions", [])
        add_mgs = selections.get("add_management_groups", [])
        remove_subs = selections.get("remove_subscriptions", [])
        remove_mgs = selections.get("remove_management_groups", [])

        add_subscriptions = flatten_scopes_to_unique_subscriptions(
            _scopes_from_subscription_and_management_group_dicts(add_subs, add_mgs)
        )
        remove_subscriptions = flatten_scopes_to_unique_subscriptions(
            _scopes_from_subscription_and_management_group_dicts(remove_subs, remove_mgs)
        )

        log_forwarding_options = selections.get("log_forwarding_options") or "{}"
        log_forwarding_config = json.loads(log_forwarding_options)

        return LogForwardingUserSelections(
            add_subscriptions=add_subscriptions,
            remove_subscriptions=remove_subscriptions,
            log_forwarding_config=log_forwarding_config,
        )


def receive_log_forwarding_selections(workflow_id: str) -> LogForwardingUserSelections:
    """Poll and wait for the user to submit their log forwarding user selections."""
    return _poll_and_parse_log_forwarding_selections(workflow_id)
