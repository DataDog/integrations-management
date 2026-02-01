# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Main entry point for the Agentless Scanner Cloud Shell setup."""

import os
import signal
import sys
import threading

from .config import parse_config
from .destroy import cmd_destroy
from .errors import DatadogCredentialsError, SetupError
from .preflight import run_preflight_checks, validate_datadog_api_key, validate_datadog_app_key
from .reporter import Reporter, AgentlessStep
from .secrets import ensure_api_key_secret
from .state_bucket import ensure_state_bucket
from .terraform import TerraformRunner


# Total number of steps in the deploy process
TOTAL_STEPS = 6

# Session timeout in minutes (Cloud Shell times out after 20 min of inactivity,
# but we set 30 min to account for Terraform operations keeping the session alive)
SESSION_TIMEOUT_MINUTES = 30

# Available commands
COMMANDS = ["deploy", "destroy", "help"]


def print_help() -> None:
    """Print usage help."""
    print()
    print("Datadog Agentless Scanner - GCP Cloud Shell Setup")
    print()
    print("Usage:")
    print("  python gcp_agentless_setup.pyz <command>")
    print()
    print("Commands:")
    print("  deploy    Deploy the Agentless Scanner infrastructure")
    print("  destroy   Destroy the Agentless Scanner infrastructure")
    print("  help      Show this help message")
    print()
    print("=" * 60)
    print("DEPLOY - Environment Variables:")
    print("=" * 60)
    print()
    print("Required:")
    print("  DD_API_KEY        Datadog API key with Remote Configuration enabled")
    print("  DD_APP_KEY        Datadog Application key")
    print("  DD_SITE           Datadog site (e.g., datadoghq.com, datadoghq.eu)")
    print("  WORKFLOW_ID       Workflow ID from Datadog UI (UUID)")
    print("  SCANNER_PROJECT   GCP project where the scanner will be deployed")
    print("  SCANNER_REGIONS   Comma-separated list of GCP regions (max 4)")
    print("  PROJECTS_TO_SCAN  Comma-separated list of GCP projects to scan")
    print()
    print("Optional:")
    print("  TF_STATE_BUCKET   Custom GCS bucket for Terraform state")
    print()
    print("Example:")
    print("  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\")
    print("  WORKFLOW_ID=<uuid-from-datadog-ui> \\")
    print("  SCANNER_PROJECT=my-project SCANNER_REGIONS=us-central1 \\")
    print("  PROJECTS_TO_SCAN=proj1,proj2 \\")
    print("  python gcp_agentless_setup.pyz deploy")
    print()
    print("=" * 60)
    print("DESTROY - Environment Variables:")
    print("=" * 60)
    print()
    print("Optional (inferred if only one installation exists):")
    print("  SCANNER_PROJECT   GCP project where the scanner was deployed")
    print()
    print("Required only if local config folder doesn't exist:")
    print("  DD_API_KEY        Datadog API key")
    print("  DD_APP_KEY        Datadog Application key")
    print("  DD_SITE           Datadog site")
    print("  TF_STATE_BUCKET   Custom GCS bucket (if used during deploy)")
    print()
    print("Example:")
    print("  SCANNER_PROJECT=my-project python gcp_agentless_setup.pyz destroy")
    print()


def sigint_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Setup interrupted by user (Ctrl+C)")
    print("   Partial resources may have been created.")
    print("   To clean up, run: terraform destroy")
    sys.exit(130)  # Standard exit code for SIGINT


def session_timeout_handler() -> None:
    """Handle session timeout."""
    print("\n\n⚠️  Session expired after 30 minutes.")
    print("   If you still wish to complete the setup, re-run the command.")
    print("   Terraform state is persisted, so it will continue where it left off.")
    os._exit(1)  # Force exit from timer thread


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
    # Validate Datadog API key (with RC) and Application key
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

    # Handle login step (verify GCloud auth and report to API)
    reporter.handle_login_step()


def cmd_deploy() -> None:
    """Deploy the Agentless Scanner infrastructure."""
    # Set up SIGINT handler for graceful Ctrl+C handling
    signal.signal(signal.SIGINT, sigint_handler)

    timer = start_session_timer()

    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - GCP Cloud Shell Setup")
    print("=" * 60)

    print_session_warning()

    try:
        config = parse_config()
        reporter = Reporter(TOTAL_STEPS, workflow_id=config.workflow_id)

        validate_credentials_and_workflow(config, reporter)

        # Show what we're going to do
        print()
        print("Configuration:")
        print(f"  Datadog Site:     {config.site}")
        print(f"  Scanner Project:  {config.scanner_project}")
        if len(config.regions) == 1:
            print(f"  Region:           {config.regions[0]}")
        else:
            print(f"  Regions:          {len(config.regions)}")
            for r in config.regions:
                print(f"    - {r}")
        if config.state_bucket:
            print(f"  State Bucket:     {config.state_bucket} (custom)")
        print(f"  Projects to Scan: {len(config.all_projects)}")
        for p in config.all_projects:
            marker = " (scanner)" if p == config.scanner_project else ""
            print(f"    - {p}{marker}")

        # Step 1: Preflight checks
        run_preflight_checks(config, reporter)
        reporter.finish_step()

        # Step 2: Ensure state bucket exists
        state_bucket = ensure_state_bucket(config, reporter)
        reporter.finish_step()

        # Step 3: Store API key in Secret Manager
        reporter.start_step("Storing API key in Secret Manager", AgentlessStep.STORE_API_KEY)
        api_key_secret_id = ensure_api_key_secret(
            reporter, config.scanner_project, config.api_key
        )
        reporter.finish_step()

        # Steps 4-6: Run Terraform
        tf_runner = TerraformRunner(config, state_bucket, api_key_secret_id, reporter)
        tf_runner.run()

        # Done!
        reporter.complete()
        reporter.summary(config.scanner_project, config.regions, config.all_projects)

        print()
        print("Next Steps:")
        print("  1. Go to Datadog Security → Cloud Security → Vulnerabilities")
        print("  2. Your GCP resources should appear shortly")
        print()
        print("Tip: To view only vulnerabilities detected by Agentless Scanning,")
        print('     use the filter: origin:"Agentless scanner" in the search bar.')
        print()
        print("To update or destroy this deployment, run Terraform commands in:")
        print(f"  {tf_runner.work_dir}")
        print()

        # Cancel session timer on success
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
    """Main entry point - parse command and dispatch."""
    # Get command from arguments
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "help" or command == "--help" or command == "-h":
        print_help()
        sys.exit(0)

    if command == "deploy":
        cmd_deploy()
        return

    if command == "destroy":
        cmd_destroy()
        return

    # Unknown command
    print(f"❌ Unknown command: {command}")
    print()
    print(f"Available commands: {', '.join(COMMANDS)}")
    print("Run 'python gcp_agentless_setup.pyz help' for usage information.")
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
