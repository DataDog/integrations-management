# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Destroy command for the Azure Agentless Scanner Cloud Shell setup."""

import os
import shutil
import signal
import sys
from pathlib import Path
from typing import Optional, Tuple

from .agentless_api import deactivate_scan_options
from .config import (
    CONFIG_BASE_DIR,
    Config,
    DEFAULT_RESOURCE_GROUP,
    compute_install_id,
    get_config_dir,
    parse_credentials,
)
from .errors import ConfigurationError, SetupError
from .metadata import (
    MetadataReadResult,
    MetadataReadStatus,
    delete_metadata,
    read_metadata,
    rg_mismatch_detail,
    terraform_state_exists,
)
from .secrets import (
    API_KEY_SECRET_NAME,
    get_key_vault_name,
    key_vault_exists,
    purge_key_vault,
)
from .reporter import PrintReporter
from .state_storage import (
    ensure_current_user_blob_data_access,
    find_agentless_resource_groups,
    get_storage_account_name,
    resource_group_exists,
    storage_account_exists,
)
from .terraform import generate_ssh_key, generate_terraform_config, generate_tfvars


def sigint_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Destroy interrupted by user (Ctrl+C)")
    print("   Partial resources may still exist.")
    print("   Re-run the destroy command to continue.")
    sys.exit(130)


def get_scanner_subscription() -> str:
    """Get the scanner subscription for destroy command.

    If SCANNER_SUBSCRIPTION is set, use it.
    If not set and exactly one installation folder exists, infer from it.
    Otherwise, raise an error.
    """
    scanner_subscription = os.environ.get("SCANNER_SUBSCRIPTION", "").strip()

    if scanner_subscription:
        return scanner_subscription

    if not CONFIG_BASE_DIR.exists():
        raise SetupError(
            "No installation found",
            "SCANNER_SUBSCRIPTION is required. No existing installations found.",
        )

    folders = [f for f in CONFIG_BASE_DIR.iterdir() if f.is_dir()]

    if len(folders) == 0:
        raise SetupError(
            "No installation found",
            "SCANNER_SUBSCRIPTION is required. No existing installations found.",
        )

    if len(folders) == 1:
        inferred_subscription = folders[0].name
        print(f"  Inferred SCANNER_SUBSCRIPTION: {inferred_subscription}")
        return inferred_subscription

    folder_names = [f.name for f in folders]
    raise SetupError(
        "Multiple installations found",
        f"SCANNER_SUBSCRIPTION is required when multiple installations exist.\n"
        f"Found: {', '.join(folder_names)}",
    )


def get_storage_account(install_id: str) -> str:
    """Determine the storage account name from env var or install_id."""
    custom = os.environ.get("TF_STATE_STORAGE_ACCOUNT", "").strip()
    if custom:
        return custom
    return get_storage_account_name(install_id)


def _resolve_destroy_resource_group(
    *,
    env_rg: Optional[str],
    tagged_rgs: list[str],
    scanner_subscription: str,
) -> str:
    """Resolve the resource group to use for destroy.

    With install-id-scoped resource naming, the Storage Account that
    holds the deployment metadata is itself addressable only after we
    know the resource group — so we can no longer use the metadata blob
    as the source of truth here. Tag-based discovery and
    ``SCANNER_RESOURCE_GROUP`` are now the only inputs:

      * ≥2 tagged RGs without env var → ``SetupError``. The single-install
        policy keeps us from picking one silently, and on the destroy
        path silence would be even worse than on deploy.
      * ≥2 tagged RGs with env var matching one → use it.
      * ≥2 tagged RGs with env var matching none → ``ConfigurationError``.
      * 1 tagged RG with env var disagreeing → ``ConfigurationError`` via
        the shared ``rg_mismatch_detail`` guidance.
      * 1 tagged RG, env var unset or matching → use it.
      * 0 tagged RGs → ``SCANNER_RESOURCE_GROUP`` if set, otherwise the
        default RG name (covers the "admin pre-created an untagged RG"
        edge case, in which the user must remember the env var).
    """
    if len(tagged_rgs) >= 2:
        if env_rg:
            if env_rg not in tagged_rgs:
                raise ConfigurationError(
                    "Resource group not recognised",
                    f"SCANNER_RESOURCE_GROUP={env_rg} does not match any tagged\n"
                    f"Agentless Scanner deployment in subscription {scanner_subscription}.\n"
                    f"Tagged resource groups found:\n"
                    + "\n".join(f"  - {rg}" for rg in tagged_rgs),
                )
            return env_rg
        raise SetupError(
            "Multiple Agentless Scanner deployments detected",
            f"Scanner subscription {scanner_subscription} hosts {len(tagged_rgs)} "
            f"Agentless Scanner deployments:\n"
            + "\n".join(f"  - {rg}" for rg in tagged_rgs)
            + "\nSet SCANNER_RESOURCE_GROUP to the one you want to destroy.",
        )

    if len(tagged_rgs) == 1:
        tagged = tagged_rgs[0]
        if env_rg and env_rg != tagged:
            raise ConfigurationError(
                "Resource group mismatch",
                rg_mismatch_detail(
                    existing_rg=tagged,
                    requested_rg=env_rg,
                    scanner_subscription=scanner_subscription,
                ),
            )
        return tagged

    return env_rg or DEFAULT_RESOURCE_GROUP


