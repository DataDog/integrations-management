# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""GCS bucket management for Terraform state."""

from .config import Config
from .errors import BucketCreationError
from .gcloud import run_command
from .reporter import Reporter


def get_state_bucket_name(scanner_project: str) -> str:
    """Generate the state bucket name for a project.

    The project name is included in the bucket name because:
    1. GCS bucket names must be globally unique across all of Google Cloud
    2. This ensures state isolation when deploying scanners to multiple projects
    """
    return f"datadog-agentless-tfstate-{scanner_project}"


def bucket_exists(bucket_name: str) -> bool:
    """Check if a GCS bucket exists."""
    result = run_command([
        "gcloud", "storage", "buckets", "describe",
        f"gs://{bucket_name}",
        "--format", "json",
    ])
    return result.success


def create_bucket(
    reporter: Reporter,
    bucket_name: str,
    project: str,
    region: str,
) -> None:
    """Create a GCS bucket for Terraform state.

    Raises:
        BucketCreationError: If the bucket cannot be created.
    """
    # Use regional location based on the scanner region
    # Map region to location (e.g., us-central1 -> US, europe-west1 -> EU)
    location = region.split("-")[0].upper()  # Simple mapping: us-central1 -> US

    result = run_command([
        "gcloud", "storage", "buckets", "create",
        f"gs://{bucket_name}",
        "--project", project,
        "--location", location,
        "--uniform-bucket-level-access",
        "--format", "json",
    ])

    if not result.success:
        raise BucketCreationError(
            f"Failed to create state bucket: {bucket_name}",
            result.stderr,
        )

    # Enable versioning for state protection
    result = run_command([
        "gcloud", "storage", "buckets", "update",
        f"gs://{bucket_name}",
        "--versioning",
        "--format", "json",
    ])

    if not result.success:
        reporter.warning(f"Could not enable versioning on {bucket_name}")


def ensure_state_bucket(config: Config, reporter: Reporter) -> str:
    """Ensure the Terraform state bucket exists.

    If config.state_bucket is set, uses that bucket (must already exist).
    Otherwise, creates a default bucket named after the scanner project.

    Raises:
        BucketCreationError: If the bucket cannot be created.

    Returns:
        The bucket name.
    """
    reporter.start_step("Setting up Terraform state storage")

    # Use custom bucket if provided, otherwise generate default name
    if config.state_bucket:
        bucket_name = config.state_bucket
        if not bucket_exists(bucket_name):
            reporter.fatal(
                f"Custom state bucket does not exist: gs://{bucket_name}",
                "Create the bucket first or remove GCP_STATE_BUCKET to use the default.",
            )
        reporter.success(f"Using custom state bucket: gs://{bucket_name}")
    else:
        bucket_name = get_state_bucket_name(config.scanner_project)
        if bucket_exists(bucket_name):
            reporter.success(f"Using existing state bucket: gs://{bucket_name}")
        else:
            reporter.info(f"Creating state bucket: gs://{bucket_name}")
            create_bucket(reporter, bucket_name, config.scanner_project, config.region)
            reporter.success(f"Created state bucket: gs://{bucket_name}")

    return bucket_name
