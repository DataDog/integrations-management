# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from urllib.error import URLError

from az_shared.errors import (
    AccessError,
    AppRegistrationCreationPermissionsError,
    InteractiveAuthenticationRequiredError,
)
from az_shared.execute_cmd import execute, execute_json
from azure_integration_quickstart.constants import APP_REGISTRATION_WORKFLOW_TYPE
from azure_integration_quickstart.extension.vm_extension import list_vms_for_subscriptions, set_extension_latest
from azure_integration_quickstart.quickstart_shared import (
    login,
    report_existing_log_forwarders,
    setup_cancellation_handlers,
    upsert_log_forwarder,
    validate_environment_variables,
)
from azure_integration_quickstart.role_assignments import can_current_user_create_applications
from azure_integration_quickstart.scopes import (
    Scope,
    Subscription,
    flatten_scopes_to_unique_subscriptions,
    report_available_scopes,
)
from azure_integration_quickstart.script_status import Status, StatusReporter
from azure_integration_quickstart.user_selections import receive_app_registration_selections
from azure_integration_quickstart.util import dd_request
from common.shell import Cmd


@dataclass
class AppRegistration:
    """An Azure app registration."""

    tenant_id: str
    client_id: str
    client_secret: str


APP_REGISTRATION_NAME_PREFIX = "datadog-azure-integration"
APP_REGISTRATION_CLIENT_SECRET_TTL_YEARS = 2
APP_REGISTRATION_ROLE = "Monitoring Reader"

FEDERATED_AUTH_SECRET_PLACEHOLDER = "SECRETLESS_AUTH"
FEDERATED_CREDENTIAL_NAME = "datadog"
FEDERATED_AUTH_ISSUER = "https://ticino-sandbox.identity-sandbox.local-cluster.local-dc.fabric.dog:8443/v1/issuer/pine"
FEDERATED_AUTH_SUBJECT = "datadog-oidc"
FEDERATED_CREDENTIAL_DESCRIPTION = (
    "Federated credential that permits Datadog to authenticate without storing a client secret"
)
FEDERATED_AUTH_AUDIENCE = "api://AzureADTokenExchange"


def get_app_registration_name() -> str:
    return f"{APP_REGISTRATION_NAME_PREFIX}-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"


def run_app_reg_create_cmd(cmd: Cmd):
    try:
        return execute_json(cmd)
    except AccessError as e:
        raise AppRegistrationCreationPermissionsError(str(e)) from e
    except InteractiveAuthenticationRequiredError as e:
        # TODO: Run the auth commands in the background and prompt the user in the setup UI.
        raise InteractiveAuthenticationRequiredError(e.commands, str(e))


def create_app_registration_with_permissions(scopes: Iterable[Scope], use_secretless_auth=False) -> AppRegistration:
    """Create an app registration with the necessary permissions for Datadog to function over the given scopes."""
    cmd = (
        Cmd(["az", "ad", "sp", "create-for-rbac"])
        .param("--name", get_app_registration_name())
        .param("--role", APP_REGISTRATION_ROLE)
        .param_list("--scopes", [s.scope for s in scopes])
    )
    if use_secretless_auth:
        result = run_app_reg_create_cmd(cmd)
        execute(
            Cmd(["az", "ad", "app", "federated-credential", "create"])
            .param("--id", result["appId"])
            .param(
                "--parameters",
                f"""{{
                    "name": "{FEDERATED_CREDENTIAL_NAME}",
                    "issuer": "{FEDERATED_AUTH_ISSUER}",
                    "subject": "{FEDERATED_AUTH_SUBJECT}",
                    "description": "{FEDERATED_CREDENTIAL_DESCRIPTION}",
                    "audiences": ["{FEDERATED_AUTH_AUDIENCE}"]
                }}""",
            )
        )

    else:
        try:
            # Try setting the TTL to the max of 2 years.
            result = execute_json(cmd.param("--years", f"{APP_REGISTRATION_CLIENT_SECRET_TTL_YEARS}"))
            # If it fails, just use the default TTL.
        except Exception:
            result = run_app_reg_create_cmd(cmd)

    return AppRegistration(
        result["tenant"],
        result["appId"],
        # replace client secret with a placeholder if the user has opted for secretless auth
        FEDERATED_AUTH_SECRET_PLACEHOLDER if use_secretless_auth else result["password"],
    )


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
    validate_environment_variables()

    workflow_id = os.environ["WORKFLOW_ID"]
    status = StatusReporter(APP_REGISTRATION_WORKFLOW_TYPE, workflow_id)

    setup_cancellation_handlers(status)
    with status.report_step("login"):
        login()

    def _check_app_registration_permissions() -> None:
        if not can_current_user_create_applications():
            error = AppRegistrationCreationPermissionsError("The current user cannot create app registrations")
            StatusReporter(APP_REGISTRATION_WORKFLOW_TYPE, workflow_id).report(
                "app_registration_permissions", Status.USER_ACTIONABLE_ERROR, error.user_action_message
            )
            raise error

    def _collect_scopes() -> list[Subscription]:
        with status.report_step("scopes", "Collecting scopes") as step_metadata:
            return report_available_scopes(step_metadata)

    with ThreadPoolExecutor() as executor:
        scopes_future = executor.submit(_collect_scopes)
        # NOTE: For now, we do not bubble up any exceptions from `_check_app_registration_permissions`.
        # We're just reporting the status to verify correctness. Later, this will be used to early exit.
        executor.submit(_check_app_registration_permissions)
    subscriptions = scopes_future.result()

    with status.report_step(
        "log_forwarders", loading_message="Collecting existing Log Forwarders", required=False
    ) as step_metadata:
        existing_lfo = report_existing_log_forwarders(subscriptions, step_metadata, False)
    with status.report_step("selections", "Waiting for user selections in the Datadog UI"):
        selections = receive_app_registration_selections(workflow_id)
    with status.report_step("app_registration", "Creating app registration in Azure"):
        app_registration = create_app_registration_with_permissions(selections.scopes)
    with status.report_step("integration_config", "Submitting new configuration to Datadog"):
        submit_integration_config(app_registration, selections.app_registration_config)
    with status.report_step("config_identifier", "Submitting new configuration identifier to Datadog") as step_metadata:
        step_metadata["service_principal"] = {
            "client_id": app_registration.client_id,
            "tenant_id": app_registration.tenant_id,
        }
    if selections.app_registration_config.get("is_agent_enabled"):
        with status.report_step("agent", "Installing the Datadog Agent"):
            set_extension_latest(
                list_vms_for_subscriptions([s.id for s in flatten_scopes_to_unique_subscriptions(selections.scopes)])
            )
    if selections.log_forwarding_config:
        with status.report_step("upsert_log_forwarder", f"{'Updating' if existing_lfo else 'Creating'} Log Forwarder"):
            selected_subs = flatten_scopes_to_unique_subscriptions(selections.scopes)
            # App registration flow is add-only: when an LFO exists, monitored scopes becomes existing ∪ selected.
            if existing_lfo:
                existing_subs = {
                    Subscription(id=sub_id, name=name) for sub_id, name in existing_lfo.monitored_subs.items()
                }
                final_scopes = existing_subs | selected_subs
            else:
                final_scopes = selected_subs
            upsert_log_forwarder(selections.log_forwarding_config, final_scopes)

    print("Script succeeded. You may exit this shell.")


if __name__ == "__main__":
    main()
