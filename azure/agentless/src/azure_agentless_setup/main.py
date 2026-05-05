# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Main entry point for the Azure Agentless Scanner Cloud Shell setup."""

import os
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from az_shared.script_status import Status

from .agentless_api import activate_scan_options
from .config import Config, parse_config
from .destroy import cmd_destroy
from .errors import ConfigurationError, DatadogCredentialsError, SetupError
from .metadata import (
    DeploymentMetadata,
    MetadataReadResult,
    MetadataReadStatus,
    merge_with_config,
    read_metadata,
    rg_mismatch_detail,
    terraform_state_exists,
    write_metadata,
)
from .preflight import run_preflight_checks, validate_datadog_api_key, validate_datadog_app_key
from .reporter import AgentlessStep, Reporter
from .secrets import (
    get_key_vault_name,
    prepare_key_vault,
    set_or_update_secret,
    wait_for_secret_access,
)
from .state_storage import (
    ensure_resource_group,
    finalize_storage_container,
    find_storage_account_rg,
    get_storage_account_name,
    prepare_storage_account,
    wait_for_blob_access,
)
from .terraform import TerraformRunner


# Total number of steps in the deploy process:
#   1. Preflight checks
#   2. Create state storage (resource group, Storage Account, tfstate blob container)
#   3. Store API key in Key Vault
#   4. Generate Terraform configuration
#   5. Terraform init
#   6. Deploy infrastructure (Terraform apply)
#   7. Activate scan options for each subscription via the Agentless Scanning API
TOTAL_STEPS = 7

SESSION_TIMEOUT_MINUTES = 30