def regenerate_terraform_config(
    scanner_subscription: str,
    storage_account: str,
    resource_group: str,
    config_folder: Path,
    metadata_result: Optional[MetadataReadResult] = None,
) -> Path:
    """Regenerate Terraform configuration when local folder doesn't exist.

    When ``metadata_result`` is provided, reuses the caller's metadata
    read instead of issuing a second ``az storage blob show`` round-trip:
    ``cmd_destroy`` already reads the blob to recover the scan
    subscription list before deciding to call this helper, so a fresh
    read here would only duplicate work and risk inconsistency on
    transient failures. Falls back to environment variables if metadata
    is not available (the typical "user wiped local config and we have
    no blob to read" path).

    Generates a throwaway SSH key pair with :func:`terraform.generate_ssh_key` (same as
    deploy): Azure only needs a decodable public key in ``terraform.tfvars`` for refresh/destroy;
    the value need not match the key used at apply time.

    Returns:
        Path to a temp directory containing the key pair. The caller should
        :func:`shutil.rmtree` it after ``terraform destroy`` finishes.
    """
    print("Local config not found, but Terraform state exists in storage account.")

    api_key, app_key, site = parse_credentials()

    result = metadata_result if metadata_result is not None else read_metadata(storage_account)
    metadata = result.metadata if result.status == MetadataReadStatus.PRESENT else None
    if metadata:
        print(
            f"Found deployment metadata with {len(metadata.locations)} location(s) "
            f"and {len(metadata.subscriptions_to_scan)} subscription(s)."
        )
        locations = metadata.locations
        subscriptions_to_scan = metadata.subscriptions_to_scan
    else:
        if result.status == MetadataReadStatus.ERROR:
            print(
                f"⚠️  Could not read deployment metadata ({result.error_detail or 'unknown error'}); "
                "falling back to environment variables."
            )
        else:
            print("No deployment metadata found. Using environment variables.")
        locations_str = os.environ.get("SCANNER_LOCATIONS", "").strip()
        subs_str = os.environ.get("SUBSCRIPTIONS_TO_SCAN", "").strip()

        if not locations_str or not subs_str:
            raise SetupError(
                "Cannot determine deployment configuration",
                "No deployment metadata (config.json) found in the storage account.\n"
                "Please provide SCANNER_LOCATIONS and SUBSCRIPTIONS_TO_SCAN environment\n"
                "variables matching your original deployment.",
            )

        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        subscriptions_to_scan = [s.strip() for s in subs_str.split(",") if s.strip()]

    print("Regenerating Terraform configuration...")
    config_folder.mkdir(parents=True, exist_ok=True)

    config = Config(
        api_key=api_key,
        app_key=app_key,
        site=site,
        workflow_id="destroy",
        scanner_subscription=scanner_subscription,
        locations=locations,
        subscriptions_to_scan=subscriptions_to_scan,
        resource_group=resource_group,
    )

    install_id = compute_install_id(scanner_subscription, resource_group)
    vault_name = get_key_vault_name(install_id)
    api_key_secret_id = f"/subscriptions/{scanner_subscription}/resourceGroups/{resource_group}/providers/Microsoft.KeyVault/vaults/{vault_name}/secrets/{API_KEY_SECRET_NAME}"

    public_key, ssh_tmp_dir = generate_ssh_key()
    try:
        main_tf = config_folder / "main.tf"
        main_tf.write_text(
            generate_terraform_config(config, storage_account, api_key_secret_id, public_key)
        )

        tfvars = config_folder / "terraform.tfvars"
        tfvars.write_text(generate_tfvars(public_key))
    except Exception:
        shutil.rmtree(ssh_tmp_dir, ignore_errors=True)
        raise

    print(f"Configuration written to {config_folder}")
    print()
    return ssh_tmp_dir


