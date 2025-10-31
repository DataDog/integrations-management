#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

# ruff: noqa: E402
import os
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TypedDict
from urllib.error import URLError

from az_shared.az_cmd import AzCmd, execute, execute_json
from az_shared.errors import AccessError, AzCliNotAuthenticatedError, UserActionRequiredError
from azure_integration_quickstart.scopes import Scope, Subscription, flatten_scopes, report_available_scopes
from azure_integration_quickstart.script_status import Status, StatusReporter
from azure_integration_quickstart.user_selections import receive_user_selections
from azure_integration_quickstart.util import MAX_WORKERS, dd_request
from azure_logging_install.configuration import Configuration
from azure_logging_install.existing_lfo import LfoMetadata, check_existing_lfo
from azure_logging_install.main import install_log_forwarder


@dataclass
class AppRegistration:
    """An Azure app registration."""

    tenant_id: str
    client_id: str
    client_secret: str


class LogForwarderPayload(TypedDict):
    """Log Forwarder format expected by quickstart UI"""

    resourceGroupName: str
    controlPlaneSubscriptionId: str
    controlPlaneSubscriptionName: str
    controlPlaneRegion: str
    tagFilters: Optional[str]
    piiFilters: Optional[str]


# Main


def ensure_login() -> None:
    """Ensure that the user is logged into the Azure CLI. If not, raise an exception."""
    if not execute(AzCmd("account", "show"), can_fail=True):
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


APP_REGISTRATION_NAME_PREFIX = "datadog-azure-integration"
APP_REGISTRATION_CLIENT_SECRET_TTL_YEARS = 2
APP_REGISTRATION_ROLE = "Monitoring Reader"


def get_app_registration_name() -> str:
    return f"{APP_REGISTRATION_NAME_PREFIX}-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"


def create_app_registration_with_permissions(scopes: Sequence[Scope]) -> AppRegistration:
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
        result = execute_json(cmd)

    return AppRegistration(result["tenant"], result["appId"], result["password"])


MS_GRAPH_API = "00000003-0000-0000-c000-000000000000"


def add_ms_graph_app_role_assignments(app_registration: AppRegistration, roles: list[str]) -> None:
    """Assign an app registration the necessary app roles for Datadog to function.

    See https://learn.microsoft.com/en-us/graph/permissions-reference for more information."""
    execute(
        AzCmd("ad app permission", "add")
        .param("--id", f'"{app_registration.client_id}"')
        .param("--api", MS_GRAPH_API)
        .param("--api-permissions", " ".join([f"{role}=Role" for role in roles]))
    )
    execute(AzCmd("ad app permission", "admin-consent").param("--id", f'"{app_registration.client_id}"'))


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
    log_forwarder_config = Configuration(
        control_plane_region=config["controlPlaneRegion"],
        control_plane_sub_id=config["controlPlaneSubscriptionId"],
        control_plane_rg=config["resourceGroupName"],
        monitored_subs=",".join([s.id for s in subscriptions]),
        datadog_api_key=os.environ["DD_API_KEY"],
        datadog_site=os.environ["DD_SITE"],
    )
    if "tagFilters" in config:
        log_forwarder_config.resource_tag_filters = config["tagFilters"]
    if "piiFilters" in config:
        log_forwarder_config.pii_scrubber_rules = config["piiFilters"]

    try:
        install_log_forwarder(log_forwarder_config)
    except AccessError as e:
        raise UserActionRequiredError(
            f"Insufficient Azure user permissions when installing log forwarder. Please check your Azure permissions and try again: {e}"
        ) from e


def assign_permissions(client_id: str, scopes: Sequence[Scope]) -> None:
    """Assign an app registration the necessary permissions for Datadog to function over the given scopes."""
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        for scope in scopes:
            executor.submit(
                execute,
                AzCmd("role assignment", "create")
                .param("--assignee", f'"{client_id}"')
                .param("--role", f'"{APP_REGISTRATION_ROLE}')
                .param("--scope", f'"{scope.scope}"'),
            )


REQUIRED_ENVIRONMENT_VARS = {"DD_API_KEY", "DD_APP_KEY", "DD_SITE", "WORKFLOW_ID"}


def time_out(status: StatusReporter):
    status.report("connection", Status.ERROR, "session expired")
    print(
        "\nSession expired. If you still wish to create a new Datadog configuration, please reload the onboarding page in Datadog and reconnect using the provided command."
    )
    os._exit(1)


def main():
    if missing_environment_vars := REQUIRED_ENVIRONMENT_VARS - os.environ.keys():
        print(f"Missing required environment variables: {', '.join(missing_environment_vars)}")
        sys.exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    status = StatusReporter(workflow_id)

    # give up after 30 minutes
    timer = threading.Timer(30 * 60, time_out, [status])
    timer.daemon = True
    timer.start()

    try:
        with status.report_step("login"):
            ensure_login()
    except Exception as e:
        if "az: command not found" in str(e):
            print("You must install and log in to Azure CLI to run this script.")
        else:
            print("You must be logged in to Azure CLI to run this script. Run `az login` and try again.")
        sys.exit(1)
    else:
        print("Connected! Leave this shell running and go back to the Datadog UI to continue.")

    with status.report_step("scopes", "Collecting scopes"):
        subscriptions, _ = report_available_scopes(workflow_id)
    exactly_one_log_forwarder = False
    with status.report_step(
        "log_forwarders",
        loading_message="Collecting existing Log Forwarders",
        required=False,
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
    if selections.log_forwarding_config:
        with status.report_step(
            "upsert_log_forwarder", f"{'Updating' if exactly_one_log_forwarder else 'Creating'} Log Forwarder"
        ):
            upsert_log_forwarder(selections.log_forwarding_config, flatten_scopes(selections.scopes))

    print("Script succeeded. You may exit this shell.")


if __name__ == "__main__":
    main()
