#!/usr/bin/env python3

import argparse
import logging
import sys
from logging import basicConfig, getLogger

from .az_cmd import list_users_subscriptions, set_subscription
from .configuration import Configuration
from .deploy import deploy_control_plane, run_initial_deploy
from .resource_setup import create_resource_group
from .role_setup import grant_permissions
from .validation import check_fresh_install, validate_user_parameters, validate_az_cli


log = getLogger("installer")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Azure Log Forwarding Orchestration Installation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required parameters
    parser.add_argument(
        "-mg",
        "--management-group",
        type=str,
        required=True,
        help="Management group ID to deploy under (required)",
    )

    parser.add_argument(
        "--control-plane-region",
        type=str,
        required=True,
        help="Azure region for the control plane (e.g., eastus, westus2) (required)",
    )

    parser.add_argument(
        "--control-plane-subscription",
        type=str,
        required=True,
        help="Subscription ID where the control plane will be deployed (required)",
    )

    parser.add_argument(
        "--control-plane-resource-group",
        type=str,
        required=True,
        help="Resource group name for the control plane (required)",
    )

    parser.add_argument(
        "--monitored-subscriptions",
        type=str,
        required=True,
        help="Comma-separated list of subscription IDs to monitor for log forwarding (required)",
    )

    parser.add_argument(
        "--datadog-api-key", type=str, required=True, help="Datadog API key (required)"
    )

    parser.add_argument(
        "--datadog-site",
        type=str,
        choices=[
            "datadoghq.com",
            "datadoghq.eu",
            "ap1.datadoghq.com",
            "ap2.datadoghq.com",
            "us3.datadoghq.com",
            "us5.datadoghq.com",
            "ddog-gov.com",
        ],
        default="datadoghq.com",
        help="Datadog site (default: datadoghq.com)",
    )

    # Optional parameters
    parser.add_argument(
        "--resource-tag-filters",
        type=str,
        default="",
        help="Comma separated list of tags to filter resources by",
    )

    parser.add_argument(
        "--pii-scrubber-rules",
        type=str,
        default="",
        help="YAML formatted list of PII Scrubber Rules",
    )

    parser.add_argument(
        "--datadog-telemetry", action="store_true", help="Enable Datadog telemetry"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the log level (default: INFO)",
    )

    return parser.parse_args()


def log_header(message: str):
    """Log a formatted header message."""
    separator = "=" * 70
    header = "\n".join(["", separator, message, separator, ""])
    log.info(header)


def main():
    """Main installation flow that orchestrates all steps."""

    try:
        args = parse_arguments()
        config = Configuration(
            management_group_id=args.management_group,
            control_plane_region=args.control_plane_region,
            control_plane_sub_id=args.control_plane_subscription,
            control_plane_rg=args.control_plane_resource_group,
            monitored_subs=args.monitored_subscriptions,
            datadog_api_key=args.datadog_api_key,
            datadog_site=args.datadog_site,
            resource_tag_filters=args.resource_tag_filters,
            pii_scrubber_rules=args.pii_scrubber_rules,
            datadog_telemetry=args.datadog_telemetry,
            log_level=args.log_level,
        )

        basicConfig(level=getattr(logging, config.log_level))

        log.info("Starting setup for Azure Automated Log Forwarding...")

        log_header("STEP 1: Validating user configuration...")
        validate_az_cli()
        validate_user_parameters(config)
        sub_id_to_name = list_users_subscriptions()
        existing_lfos = check_fresh_install(config, sub_id_to_name)

        if existing_lfos:
            # TODO AZINTS-3894: Report state of azure env to front end
            log.info("Continue? (y/n)")
            if input() != "y":
                log.info("Exiting...")
                sys.exit(0)

        log.info("Validation completed")

        log_header("STEP 2: Creating control plane resource group...")
        set_subscription(config.control_plane_sub_id)
        create_resource_group(config.control_plane_rg, config.control_plane_region)
        log.info("Control plane resource group created")

        log_header("STEP 3: Deploying control plane infrastructure...")
        deploy_control_plane(config)

        log_header("STEP 4: Setting up subscription permissions...")
        grant_permissions(config)
        log.info("Subscription and resource group permissions configured")

        log_header("STEP 5: Triggering initial deploy...")
        run_initial_deploy(
            config.deployer_job_name,
            config.control_plane_rg,
            config.control_plane_sub_id,
        )
        log.info("Initial deployment triggered")

        log_header("Success! Azure Automated Log Forwarding installation completed!")

    except Exception as e:
        log.error(f"Failed with error: {e}")
        log.error("Check the Azure CLI output for more details")
        raise


if __name__ == "__main__":
    main()
