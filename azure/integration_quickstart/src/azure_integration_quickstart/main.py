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
from time import sleep
from urllib.error import URLError

from az_shared.errors import (
    AccessError,
    AppRegistrationCreationPermissionsError,
    AzCliNotAuthenticatedError,
    AzCliNotInstalledError,
    InteractiveAuthenticationRequiredError,
)
from az_shared.execute_cmd import execute_json
from azure_integration_quickstart.extension.vm_extension import list_vms_for_subscriptions, set_extension_latest
from azure_integration_quickstart.quickstart_shared import (
    REQUIRED_ENVIRONMENT_VARS,
    collect_scopes,
    ensure_login,
    report_existing_log_forwarders,
    upsert_log_forwarder,
)
from azure_integration_quickstart.role_assignments import can_current_user_create_applications
from azure_integration_quickstart.scopes import Scope, flatten_scopes
from azure_integration_quickstart.script_status import Status, StatusReporter
from azure_integration_quickstart.user_selections import receive_user_selections
from azure_integration_quickstart.util import dd_request
from common.shell import Cmd

CREATE_APP_REG_WORKFLOW_TYPE = "azure-app-registration-setup"


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
        Cmd(["az", "ad", "sp", "create-for-rbac"])
        .param("--name", get_app_registration_name())
        .param("--role", APP_REGISTRATION_ROLE)
        .param_list("--scopes", [s.scope for s in scopes])
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


def get_access_token_with_client_credentials(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    return execute_json(
        Cmd(["az", "rest"])
        .param("-m", "post")
        .param("-u", f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token")
        .param("-b", f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}&scope={scope}")
        .flag("--skip-authorization-header")
        .param("--query", "access_token")
    )


def set_access_token(az_rest_cmd: Cmd, token: str) -> Cmd:
    return az_rest_cmd.flag("--skip-authorization-header").param("--headers", f"Authorization=Bearer {token}")


def get_arm_scope() -> str:
    return f"{execute_json(Cmd(['az', 'cloud', 'show']).param('--query', 'endpoints.resourceManager')).strip('/')}/.default"


def get_subscription_count(access_token: str) -> int:
    return execute_json(
        set_access_token(Cmd(["az", "rest"]), access_token)
        .param("-u", "https://management.azure.com/subscriptions?api-version=2022-12-01")
        .param("--query", "count.value")
    )


def wait_for_app_registration_to_work(app_registration: AppRegistration) -> None:
    """Wait for a newly-created app registration's authn/authz to work."""
    # It will generally take at least this long. No point even trying before then.
    sleep(15)

    scope = get_arm_scope()
    while True:
        try:
            access_token = get_access_token_with_client_credentials(
                app_registration.tenant_id, app_registration.client_id, app_registration.client_secret, scope
            )
        except Exception:
            sleep(1)
        else:
            break

    consecutive_success_count = 0
    while True:
        # If we can read subscription metadata, the assigned access is being honored.
        if get_subscription_count(access_token) > 0:
            consecutive_success_count += 1
        else:
            consecutive_success_count = 0
        # Require several consecutive successes to account for eventual consistency.
        if consecutive_success_count >= 5:
            break
        else:
            sleep(1)


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
            },
        )
    except URLError as e:
        raise RuntimeError("Error creating Azure Integration in Datadog") from e


def main():
    if missing_environment_vars := {var for var in REQUIRED_ENVIRONMENT_VARS if not os.environ.get(var)}:
        print(f"Missing required environment variables: {', '.join(missing_environment_vars)}")
        print('Use the "copy" button from the quickstart UI to grab the complete command.')
        if missing_environment_vars == {"DD_API_KEY", "DD_APP_KEY"}:
            print("\nNOTE: Manually selecting and copying the command won't include the masked keys.")
        sys.exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    status = StatusReporter(CREATE_APP_REG_WORKFLOW_TYPE, workflow_id)

    # report if the user manually disconnects the script
    def interrupt_handler(*_args):
        status.report("connection", Status.CANCELLED, "disconnected by user")
        exit(1)

    signal.signal(signal.SIGINT, interrupt_handler)

    # give up after 30 minutes
    def time_out():
        status.report("connection", Status.CANCELLED, "session expired")
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
        if not can_current_user_create_applications():
            error = AppRegistrationCreationPermissionsError("The current user cannot create app registrations")
            StatusReporter(CREATE_APP_REG_WORKFLOW_TYPE, workflow_id).report(
                "app_registration_permissions", Status.USER_ACTIONABLE_ERROR, error.user_action_message
            )
            raise error

    with ThreadPoolExecutor() as executor:
        scopes_future = executor.submit(collect_scopes, status)
        # NOTE: For now, we do not bubble up any exceptions from `_check_app_registration_permissions`.
        # We're just reporting the status to verify correctness. Later, this will be used to early exit.
        executor.submit(_check_app_registration_permissions)
    subscriptions, _ = scopes_future.result()

    with status.report_step(
        "log_forwarders", loading_message="Collecting existing Log Forwarders", required=False
    ) as step_metadata:
        exactly_one_log_forwarder = report_existing_log_forwarders(subscriptions, step_metadata)
    with status.report_step("selections", "Waiting for user selections in the Datadog UI"):
        selections = receive_user_selections(CREATE_APP_REG_WORKFLOW_TYPE, workflow_id)
    with status.report_step("app_registration", "Creating app registration in Azure"):
        app_registration = create_app_registration_with_permissions(selections.scopes)
    if selections.app_registration_config.get("validate"):
        with status.report_step("validate_app_registration", "Validating app registration's access"):
            wait_for_app_registration_to_work(app_registration)
    with status.report_step("integration_config", "Submitting new configuration to Datadog"):
        submit_integration_config(app_registration, selections.app_registration_config)
    with status.report_step("config_identifier", "Submitting new configuration identifier to Datadog") as step_metadata:
        step_metadata["service_principal"] = {
            "client_id": app_registration.client_id,
            "tenant_id": app_registration.tenant_id,
        }
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
