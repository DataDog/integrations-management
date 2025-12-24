# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Main entry point for the Agentless Scanner Cloud Shell setup."""

from .config import parse_config
from .errors import SetupError, UserInterruptError
from .preflight import run_preflight_checks
from .reporter import Reporter
from .state_bucket import ensure_state_bucket
from .terraform import TerraformRunner


# Total number of steps in the setup process
TOTAL_STEPS = 5


def main() -> None:
    """Main entry point."""
    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - GCP Cloud Shell Setup")
    print("=" * 60)


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
        print(f"  Region:           {config.region}")
        print(f"  Projects to Scan: {len(config.all_projects)}")
        for p in config.all_projects:
            marker = " (scanner)" if p == config.scanner_project else ""
            print(f"    - {p}{marker}")

        # Step 1: Preflight checks
        run_preflight_checks(config, reporter)

        # Step 2: Ensure state bucket exists
        state_bucket = ensure_state_bucket(config, reporter)

        # Steps 3-5: Run Terraform
        tf_runner = TerraformRunner(config, state_bucket, reporter)
        outputs = tf_runner.run()

        # Done!
        reporter.complete()
        reporter.summary(config.scanner_project, config.region, config.all_projects)

        # Print useful outputs
        if outputs:
            print()
            print("Resources Created:")
            if "scanner_service_account_email" in outputs:
                print(f"  Scanner SA: {outputs['scanner_service_account_email']}")
            if "vpc_network_name" in outputs:
                print(f"  VPC:        {outputs['vpc_network_name']}")
            if "mig_name" in outputs:
                print(f"  MIG:        {outputs['mig_name']}")

        print()
        print("Next Steps:")
        print("  1. Go to Datadog Security → Infrastructure Vulnerabilities")
        print("  2. Your GCP resources should appear shortly")
        print()
        print("To update or destroy this deployment, run Terraform commands in:")
        print(f"  {tf_runner.work_dir}")
        print()

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

