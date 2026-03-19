# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Main entry point for the Azure Agentless Scanner Cloud Shell setup."""

import os
import signal
import sys
import threading

from .config import parse_config
from .errors import DatadogCredentialsError, SetupError
from .preflight import run_preflight_checks, validate_datadog_api_key, validate_datadog_app_key
from .reporter import Reporter
from .secrets import ensure_api_key_secret, get_key_vault_name
from .state_storage import ensure_state_storage


# Total number of steps in the deploy process:
#   1. Preflight checks
#   2. Create state storage (Storage Account + Key Vault)
#   3. Store API key in Key Vault
#   4. Generate Terraform configuration
#   5. Terraform init
#   6. Deploy infrastructure (Terraform apply)
TOTAL_STEPS = 6

SESSION_TIMEOUT_MINUTES = 30

COMMANDS = ["deploy", "help"]


def print_help() -> None:
    """Print usage help."""
    print()
    print("Datadog Agentless Scanner - Azure Cloud Shell Setup")
    print()
    print("Usage:")
    print("  python azure_agentless_setup.pyz <command>")
    print()
    print("Commands:")
    print("  deploy    Deploy the Agentless Scanner infrastructure")
    print("  help      Show this help message")
    print()
    print("=" * 60)
    print("DEPLOY - Environment Variables:")
    print("=" * 60)
    print()
    print("Required:")
    print("  DD_API_KEY             Datadog API key with Remote Configuration enabled")
    print("  DD_APP_KEY             Datadog Application key")
    print("  DD_SITE                Datadog site (e.g., datadoghq.com, datadoghq.eu)")
    print("  WORKFLOW_ID            Workflow ID from Datadog UI (UUID)")
    print("  SCANNER_SUBSCRIPTION   Azure subscription where the scanner will be deployed")
    print("  SCANNER_LOCATIONS      Comma-separated list of Azure locations (max 4)")
    print("  SUBSCRIPTIONS_TO_SCAN  Comma-separated list of subscription IDs to scan")
    print()
    print("Optional:")
    print("  SCANNER_RESOURCE_GROUP  Resource group name (default: datadog-agentless-scanner)")
    print("  TF_STATE_STORAGE_ACCOUNT Custom Azure Storage Account for Terraform state")
    print()
    print("Example:")
    print("  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\")
    print("  WORKFLOW_ID=<uuid-from-datadog-ui> \\")
    print("  SCANNER_SUBSCRIPTION=<subscription-id> SCANNER_LOCATIONS=eastus \\")
    print("  SUBSCRIPTIONS_TO_SCAN=sub1,sub2 \\")
    print("  python azure_agentless_setup.pyz deploy")
    print()


def sigint_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Setup interrupted by user (Ctrl+C)")
    print("   Partial resources may have been created.")
    print("   To clean up, run: terraform destroy")
    sys.exit(130)


def session_timeout_handler() -> None:
    """Handle session timeout."""
    print("\n\n⚠️  Session expired after 30 minutes.")
    print("   If you still wish to complete the setup, re-run the command.")
    print("   Terraform state is persisted, so it will continue where it left off.")
    os._exit(1)


def start_session_timer() -> threading.Timer:
    """Start a background timer for session timeout."""
    timer = threading.Timer(SESSION_TIMEOUT_MINUTES * 60, session_timeout_handler)
    timer.daemon = True
    timer.start()
    return timer


def print_session_warning() -> None:
    """Print Cloud Shell session timeout warning."""
    print()
    print(f"⚠️  Note: This session will timeout after {SESSION_TIMEOUT_MINUTES} minutes.")
    print("   If your session expires, generate a new workflow ID from the Datadog UI")
    print("   and re-run the command. Terraform state is persisted, so it will")
    print("   continue where it left off.")


def validate_credentials_and_workflow(config, reporter: Reporter) -> None:
    """Validate Datadog credentials and workflow ID before starting setup.

    Exits the process if validation fails.
    """
    try:
        validate_datadog_api_key(reporter, config.api_key, config.site)
        validate_datadog_app_key(reporter, config.api_key, config.app_key, config.site)
    except DatadogCredentialsError as e:
        reporter.error(e.message)
        if e.detail:
            print(f"   {e.detail}")
        sys.exit(1)

    if not reporter.is_valid_workflow_id():
        print(
            f"Workflow ID {config.workflow_id} has already been used. "
            "Please start a new workflow from the Datadog UI."
        )
        sys.exit(1)

    reporter.handle_login_step()


def cmd_deploy() -> None:
    """Deploy the Agentless Scanner infrastructure."""
    signal.signal(signal.SIGINT, sigint_handler)

    timer = start_session_timer()

    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - Azure Cloud Shell Setup")
    print("=" * 60)

    print_session_warning()

    try:
        config = parse_config()
        reporter = Reporter(TOTAL_STEPS, workflow_id=config.workflow_id)

        validate_credentials_and_workflow(config, reporter)

        print()
        print("Current run inputs:")
        print(f"  Datadog Site:          {config.site}")
        print(f"  Scanner Subscription:  {config.scanner_subscription}")
        print(f"  Resource Group:        {config.resource_group}")
        if len(config.locations) == 1:
            print(f"  Location:              {config.locations[0]}")
        else:
            print(f"  Locations:             {len(config.locations)}")
            for loc in config.locations:
                print(f"    - {loc}")
        if config.state_storage_account:
            print(f"  State Storage Account: {config.state_storage_account} (custom)")
        print(f"  Subscriptions to Scan: {len(config.all_subscriptions)}")
        for s in config.all_subscriptions:
            marker = " (scanner)" if s == config.scanner_subscription else ""
            print(f"    - {s}{marker}")

        # Step 1: Preflight checks
        run_preflight_checks(config, reporter)

        # Step 2: Create state storage (Storage Account + blob container)
        storage_account = ensure_state_storage(config, reporter)

        # Step 3: Store API key in Key Vault
        vault_name = get_key_vault_name(config.scanner_subscription)
        api_key_secret_id = ensure_api_key_secret(
            config_api_key=config.api_key,
            vault_name=vault_name,
            resource_group=config.resource_group,
            location=config.locations[0],
            subscription=config.scanner_subscription,
            reporter=reporter,
        )

        # Step 4-6: Terraform generate, init, apply
        # TODO: implement in next PR (terraform.py)

        reporter.complete()
        reporter.summary(config.scanner_subscription, config.locations, config.all_subscriptions)

        print()
        print("Next Steps:")
        print("  1. Go to Datadog Security → Cloud Security → Vulnerabilities")
        print("  2. Your Azure resources should appear shortly")
        print()

        timer.cancel()

    except SetupError as e:
        print()
        print(f"❌ Setup failed: {e.message}")
        if e.detail:
            print()
            for line in e.detail.strip().split("\n"):
                print(f"   {line}")
        print()
        sys.exit(1)

    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        print()
        print("If this issue persists, please contact Datadog support.")
        sys.exit(1)


def main() -> None:
    """Main entry point — parse command and dispatch."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command in ("help", "--help", "-h"):
        print_help()
        sys.exit(0)

    if command == "deploy":
        cmd_deploy()
        return

    print(f"❌ Unknown command: {command}")
    print()
    print(f"Available commands: {', '.join(COMMANDS)}")
    print("Run 'python azure_agentless_setup.pyz help' for usage information.")
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
