# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared functions and constants used by both full and LFO-only quickstart scripts."""

import os
from typing import TypedDict

from az_shared.errors import AzCliNotAuthenticatedError
from az_shared.execute_cmd import execute
from azure_integration_quickstart.scopes import Scope, report_available_scopes
from azure_integration_quickstart.script_status import StatusReporter
from azure_logging_install.configuration import Configuration
from azure_logging_install.existing_lfo import LfoMetadata, check_existing_lfo
from azure_logging_install.main import install_log_forwarder
from common.shell import Cmd

# Required environment variables for both quickstart variants
REQUIRED_ENVIRONMENT_VARS = {"DD_API_KEY", "DD_APP_KEY", "DD_SITE", "WORKFLOW_ID"}


class LogForwarderPayload(TypedDict):
    """Log Forwarder format expected by quickstart UI"""

    resourceGroupName: str
    controlPlaneSubscriptionId: str
    controlPlaneSubscriptionName: str
    controlPlaneRegion: str
    tagFilters: str
    piiFilters: str


def ensure_login() -> None:
    """Ensure that the user is logged into the Azure CLI. If not, raise an exception."""
    if not execute(Cmd(["az", "account", "show"]), can_fail=True):
        raise AzCliNotAuthenticatedError("Azure CLI is not authenticated. Please run 'az login' first and retry")


def build_log_forwarder_payload(metadata: LfoMetadata) -> LogForwarderPayload:
    return LogForwarderPayload(
        resourceGroupName=metadata.control_plane.resource_group,
        controlPlaneSubscriptionId=metadata.control_plane.sub_id,
        controlPlaneSubscriptionName=metadata.control_plane.sub_name,
        controlPlaneRegion=metadata.control_plane.region,
        tagFilters=metadata.tag_filter,
        piiFilters=metadata.pii_rules,
    )


def report_existing_log_forwarders(subscriptions: list[Scope], step_metadata: dict) -> bool:
    """Send Datadog any existing Log Forwarders in the tenant and return whether we found exactly 1 Forwarder, in which case we will potentially update it."""
    scope_id_to_name = {s.id: s.name for s in subscriptions}
    forwarders = check_existing_lfo(set(scope_id_to_name.keys()), scope_id_to_name)
    step_metadata["log_forwarders"] = [build_log_forwarder_payload(forwarder) for forwarder in forwarders.values()]
    return len(forwarders) == 1


def upsert_log_forwarder(config: dict, subscriptions: set[Scope]):
    install_log_forwarder(
        Configuration(
            control_plane_region=config["controlPlaneRegion"],
            control_plane_sub_id=config["controlPlaneSubscriptionId"],
            control_plane_rg=config["resourceGroupName"],
            monitored_subs=",".join([s.id for s in subscriptions]),
            datadog_api_key=os.environ["DD_API_KEY"],
            datadog_site=os.environ["DD_SITE"],
            resource_tag_filters=config.get("tagFilters", ""),
            pii_scrubber_rules=config.get("piiFilters", ""),
        )
    )


def collect_scopes(status: StatusReporter) -> tuple[list[Scope], list[Scope]]:
    """Collect available Azure scopes (subscriptions and management groups)."""
    with status.report_step("scopes", "Collecting scopes") as step_metadata:
        return report_available_scopes(step_metadata)
