# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import signal
import sys
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict
from urllib.error import URLError

from az_shared.az_cmd import AzCmd, execute, execute_json
from az_shared.errors import (
    AccessError,
    AppRegistrationCreationPermissionsError,
    AzCliNotAuthenticatedError,
    AzCliNotInstalledError,
    InteractiveAuthenticationRequiredError,
)
from azure_integration_quickstart.extension.vm_extension import list_vms_for_subscriptions, set_extension_latest
from azure_integration_quickstart.role_assignments import can_current_user_create_applications
from azure_integration_quickstart.scopes import Scope, Subscription, flatten_scopes, report_available_scopes
from azure_integration_quickstart.script_status import Status, StatusReporter
from azure_integration_quickstart.user_selections import receive_user_selections
from azure_integration_quickstart.util import dd_request
from azure_logging_install.configuration import Configuration
from azure_logging_install.existing_lfo import LfoMetadata, check_existing_lfo
from azure_logging_install.main import install_log_forwarder


def ensure_login() -> None:
    """Ensure that the user is logged into the Azure CLI. If not, raise an exception."""
    if not execute(AzCmd("account", "show"), can_fail=True):
        raise AzCliNotAuthenticatedError("Azure CLI is not authenticated. Please run 'az login' first and retry")


class LogForwarderPayload(TypedDict):
    """Log Forwarder format expected by quickstart UI"""

    resourceGroupName: str
    controlPlaneSubscriptionId: str
    controlPlaneSubscriptionName: str
    controlPlaneRegion: str
    tagFilters: str
    piiFilters: str


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


@dataclass
class AppRegistration:
    """An Azure app registration."""

    tenant_id: str
    client_id: str
    client_secret: str


APP_REGISTRATION_NAME_PREFIX = "datadog-azure-integration"
APP_REGISTRATION_CLIENT_SECRET_TTL_YEARS = 2
APP_REGISTRATION_ROLE = "Monitoring Reader"


def get_app_registration_name() -> str:
    return f"{APP_REGISTRATION_NAME_PREFIX}-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"


def create_app_registration_with_permissions(scopes: Iterable[Scope]) -> AppRegistration:
    """Create an app registration with the necessary permissions for Datadog to function over the given scopes."""
    cmd = (
        AzCmd("ad sp", "create-for-rbac")
        .param("--name", f'"{get_app_registration_name()}"')
        .param("--role", f'"{APP_REGISTRATION_ROLE}"')
        .param("--scopes", " ".join([s.scope for s in scopes]))
    )
    try:
        # Try setting the TTL to the max of 2 years.
        result = execute_json(cmd.param("--years", f"{APP_REGISTRATION_CLIENT_SECRET_TTL_YEARS}"))
        # If it fails, just use the default TTL.
    except Exception:
        try:
            result = execute_json(cmd)
        except AccessError as e:
            raise AppRegistrationCreationPermissionsError(str(e)) from e
        except InteractiveAuthenticationRequiredError as e:
            # TODO: Run the auth commands in the background and prompt the user in the setup UI.
            raise InteractiveAuthenticationRequiredError(e.commands, str(e))

    return AppRegistration(result["tenant"], result["appId"], result["password"])


def submit_integration_config(app_registration: AppRegistration, config: dict) -> None:
    """Submit a new configuration to Datadog."""
    try:
        dd_request(
            "POST",
            "/api/v1/integration/azure",
            {
                **config,
                "client_id": app_registration.client_id,
                "client_secret": app_registration.client_secret,
                "tenant_name": app_registration.tenant_id,
                "source": "quickstart",
                "validate": False,
            },
        )
    except URLError as e:
        raise RuntimeError("Error creating Azure Integration in Datadog") from e


def submit_config_identifier(workflow_id: str, app_registration: AppRegistration) -> None:
    """Submit an identifier to Datadog for the new configuration so that it can be displayed to the user."""
    try:
        dd_request(
            "POST",
            "/api/unstable/integration/azure/setup/serviceprincipal",
            {
                "data": {
                    "id": workflow_id,
                    "type": "add_azure_app_registration",
                    "attributes": {"client_id": app_registration.client_id, "tenant_id": app_registration.tenant_id},
                }
            },
        )
    except URLError as e:
        raise RuntimeError("Error submitting configuration identifier to Datadog") from e


