# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Destroy command for the Agentless Scanner Cloud Shell setup."""

import os
import signal
import sys
from pathlib import Path

from gcp_shared.gcloud import GcloudCmd, try_gcloud

from .config import Config, CONFIG_BASE_DIR, get_config_dir
from .errors import SetupError
from .secrets import API_KEY_SECRET_NAME
from .shell import run_command
from .state_bucket import get_state_bucket_name, bucket_exists
from .terraform import generate_terraform_config, generate_tfvars


def sigint_handler(signum, frame) -> None:
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Destroy interrupted by user (Ctrl+C)")
    print("   Partial resources may still exist.")
    print("   Re-run the destroy command to continue.")
    sys.exit(130)  # Standard exit code for SIGINT


def get_scanner_project() -> str:
    """Get the scanner project for destroy command.

    If SCANNER_PROJECT is set, use it.
    If not set and exactly one installation folder exists, infer from it.
    Otherwise, raise an error.
    """
    scanner_project = os.environ.get("SCANNER_PROJECT", "").strip()

    if scanner_project:
        return scanner_project

    # Try to infer from existing installations
    if not CONFIG_BASE_DIR.exists():
        raise SetupError(
            "No installation found",
            "SCANNER_PROJECT is required. No existing installations found.",
        )

    folders = [f for f in CONFIG_BASE_DIR.iterdir() if f.is_dir()]

    if len(folders) == 0:
        raise SetupError(
            "No installation found",
            "SCANNER_PROJECT is required. No existing installations found.",
        )

    if len(folders) == 1:
        inferred_project = folders[0].name
        print(f"  Inferred SCANNER_PROJECT: {inferred_project}")
        return inferred_project

    # Multiple installations - user must specify
    folder_names = [f.name for f in folders]
    raise SetupError(
        "Multiple installations found",
        f"SCANNER_PROJECT is required when multiple installations exist.\n"
        f"Found: {', '.join(folder_names)}",
    )


def get_state_bucket(scanner_project: str) -> str:
    """Determine the state bucket name from env var or default."""
    custom_bucket = os.environ.get("TF_STATE_BUCKET", "").strip()
    if custom_bucket:
        return custom_bucket
    return get_state_bucket_name(scanner_project)


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
            "\n".join(f"  - {e}" for e in errors)
            + "\n\nThese are required because the local config folder doesn't exist.",
        )

    return api_key, app_key, site


def regenerate_terraform_config(
    scanner_project: str,
    state_bucket: str,
    config_folder: Path,
) -> None:
    """Regenerate Terraform configuration when local folder doesn't exist.

    Requires DD_API_KEY, DD_APP_KEY, DD_SITE environment variables.
    """
    print("Local config not found, but Terraform state exists in bucket.")
    print("Credentials required to regenerate configuration.")
    print()

    api_key, app_key, site = get_credentials_from_env()

    print("Regenerating Terraform configuration...")
    config_folder.mkdir(parents=True, exist_ok=True)

    # Create minimal config (regions don't matter for destroy)
    minimal_config = Config(
        api_key=api_key,
        app_key=app_key,
        site=site,
        scanner_project=scanner_project,
        regions=["us-central1"],  # Doesn't matter for destroy
        projects_to_scan=[scanner_project],
    )

    # Generate config files
    api_key_secret_id = f"projects/{scanner_project}/secrets/{API_KEY_SECRET_NAME}"

    main_tf = config_folder / "main.tf"
    main_tf.write_text(
        generate_terraform_config(minimal_config, state_bucket, api_key_secret_id)
    )

    tfvars = config_folder / "terraform.tfvars"
    tfvars.write_text(generate_tfvars(minimal_config))

    print(f"Configuration written to {config_folder}")
    print()


