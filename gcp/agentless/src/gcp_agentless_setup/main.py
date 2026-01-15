# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Main entry point for the Agentless Scanner Cloud Shell setup."""

import os
import signal
import sys
import threading

from .config import parse_config
from .errors import SetupError
from .preflight import run_preflight_checks
from .reporter import Reporter
from .secrets import ensure_api_key_secret
from .state_bucket import ensure_state_bucket
from .terraform import TerraformRunner


# Total number of steps in the setup process
TOTAL_STEPS = 6

# Session timeout in minutes (Cloud Shell times out after 20 min of inactivity,
# but we set 30 min to account for Terraform operations keeping the session alive)
SESSION_TIMEOUT_MINUTES = 30


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
    print("   If your session expires during setup, simply re-run the command.")
    print("   Terraform state is persisted, so it will continue where it left off.")


def main() -> None:
    """Main entry point."""
    # Set up SIGINT handler for graceful Ctrl+C handling
    signal.signal(signal.SIGINT, sigint_handler)

    # Start session timeout timer
    timer = start_session_timer()

    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - GCP Cloud Shell Setup")
    print("=" * 60)

    # Print session timeout warning
    print_session_warning()

    try:
        # Parse configuration
        config = parse_config()

        # Initialize reporter
        reporter = Reporter(TOTAL_STEPS)

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

        # Step 2: Ensure state bucket exists
        state_bucket = ensure_state_bucket(config, reporter)

        # Step 3: Store API key in Secret Manager
        reporter.start_step("Storing API key in Secret Manager")
        api_key_secret_id = ensure_api_key_secret(
            reporter, config.scanner_project, config.api_key
        )

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


if __name__ == "__main__":
    main()
