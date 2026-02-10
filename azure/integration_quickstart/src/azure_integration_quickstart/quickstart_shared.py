# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared functions and constants used by the main and log forwarding quickstart scripts."""

import os
import signal
import sys
import threading
from typing import TypedDict

from az_shared.errors import AzCliNotAuthenticatedError, AzCliNotInstalledError
from az_shared.execute_cmd import execute
from azure_integration_quickstart.scopes import Scope, report_available_scopes
from azure_integration_quickstart.script_status import Status, StatusReporter
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


def validate_environment_variables() -> None:
    """Validate that all required environment variables are set."""
    if missing_environment_vars := {var for var in REQUIRED_ENVIRONMENT_VARS if not os.environ.get(var)}:
        print(f"Missing required environment variables: {', '.join(missing_environment_vars)}")
        print('Use the "copy" button from the quickstart UI to grab the complete command.')
        if missing_environment_vars == {"DD_API_KEY", "DD_APP_KEY"}:
            print("\nNOTE: Manually selecting and copying the command won't include the masked keys.")
        sys.exit(1)


def setup_cancellation_handlers(status: StatusReporter) -> None:
    """Set up handler for manual script disconnection and 30-minute timeout."""

    def interrupt_handler(*_args):
        status.report("connection", Status.CANCELLED, "disconnected by user")
        exit(1)

    def time_out():
        status.report("connection", Status.CANCELLED, "session expired")
        print(
            "\nSession expired. If you still wish to create a new Datadog configuration, "
            "please reload the onboarding page in Datadog and reconnect using the provided command."
        )
        os._exit(1)

    signal.signal(signal.SIGINT, interrupt_handler)

    timer = threading.Timer(30 * 60, time_out)
    timer.daemon = True
    timer.start()


def login(status: StatusReporter) -> None:
    """Perform the Azure CLI login with error handling."""
    with status.report_step("login"):
        try:
            # Check if user is logged into Azure CLI
            if not execute(Cmd(["az", "account", "show"]), can_fail=True):
                raise AzCliNotAuthenticatedError(
                    "Azure CLI is not authenticated. Please run 'az login' first and retry"
                )
        except Exception as e:
            if "az: command not found" in str(e):
                print("You must install and log in to Azure CLI to run this script.")
                raise AzCliNotInstalledError(str(e)) from e
            else:
                print("You must be logged in to Azure CLI to run this script. Run `az login` and try again.")
                raise AzCliNotAuthenticatedError(str(e)) from e
        else:
            print("Connected! Leave this shell running and go back to the Datadog UI to continue.")


def collect_scopes(status: StatusReporter) -> tuple[list[Scope], list[Scope]]:
    """Collect available Azure scopes (subscriptions and management groups)."""
    with status.report_step("scopes", "Collecting scopes") as step_metadata:
        return report_available_scopes(step_metadata)


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
