# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared functions and constants used by the main and log forwarding quickstart scripts."""

import os
import signal
import sys
import threading
from typing import Optional, TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired  # type: ignore[import-untyped]

from az_shared.auth import check_login
from az_shared.errors import AzCliNotAuthenticatedError, AzCliNotInstalledError
from azure_integration_quickstart.scopes import Scope
from azure_integration_quickstart.script_status import Status, StatusReporter
from azure_logging_install.configuration import Configuration
from azure_logging_install.existing_lfo import LfoMetadata, check_existing_lfo
from azure_logging_install.main import install_log_forwarder

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
    monitoredSubscriptions: NotRequired[list[dict[str, str]]]


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


def login() -> None:
    """Perform the Azure CLI login with error handling."""
    try:
        check_login()
    except AzCliNotInstalledError:
        print("You must install and log in to Azure CLI to run this script.")
        raise
    except AzCliNotAuthenticatedError:
        print("You must be logged in to Azure CLI to run this script. Run `az login` and try again.")
        raise
    else:
        print("Connected! Leave this shell running and go back to the Datadog UI to continue.")


def build_log_forwarder_payload(metadata: LfoMetadata, include_monitored_scopes: bool) -> LogForwarderPayload:
    payload = LogForwarderPayload(
        resourceGroupName=metadata.control_plane.resource_group,
        controlPlaneSubscriptionId=metadata.control_plane.sub_id,
        controlPlaneSubscriptionName=metadata.control_plane.sub_name,
        controlPlaneRegion=metadata.control_plane.region,
        tagFilters=metadata.tag_filter,
        piiFilters=metadata.pii_rules,
    )
    if include_monitored_scopes:
        payload["monitoredSubscriptions"] = [
            {"id": sub_id, "name": name} for sub_id, name in metadata.monitored_subs.items()
        ]
    return payload


def report_existing_log_forwarders(
    subscriptions: list[Scope], step_metadata: dict, include_monitored_scopes: bool
) -> tuple[bool, Optional[LfoMetadata]]:
    """Send Datadog any existing Log Forwarders in the tenant. Returns (exactly_one, existing_lfo).
    When include_monitored_scopes is True, each payload includes monitoredSubscriptions.
    When exactly one LFO is found, existing_lfo is that LfoMetadata; otherwise existing_lfo is None."""
    scope_id_to_name = {s.id: s.name for s in subscriptions}
    forwarders = check_existing_lfo(set(scope_id_to_name.keys()), scope_id_to_name)
    step_metadata["log_forwarders"] = [
        build_log_forwarder_payload(forwarder, include_monitored_scopes) for forwarder in forwarders.values()
    ]
    exactly_one = len(forwarders) == 1
    existing_lfo = list(forwarders.values())[0] if exactly_one else None
    return exactly_one, existing_lfo


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