def get_working_directory(
    scanner_subscription: str,
    storage_account: str,
    resource_group: str,
    metadata_result: Optional[MetadataReadResult] = None,
) -> Tuple[Path, Optional[Path]]:
    """Get the working directory for Terraform, regenerating config if needed.

    ``metadata_result`` is forwarded to :func:`regenerate_terraform_config`
    so the caller can pass a previously-read ``MetadataReadResult`` and
    avoid re-reading the deployment metadata blob on the regen path.

    Returns:
        ``(work_dir, ssh_key_temp_dir)``. The second item is a directory to remove
        after destroy (only set when config was regenerated and contains a
        throwaway key pair from :func:`terraform.generate_ssh_key`); otherwise
        ``None``.
    """
    install_id = compute_install_id(scanner_subscription, resource_group)
    config_folder = get_config_dir(scanner_subscription, install_id)
    folder_exists = config_folder.exists() and (config_folder / "main.tf").exists()

    print(f"  Scanner Subscription:  {scanner_subscription}")
    print(f"  Resource Group:        {resource_group}")
    print(f"  Storage Account:       {storage_account}")
    print(f"  Config Folder:         {config_folder}")
    print(f"  Folder Exists:         {'Yes' if folder_exists else 'No'}")
    print()

    if folder_exists:
        print("Using existing configuration...")
        return config_folder, None

    if not storage_account_exists(storage_account, resource_group, scanner_subscription):
        print(f"❌ No installation found for subscription: {scanner_subscription}")
        print()
        print("The Terraform state storage account does not exist.")
        print("If you used a custom storage account during deploy, set TF_STATE_STORAGE_ACCOUNT.")
        sys.exit(1)

    if not terraform_state_exists(storage_account):
        print(f"❌ No Terraform state found in storage account: {storage_account}")
        print()
        print("There is nothing to destroy.")
        sys.exit(1)

    ssh_tmp = regenerate_terraform_config(
        scanner_subscription,
        storage_account,
        resource_group,
        config_folder,
        metadata_result,
    )
    return config_folder, ssh_tmp


def run_terraform_destroy(work_dir: Path) -> None:
    """Run terraform init and destroy in the given directory.

    Raises:
        SetupError: If terraform commands fail.
    """
    import subprocess

    original_dir = os.getcwd()
    os.chdir(work_dir)

    try:
        print("Initializing Terraform...")
        result = subprocess.run(
            ["terraform", "init", "-input=false", "-reconfigure"],
            capture_output=False,
        )
        if result.returncode != 0:
            raise SetupError("Terraform init failed")

        print()
        print("=" * 60)
        print("  Ready to destroy resources")
        print("=" * 60)
        print()

        result = subprocess.run(
            ["terraform", "destroy"],
            capture_output=False,
        )
        if result.returncode != 0:
            raise SetupError("Terraform destroy failed or was cancelled")

        print()
        print("✅ Infrastructure destroyed successfully!")
        print()
    finally:
        os.chdir(original_dir)


def cleanup_key_vault(
    install_id: str, resource_group: str, subscription: str
) -> None:
    """Purge the Key Vault left behind by Terraform.

    Terraform does not manage the vault itself (the API-key secret is
    written by the wizard before any plan runs), so destroy never
    cleans it up automatically. Without a purge, Azure keeps the
    soft-deleted vault reserved for its retention window (7 days for
    wizard-created vaults) - the recurring root cause of
    ``VaultAlreadyExists`` on re-deploy.

    Always purges: ``terraform destroy`` has already confirmed the
    user's intent by the time we get here. Skips when the vault has
    already been removed.
    """
    vault_name = get_key_vault_name(install_id)

    if not key_vault_exists(vault_name, resource_group, subscription):
        print("Key Vault already removed:")
        print(f"  {vault_name}")
        print()
        return

    print(f"Purging Key Vault {vault_name}...")
    if purge_key_vault(vault_name, subscription):
        print(f"✅ Key Vault purged: {vault_name}")
    else:
        print(f"⚠️  Failed to purge Key Vault {vault_name}.")
    print()


def print_final_notes(
    storage_account: str, resource_group: str, scanner_subscription: str
) -> None:
    """Print final notes about resources that Terraform did not delete.

    The state Storage Account, Key Vault, and Resource Group are created
    by the Python wizard rather than Terraform, so ``terraform destroy``
    leaves them in place by design. When the user has already removed
    them out-of-band (typically via ``az group delete``), telling them to
    run it again would only surface a ``ResourceGroupNotFound`` error,
    so we adjust the notes to match the actual state.
    """
    print()
    rg_present = resource_group_exists(resource_group, scanner_subscription)
    sa_present = rg_present and storage_account_exists(
        storage_account, resource_group, scanner_subscription
    )

    if not rg_present:
        print("=" * 60)
        print("  Cleanup Complete")
        print("=" * 60)
        print()
        print(f"Resource group already removed: {resource_group}")
        print("No further manual cleanup needed.")
        print()
        return

    print("=" * 60)
    print("  Notes")
    print("=" * 60)
    print()
    print("The following resources were NOT deleted:")
    print()
    print(f"  Resource Group:   {resource_group}")
    if sa_present:
        print(f"  Storage Account:  {storage_account} (contains Terraform state)")
    print()
    print("You can delete the resource group manually if no longer needed:")
    print(f"  az group delete --name {resource_group} --yes --no-wait")
    print()
    print("This will also delete the storage account and any remaining resources")
    print("within the resource group.")
    print()