def get_working_directory(scanner_project: str, state_bucket: str) -> Path:
    """Get the working directory for Terraform, regenerating config if needed.

    Returns:
        Path to the working directory containing main.tf.
    """
    config_folder = get_config_dir(scanner_project)
    folder_exists = config_folder.exists() and (config_folder / "main.tf").exists()

    print(f"  Scanner Project:  {scanner_project}")
    print(f"  State Bucket:     gs://{state_bucket}")
    print(f"  Config Folder:    {config_folder}")
    print(f"  Folder Exists:    {'Yes' if folder_exists else 'No'}")
    print()

    if folder_exists:
        print("Using existing configuration...")
        return config_folder

    if not bucket_exists(state_bucket):
        print(f"❌ No installation found for project: {scanner_project}")
        print()
        print("The Terraform state bucket does not exist.")
        print("If you used a custom bucket during deploy, set TF_STATE_BUCKET.")
        sys.exit(1)

    # Bucket exists but folder doesn't - regenerate config
    regenerate_terraform_config(scanner_project, state_bucket, config_folder)
    return config_folder


def run_terraform_destroy(work_dir: Path) -> None:
    """Run terraform init and destroy in the given directory.

    Raises:
        SetupError: If terraform commands fail.
    """
    original_dir = os.getcwd()
    os.chdir(work_dir)

    try:
        print("Initializing Terraform...")
        result = run_command(
            ["terraform", "init", "-input=false"],
            capture_output=False,
        )
        if not result.success:
            raise SetupError("Terraform init failed")

        print()
        print("=" * 60)
        print("  Ready to destroy resources")
        print("=" * 60)
        print()

        # Terraform destroy (without -auto-approve, user must type "yes")
        result = run_command(
            ["terraform", "destroy"],
            capture_output=False,
        )
        if not result.success:
            raise SetupError("Terraform destroy failed or was cancelled")

        print()
        print("✅ Infrastructure destroyed successfully!")
        print()
    finally:
        os.chdir(original_dir)


def delete_api_key_secret(project: str) -> bool:
    """Delete the API key secret from Secret Manager.

    Returns:
        True if deleted, False if failed.
    """
    result = try_gcloud(
        GcloudCmd("secrets", "delete")
        .arg(API_KEY_SECRET_NAME)
        .param("--project", project)
        .flag("--quiet")
    )
    return result.success


def prompt_secret_cleanup(scanner_project: str) -> None:
    """Ask user if they want to delete the API key secret."""
    print("=" * 60)
    print("  Cleanup Options")
    print("=" * 60)
    print()
    print("The API key secret in Secret Manager was NOT deleted:")
    print(f"  projects/{scanner_project}/secrets/{API_KEY_SECRET_NAME}")
    print()
    print("This secret may be used by other deployments or can be reused.")
    print()

    try:
        response = input("Do you want to delete the API key secret? (y/N): ").strip().lower()
        if response in ("y", "yes"):
            print("Deleting API key secret...")
            if delete_api_key_secret(scanner_project):
                print("✅ API key secret deleted.")
            else:
                print("⚠️  Failed to delete API key secret (it may not exist).")
        else:
            print("API key secret kept.")
    except EOFError:
        # Non-interactive mode
        print("API key secret kept (non-interactive mode).")


def print_final_notes(state_bucket: str) -> None:
    """Print final notes about resources not deleted."""
    print()
    print("=" * 60)
    print("  Notes")
    print("=" * 60)
    print()
    print("The Terraform state bucket was NOT deleted:")
    print(f"  gs://{state_bucket}")
    print()
    print("You can delete it manually if no longer needed:")
    print(f"  gcloud storage buckets delete gs://{state_bucket}")
    print()


def cmd_destroy() -> None:
    """Destroy the Agentless Scanner infrastructure."""
    signal.signal(signal.SIGINT, sigint_handler)

    print()
    print("=" * 60)
    print("  Datadog Agentless Scanner - Destroy")
    print("=" * 60)
    print()

    try:
        scanner_project = get_scanner_project()
        state_bucket = get_state_bucket(scanner_project)

        work_dir = get_working_directory(scanner_project, state_bucket)

        run_terraform_destroy(work_dir)

        prompt_secret_cleanup(scanner_project)
        print_final_notes(state_bucket)
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