COMMANDS = ["deploy", "destroy", "help"]


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
    print("  destroy   Destroy the Agentless Scanner infrastructure")
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
    print("=" * 60)
    print("DESTROY - Environment Variables:")
    print("=" * 60)
    print()
    print("Required:")
    print("  DD_API_KEY              Datadog API key")
    print("  DD_APP_KEY              Datadog Application key")
    print("  DD_SITE                 Datadog site (e.g., datadoghq.com, datadoghq.eu)")
    print("  SCANNER_SUBSCRIPTION    Azure subscription where the scanner was deployed")
    print("                          (inferred if only one installation exists)")
    print()
    print("Optional:")
    print("  SCANNER_RESOURCE_GROUP      Resource group name (default: datadog-agentless-scanner)")
    print("  TF_STATE_STORAGE_ACCOUNT    Custom Azure Storage Account for Terraform state")
    print()
    print("Example:")
    print("  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\")
    print("  SCANNER_SUBSCRIPTION=<subscription-id> \\")
    print("  python azure_agentless_setup.pyz destroy")
    print()


def sigint_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Setup interrupted by user (Ctrl+C)")
    print("   Partial resources may have been created.")
    print("   To clean up, run: terraform destroy")
    sys.exit(130)


def session_timeout_handler() -> None:
    """Handle session timeout."""
    print(f"\n\n⚠️  Session expired after {SESSION_TIMEOUT_MINUTES} minutes.")
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


def _print_current_run_inputs(config: Config) -> None:
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


def _check_existing_deployment(
    config: Config,
    storage_account_name: str,
) -> MetadataReadResult:
    """Validate compatibility with any existing deployment before mutating.

    Runs *before* ``ensure_state_storage`` so we can fail fast on a
    mismatched ``SCANNER_RESOURCE_GROUP``: the deterministic Storage
    Account / Key Vault names are shared across runs but those resources
    can only live in one resource group at a time, so a mismatch would
    otherwise surface much later as a confusing ``StorageAccountAlreadyTaken``
    after we'd already created an orphaned RG.

    Returns the metadata read result so callers can reuse it for the
    additive merge instead of issuing a second blob read.
    """
    result = read_metadata(storage_account_name)

    if result.status == MetadataReadStatus.PRESENT and result.metadata is not None:
        existing_rg = result.metadata.resource_group
        if existing_rg and existing_rg != config.resource_group:
            raise ConfigurationError(
                "Resource group mismatch",
                rg_mismatch_detail(
                    existing_rg=existing_rg,
                    requested_rg=config.resource_group,
                    scanner_subscription=config.scanner_subscription,
                ),
            )
        return result

    if result.status == MetadataReadStatus.ERROR:
        raise SetupError(
            "Could not read deployment metadata",
            f"{result.error_detail or 'unknown error'}\n"
            "Fix the underlying access/network issue and re-run.\n"
            "(Proceeding could silently create duplicate resources or "
            "shrink an existing deployment.)",
        )

    # MISSING: blob (or its container/SA) does not exist for the requested
    # resource group. When using the deterministic Storage Account name,
    # also check whether that SA already lives in *another* RG of the
    # scanner subscription — that would mean the user is re-running with a
    # different SCANNER_RESOURCE_GROUP than the original deployment.
    # Skipped for the custom-SA case: ensure_state_storage already requires
    # the user-provided account to exist in `config.resource_group`.
    if config.state_storage_account is None:
        actual_rg = find_storage_account_rg(
            storage_account_name, config.scanner_subscription
        )
        if actual_rg and actual_rg != config.resource_group:
            raise ConfigurationError(
                "Resource group mismatch",
                rg_mismatch_detail(
                    existing_rg=actual_rg,
                    requested_rg=config.resource_group,
                    scanner_subscription=config.scanner_subscription,
                ),
            )

    return result


def ensure_scanner_resources(config: Config, reporter: Reporter) -> tuple[str, str]:
    """Provision the scanner-side state Storage Account and Key Vault and
    store the Datadog API key, with control-plane work parallelised across
    the two resources.

    Layout of the deploy flow this replaces (Cloud Shell, first deploy):

    * sequential:  ~12s SA create + ~30s blob RBAC propagation
    * sequential:  ~20s KV create + ~30s secret RBAC propagation
    * total:       ~90s

    With the parallel orchestrator the control-plane creates run
    concurrently and the two RBAC propagation waits overlap, cutting
    first-deploy time roughly in half. Each path emits its own progress
    messages — the lines may interleave, but they are line-buffered so
    Cloud Shell's UX stays readable.

    Reporter steps are preserved (CREATE_STATE_STORAGE, STORE_API_KEY) so
    the workflow API contract / Datadog UI percentage display is
    unchanged. The "create state storage" step is renamed to reflect
    that it now also provisions the Key Vault.

    Returns ``(storage_account_name, api_key_secret_resource_id)``.
    """
    reporter.start_step(
        "Setting up Terraform state storage and Key Vault",
        AgentlessStep.CREATE_STATE_STORAGE,
    )

    # Resource group is the parent of both the SA and the KV, so it must
    # exist before either path runs. Idempotent when the RG already exists.
    ensure_resource_group(
        config.resource_group, config.locations[0], config.scanner_subscription
    )

    vault_name = get_key_vault_name(config.scanner_subscription)

    # Run the two control-plane paths in parallel: each does its own
    # existence check + create-if-missing + role grant. Letting the SA and
    # KV existence checks overlap also covers the "parallelise existence
    # probes" optimisation.
    with ThreadPoolExecutor(max_workers=2) as executor:
        sa_future = executor.submit(prepare_storage_account, config, reporter)
        kv_future = executor.submit(
            prepare_key_vault,
            vault_name,
            config.resource_group,
            config.locations[0],
            config.scanner_subscription,
            reporter,
        )
        storage_account, sa_role_created = sa_future.result()
        kv_role_created = kv_future.result()

    # Combined RBAC propagation wait: each plane has its own retry loop,
    # but running them concurrently means the total wait is max(blob, kv)
    # rather than blob + kv. Skipped entirely when neither role was newly
    # created (re-runs by the same user on an existing deployment).
    if sa_role_created or kv_role_created:
        with ThreadPoolExecutor(max_workers=2) as executor:
            wait_futures = []
            if sa_role_created:
                wait_futures.append(
                    executor.submit(wait_for_blob_access, storage_account, reporter)
                )
            if kv_role_created:
                wait_futures.append(
                    executor.submit(wait_for_secret_access, vault_name, reporter)
                )
            for future in wait_futures:
                future.result()

    # Container creation is data-plane on the Storage Account; safe to run
    # now that the blob role has propagated.
    finalize_storage_container(storage_account, reporter)
    reporter.finish_step()

    # The secret write is the only remaining work for the API-key step;
    # the KV is already created and the role has propagated above.
    reporter.start_step("Storing API key in Key Vault", AgentlessStep.STORE_API_KEY)
    api_key_secret_id = set_or_update_secret(
        config.api_key, vault_name, config.resource_group, reporter
    )
    reporter.finish_step()

    return storage_account, api_key_secret_id


def _print_merged_deployment(
    config: Config,
    existing_metadata: Optional[DeploymentMetadata],
    merged_config: Config,
) -> None:
    if not existing_metadata:
        return

    new_locations = set(config.locations) - set(existing_metadata.locations)
    new_subs = set(config.all_subscriptions) - set(existing_metadata.subscriptions_to_scan)
    print()
    print("Merged with existing deployment:")
    print(f"  Total locations:       {len(merged_config.locations)}")
    for loc in merged_config.locations:
        marker = " (new)" if loc in new_locations else ""
        print(f"    - {loc}{marker}")
    print(f"  Total subscriptions:   {len(merged_config.all_subscriptions)}")
    for s in merged_config.all_subscriptions:
        marker = " (new)" if s in new_subs else ""
        if s == config.scanner_subscription:
            marker += " (scanner)"
        print(f"    - {s}{marker}")


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

        _print_current_run_inputs(config)

        # Step 1: Preflight checks (on current run inputs first)
        run_preflight_checks(config, reporter)

        # Resolve the storage account name now so we can read existing
        # deployment metadata *before* any mutation. The deterministic name
        # is subscription-scoped, so a previous deploy (potentially under a
        # different SCANNER_RESOURCE_GROUP) is observable from here.
        storage_account_name = (
            config.state_storage_account
            or get_storage_account_name(config.scanner_subscription)
        )
        existing_metadata_result = _check_existing_deployment(config, storage_account_name)

        # Steps 2 & 3: provision the scanner-side state Storage Account and
        # Key Vault in parallel and store the API key. See
        # ``ensure_scanner_resources`` for the parallelisation rationale.
        storage_account, api_key_secret_id = ensure_scanner_resources(config, reporter)

        existing_metadata = (
            existing_metadata_result.metadata
            if existing_metadata_result.status == MetadataReadStatus.PRESENT
            else None
        )
        metadata_etag = existing_metadata_result.etag

        if existing_metadata is None and terraform_state_exists(storage_account):
            reporter.warning(
                "Terraform state exists but no deployment metadata. "
                "Recovering metadata from current inputs."
            )
            metadata_etag = None

        merged_metadata = merge_with_config(existing_metadata, config)
        merged_config = config.with_merged(
            locations=merged_metadata.locations,
            subscriptions_to_scan=merged_metadata.subscriptions_to_scan,
        )

        _print_merged_deployment(config, existing_metadata, merged_config)

        # Steps 4-6: Run Terraform (with merged config)
        tf_runner = TerraformRunner(merged_config, storage_account, api_key_secret_id, reporter)
        tf_runner.run()

        # Write metadata only after successful apply
        write_metadata(storage_account, merged_metadata, metadata_etag, config)

        # Step 7: Activate scan options via the Agentless Scanning API. Soft-fails:
        # the infra is already deployed and metadata is persisted, so a partial
        # API failure leaves a recoverable state. We report WARN (not FAILED)
        # on partial failure so the UI surfaces it while keeping the workflow
        # ID valid for retries (is_valid_workflow_id only blocks on FAILED).
        reporter.start_step("Activating scan options", AgentlessStep.ACTIVATE_SCAN_OPTIONS)
        if activate_scan_options(merged_config.all_subscriptions):
            reporter.finish_step()
        else:
            reporter.warning(
                "Some subscriptions could not be activated. "
                "Enable them in the Datadog UI: Security → Cloud Security → Settings → Azure."
            )
            reporter.finish_step(outcome=Status.WARN)

        reporter.complete()
        reporter.summary(merged_config.scanner_subscription, merged_config.locations, merged_config.all_subscriptions)

        print()
        print("Next Steps:")
        print("  1. Go to Datadog Security → Cloud Security → Vulnerabilities")
        print("  2. Your Azure resources should appear shortly")
        print()
        print("Tip: To view only vulnerabilities detected by Agentless Scanning,")
        print('     use the filter: origin:"Agentless scanner" in the search bar.')
        print()
        print("To update or destroy this deployment, run Terraform commands in:")
        print(f"  {tf_runner.work_dir}")
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

    if command == "destroy":
        cmd_destroy()
        return

    print(f"❌ Unknown command: {command}")
    print()
    print(f"Available commands: {', '.join(COMMANDS)}")
    print("Run 'python azure_agentless_setup.pyz help' for usage information.")
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