def cmd_destroy() -> None:
    """Destroy the Agentless Scanner infrastructure."""
    signal.signal(signal.SIGINT, sigint_handler)

    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - Destroy (Azure)")
    print("=" * 60)
    print()

    try:
        # Fail fast if Datadog credentials aren't set — they're required
        # below for scan options cleanup and for regenerate_terraform_config.
        # The returned values are re-read by the callers that actually use them.
        parse_credentials()

        scanner_subscription = get_scanner_subscription()

        # The storage account name is install-id-scoped, and the install_id
        # is derived from (scanner subscription, resource group), so the
        # resource group must be resolved first. Tag-based discovery plus
        # the env var are the only inputs — the metadata blob lives inside
        # the SA we are about to address and can no longer participate.
        env_rg = os.environ.get("SCANNER_RESOURCE_GROUP", "").strip() or None
        tagged_rgs = find_agentless_resource_groups(scanner_subscription)
        resource_group = _resolve_destroy_resource_group(
            env_rg=env_rg,
            tagged_rgs=tagged_rgs,
            scanner_subscription=scanner_subscription,
        )

        install_id = compute_install_id(scanner_subscription, resource_group)
        storage_account = get_storage_account(install_id)

        # Storage Blob Data Contributor is a *data-plane* role; Owner on
        # the resource group does not include it. Grant it to the current
        # user before the metadata read so a user destroying a deployment
        # created by someone else doesn't trip over an opaque
        # "permissions" error from `az storage blob show`. When the SA
        # does not exist (RG already nuked out-of-band, or a partial
        # deploy never created it) the metadata read is also skipped:
        # ``az storage blob show`` would DNS-fail on the missing account
        # endpoint and produce noisy stderr that ``_classify_blob_show_failure``
        # cannot recognise as a clean MISSING.
        sa_present = storage_account_exists(
            storage_account, resource_group, scanner_subscription
        )

        metadata_result: Optional[MetadataReadResult] = None
        subscriptions_to_scan: list[str] = []
        if sa_present:
            ensure_current_user_blob_data_access(
                storage_account,
                resource_group,
                scanner_subscription,
                PrintReporter(),
            )

            # Metadata is no longer authoritative for the resource group, but
            # we still read it to recover the list of scan subscriptions for
            # the Datadog-API cleanup at the end. The result is also handed
            # down to ``get_working_directory`` so the regen path doesn't
            # round-trip the same blob again.
            metadata_result = read_metadata(storage_account)
            metadata = (
                metadata_result.metadata
                if metadata_result.status == MetadataReadStatus.PRESENT
                else None
            )
            subscriptions_to_scan = metadata.subscriptions_to_scan if metadata else []

        work_dir, destroy_ssh_key_dir = get_working_directory(
            scanner_subscription,
            storage_account,
            resource_group,
            metadata_result,
        )

        try:
            run_terraform_destroy(work_dir)
        finally:
            if destroy_ssh_key_dir is not None:
                shutil.rmtree(destroy_ssh_key_dir, ignore_errors=True)

        scan_options_fully_cleaned = True
        if subscriptions_to_scan:
            scan_options_fully_cleaned = deactivate_scan_options(subscriptions_to_scan)
        else:
            print("⚠️  No subscriptions found in metadata — skipping scan options cleanup.")
            print("   You can disable them manually from the Datadog UI.")
            print()

        # Keep the metadata blob around on partial scan options failure so a
        # retry of `destroy` can still find the subscription list.
        if scan_options_fully_cleaned:
            if delete_metadata(storage_account):
                print("Deployment metadata removed.")
            else:
                print("⚠️  Could not remove deployment metadata from storage account.")
        else:
            print("⚠️  Keeping deployment metadata so you can re-run `destroy` to retry.")

        cleanup_key_vault(install_id, resource_group, scanner_subscription)
        print_final_notes(storage_account, resource_group, scanner_subscription)

    except SetupError as e:
        print()
        print(f"❌ {e.message}")
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
