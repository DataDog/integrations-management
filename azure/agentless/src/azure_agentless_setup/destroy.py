# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Destroy command for the Azure Agentless Scanner Cloud Shell setup."""

import os
import shutil
import signal
import sys
from pathlib import Path
from typing import Optional, Tuple

from az_shared.execute_cmd import execute
from common.shell import Cmd

from .agentless_api import deactivate_scan_options
from .config import Config, CONFIG_BASE_DIR, DEFAULT_RESOURCE_GROUP, get_config_dir
from .errors import ConfigurationError, SetupError
from .metadata import (
    DeploymentMetadata,
    MetadataReadStatus,
    delete_metadata,
    read_metadata,
    rg_mismatch_detail,
    terraform_state_exists,
)
from .secrets import API_KEY_SECRET_NAME, get_key_vault_name
from .state_storage import get_storage_account_name, storage_account_exists
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


def get_storage_account(scanner_subscription: str) -> str:
    """Determine the storage account name from env var or default."""
    custom = os.environ.get("TF_STATE_STORAGE_ACCOUNT", "").strip()
    if custom:
        return custom
    return get_storage_account_name(scanner_subscription)


def _resolve_destroy_resource_group(
    *,
    metadata: Optional[DeploymentMetadata],
    metadata_status: MetadataReadStatus,
    metadata_error_detail: Optional[str],
    env_rg: Optional[str],
    scanner_subscription: str,
) -> str:
    """Resolve the resource group to use for destroy.

    Precedence (metadata is the source of truth, env var is a fallback for
    legacy installs only):

      1. Metadata has ``resource_group`` set → use it. If ``SCANNER_RESOURCE_GROUP``
         is also set and disagrees, raise ``ConfigurationError`` rather than
         silently destroying the wrong resources (the env var override was
         the original source of the bug; treating it as a fallback eliminates
         the foot-gun without adding a new flag).
      2. Metadata exists but has no ``resource_group`` (legacy install) →
         require ``SCANNER_RESOURCE_GROUP``.
      3. No metadata at all → use ``SCANNER_RESOURCE_GROUP`` if set,
         otherwise the default.
    """
    if metadata and metadata.resource_group:
        if env_rg and env_rg != metadata.resource_group:
            raise ConfigurationError(
                "Resource group mismatch",
                rg_mismatch_detail(
                    existing_rg=metadata.resource_group,
                    requested_rg=env_rg,
                    scanner_subscription=scanner_subscription,
                ),
            )
        return metadata.resource_group

    if metadata:
        # Metadata blob exists but pre-dates the resource_group field.
        if not env_rg:
            raise SetupError(
                "Resource group required",
                "This deployment's metadata does not include the resource group "
                "(installations created before this field was added).\n"
                "Set SCANNER_RESOURCE_GROUP to the resource group used at deploy time.",
            )
        return env_rg

    if metadata_status == MetadataReadStatus.ERROR:
        print(
            f"⚠️  Could not read deployment metadata ({metadata_error_detail or 'unknown error'}); "
            "falling back to SCANNER_RESOURCE_GROUP / default."
        )

    return env_rg or DEFAULT_RESOURCE_GROUP


def get_credentials_from_env() -> tuple:
    """Get Datadog credentials from environment variables.

    Returns:
        Tuple of (api_key, app_key, site)

    Raises:
        SetupError: If any required credentials are missing.
    """
    api_key = os.environ.get("DD_API_KEY", "").strip()
    app_key = os.environ.get("DD_APP_KEY", "").strip()
    site = os.environ.get("DD_SITE", "").strip()

    errors = []
    if not api_key:
        errors.append("DD_API_KEY is required")
    if not app_key:
        errors.append("DD_APP_KEY is required")
    if not site:
        errors.append("DD_SITE is required")

    if errors:
        raise SetupError(
            "Missing credentials",
            "\n".join(f"  - {e}" for e in errors),
        )

    return api_key, app_key, site


