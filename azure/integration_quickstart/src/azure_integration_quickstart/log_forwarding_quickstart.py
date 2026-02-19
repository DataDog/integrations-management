# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
from concurrent.futures import ThreadPoolExecutor

from azure_integration_quickstart.constants import LOG_FORWARDING_WORKFLOW_TYPE
from azure_integration_quickstart.quickstart_shared import (
    login,
    report_existing_log_forwarders,
    setup_cancellation_handlers,
    upsert_log_forwarder,
    validate_environment_variables,
)
from azure_integration_quickstart.scopes import finish_collecting_scopes, flatten_scopes, get_tenant_and_subscriptions
from azure_integration_quickstart.script_status import StatusReporter
from azure_integration_quickstart.user_selections import receive_log_forwarding_selections


def main():
    validate_environment_variables()

    workflow_id = os.environ["WORKFLOW_ID"]
    status = StatusReporter(LOG_FORWARDING_WORKFLOW_TYPE, workflow_id)

    setup_cancellation_handlers(status)
    with status.report_step("login"):
        login()

    with status.report_step(
        "scopes_and_log_forwarders", loading_message="Collecting scopes and existing Log Forwarders"
    ) as step_metadata:
        tenant_id, subscriptions = get_tenant_and_subscriptions()
        with ThreadPoolExecutor() as executor:
            scopes_future = executor.submit(finish_collecting_scopes, tenant_id, subscriptions, step_metadata)
            lfo_future = executor.submit(report_existing_log_forwarders, subscriptions, step_metadata)
        scopes_future.result()
        exactly_one_log_forwarder = lfo_future.result()
    with status.report_step("selections", "Waiting for user selections in the Datadog UI"):
        selections = receive_log_forwarding_selections(workflow_id)
    if selections.log_forwarding_config:
        with status.report_step(
            "upsert_log_forwarder", f"{'Updating' if exactly_one_log_forwarder else 'Creating'} Log Forwarder"
        ):
            upsert_log_forwarder(selections.log_forwarding_config, flatten_scopes(selections.scopes))

    print("Script succeeded. You may exit this shell.")


if __name__ == "__main__":
    main()