def upsert_log_forwarder(config: dict, subscriptions: set[Subscription]):
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


REQUIRED_ENVIRONMENT_VARS = {"DD_API_KEY", "DD_APP_KEY", "DD_SITE", "WORKFLOW_ID"}


def main():
    if missing_environment_vars := {var for var in REQUIRED_ENVIRONMENT_VARS if not os.environ.get(var)}:
        print(f"Missing required environment variables: {', '.join(missing_environment_vars)}")
        print('Use the "copy" button from the quickstart UI to grab the complete command.')
        if missing_environment_vars == {"DD_API_KEY", "DD_APP_KEY"}:
            print("\nNOTE: Manually selecting and copying the command won't include the masked keys.")
        sys.exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    status = StatusReporter(workflow_id)

    # report if the user manually disconnects the script
    def interrupt_handler(*_args):
        status.report("connection", Status.DISCONNECTED, "disconnected by user")
        exit(1)

    signal.signal(signal.SIGINT, interrupt_handler)

    # give up after 30 minutes
    def time_out():
        status.report("connection", Status.DISCONNECTED, "session expired")
        print(
            "\nSession expired. If you still wish to create a new Datadog configuration, please reload the onboarding page in Datadog and reconnect using the provided command."
        )
        os._exit(1)

    timer = threading.Timer(30 * 60, time_out)
    timer.daemon = True
    timer.start()

    with status.report_step("login"):
        try:
            ensure_login()
        except Exception as e:
            if "az: command not found" in str(e):
                print("You must install and log in to Azure CLI to run this script.")
                raise AzCliNotInstalledError(str(e)) from e
            else:
                print("You must be logged in to Azure CLI to run this script. Run `az login` and try again.")
                raise AzCliNotAuthenticatedError(str(e)) from e
        else:
            print("Connected! Leave this shell running and go back to the Datadog UI to continue.")

    def _check_app_registration_permissions() -> None:
        with StatusReporter(workflow_id).report_step(
            "app_registration_permissions", "Verifying that the current user can create app registrations"
        ):
            if not can_current_user_create_applications():
                raise AppRegistrationCreationPermissionsError("The current user cannot create app registrations")

    def _collect_scopes() -> tuple[list[Scope], list[Scope]]:
        with StatusReporter(workflow_id).report_step("scopes", "Collecting scopes"):
            return report_available_scopes(workflow_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_collect_scopes), executor.submit(_check_app_registration_permissions)]
    subscriptions, _ = futures[0].result()
    # NOTE: For now, we do not evaluate the `result` of the `_check_app_registration_permissions` future.
    # We initially just want to report the status of this operation rather than bubbling up the exception.
    # Once correctness is verified, this will be used to early exit.

    with status.report_step(
        "log_forwarders", loading_message="Collecting existing Log Forwarders", required=False
    ) as step_metadata:
        exactly_one_log_forwarder = report_existing_log_forwarders(subscriptions, step_metadata)
    with status.report_step("selections", "Waiting for user selections in the Datadog UI"):
        selections = receive_user_selections(workflow_id)
    with status.report_step("app_registration", "Creating app registration in Azure"):
        app_registration = create_app_registration_with_permissions(selections.scopes)
    with status.report_step("integration_config", "Submitting new configuration to Datadog"):
        submit_integration_config(app_registration, selections.app_registration_config)
    with status.report_step("config_identifier", "Submitting new configuration identifier to Datadog"):
        submit_config_identifier(workflow_id, app_registration)
    if selections.app_registration_config.get("is_agent_enabled"):
        with status.report_step("agent", "Installing the Datadog Agent"):
            set_extension_latest(list_vms_for_subscriptions([s.id for s in flatten_scopes(selections.scopes)]))
    if selections.log_forwarding_config:
        with status.report_step(
            "upsert_log_forwarder", f"{'Updating' if exactly_one_log_forwarder else 'Creating'} Log Forwarder"
        ):
            upsert_log_forwarder(selections.log_forwarding_config, flatten_scopes(selections.scopes))

    print("Script succeeded. You may exit this shell.")


if __name__ == "__main__":
    main()