def regenerate_terraform_config(
    scanner_subscription: str,
    storage_account: str,
    resource_group: str,
    config_folder: Path,
) -> Path:
    """Regenerate Terraform configuration when local folder doesn't exist.

    Reads deployment metadata from Azure Blob Storage to discover all
    locations and subscriptions. Falls back to requiring environment
    variables if metadata is not available.

    Generates a throwaway SSH key pair with :func:`terraform.generate_ssh_key` (same as
    deploy): Azure only needs a decodable public key in ``terraform.tfvars`` for refresh/destroy;
    the value need not match the key used at apply time.

    Returns:
        Path to a temp directory containing the key pair. The caller should
        :func:`shutil.rmtree` it after ``terraform destroy`` finishes.
    """
    print("Local config not found, but Terraform state exists in storage account.")

    api_key, app_key, site = get_credentials_from_env()

    result = read_metadata(storage_account)
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

    vault_name = get_key_vault_name(scanner_subscription)
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
) -> Tuple[Path, Optional[Path]]:
    """Get the working directory for Terraform, regenerating config if needed.

    Returns:
        ``(work_dir, ssh_key_temp_dir)``. The second item is a directory to remove
        after destroy (only set when config was regenerated and contains a
        throwaway key pair from :func:`terraform.generate_ssh_key`); otherwise
        ``None``.
    """
    config_folder = get_config_dir(scanner_subscription)
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
        scanner_subscription, storage_account, resource_group, config_folder
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


def delete_key_vault(vault_name: str) -> bool:
    """Delete the Key Vault.

    Returns:
        True if deleted, False if the az CLI reported failure.
    """
    try:
        execute(
            Cmd(["az", "keyvault", "delete"])
            .param("--name", vault_name)
            .flag("--no-wait"),
        )
        return True
    except Exception:
        return False


def prompt_key_vault_cleanup(scanner_subscription: str) -> None:
    """Ask user if they want to delete the Key Vault."""
    vault_name = get_key_vault_name(scanner_subscription)

    print("=" * 60)
    print("  Cleanup Options")
    print("=" * 60)
    print()
    print("The Key Vault was NOT deleted by Terraform:")
    print(f"  {vault_name}")
    print()
    print("This vault holds the Datadog API key and may be reused for future deployments.")
    print()

    try:
        response = input("Do you want to delete the Key Vault? (y/N): ").strip().lower()
        if response in ("y", "yes"):
            print("Deleting Key Vault...")
            if delete_key_vault(vault_name):
                print("✅ Key Vault deleted.")
                print("   Note: Azure retains soft-deleted vaults for the configured")
                print("   retention period. It will be auto-purged after that.")
            else:
                print("⚠️  Failed to delete Key Vault (it may not exist or you lack permissions).")
        else:
            print("Key Vault kept.")
    except EOFError:
        print("Key Vault kept (non-interactive mode).")


def print_final_notes(storage_account: str, resource_group: str) -> None:
    """Print final notes about resources not deleted."""
    print()
    print("=" * 60)
    print("  Notes")
    print("=" * 60)
    print()
    print("The following resources were NOT deleted:")
    print()
    print(f"  Resource Group:   {resource_group}")
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
        get_credentials_from_env()

        scanner_subscription = get_scanner_subscription()

        # Storage account name is derived from the subscription and does not
        # depend on the resource group, so we can look up metadata first and
        # then resolve the resource group with metadata as the source of truth.
        storage_account = get_storage_account(scanner_subscription)

        result = read_metadata(storage_account)
        metadata = result.metadata if result.status == MetadataReadStatus.PRESENT else None
        subscriptions_to_scan = metadata.subscriptions_to_scan if metadata else []

        env_rg = os.environ.get("SCANNER_RESOURCE_GROUP", "").strip() or None
        resource_group = _resolve_destroy_resource_group(
            metadata=metadata,
            metadata_status=result.status,
            metadata_error_detail=result.error_detail,
            env_rg=env_rg,
            scanner_subscription=scanner_subscription,
        )

        work_dir, destroy_ssh_key_dir = get_working_directory(
            scanner_subscription, storage_account, resource_group
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

        prompt_key_vault_cleanup(scanner_subscription)
        print_final_notes(storage_account, resource_group)

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
