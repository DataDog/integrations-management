# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Deployment metadata management in GCS.

Stores a config.json file in the Terraform state bucket that tracks
all deployed regions and projects-to-scan across runs. This enables
additive deployments: each run merges its inputs with the existing
metadata so that previous regions/projects are preserved.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config
from .errors import MetadataError


METADATA_BLOB = "config.json"
METADATA_VERSION = 1
MAX_CAS_ATTEMPTS = 3
TF_STATE_PREFIX = "agentless-scanner"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeploymentMetadata:
    """Tracks the full set of deployed regions and projects."""

    scanner_project: str
    regions: list[str]
    projects_to_scan: list[str]
    created_at: str
    modified_at: str

    def to_dict(self) -> dict:
        return {
            "version": METADATA_VERSION,
            "scanner_project": self.scanner_project,
            "regions": sorted(self.regions),
            "projects_to_scan": sorted(self.projects_to_scan),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "DeploymentMetadata":
        return DeploymentMetadata(
            scanner_project=data["scanner_project"],
            regions=sorted(data.get("regions", [])),
            projects_to_scan=sorted(data.get("projects_to_scan", [])),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )


def _gcs_uri(bucket: str) -> str:
    return f"gs://{bucket}/{METADATA_BLOB}"


def _get_object_generation(bucket: str) -> Optional[int]:
    """Get the generation number of config.json, or None if it doesn't exist."""
    result = subprocess.run(
        [
            "gcloud", "storage", "objects", "describe",
            _gcs_uri(bucket),
            "--format=value(generation)",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _download_metadata(bucket: str) -> Optional[str]:
    """Download config.json content from GCS. Returns None if it doesn't exist."""
    result = subprocess.run(
        ["gcloud", "storage", "cat", _gcs_uri(bucket)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _upload_metadata_cas(bucket: str, content: str, expected_generation: int) -> bool:
    """Upload config.json with compare-and-swap using object generation.

    Args:
        bucket: GCS bucket name.
        content: JSON content to upload.
        expected_generation: Expected current generation (0 for new object).

    Returns:
        True if the upload succeeded, False if the generation didn't match.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                "gcloud", "storage", "cp",
                tmp_path,
                _gcs_uri(bucket),
                f"--if-generation-match={expected_generation}",
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def read_metadata(bucket: str) -> tuple[Optional[DeploymentMetadata], int]:
    """Read deployment metadata from GCS.

    Returns:
        Tuple of (metadata or None if not found, generation number).
        Generation is 0 when the object doesn't exist (for CAS on first write).
    """
    content = _download_metadata(bucket)
    if content is None:
        return None, 0

    generation = _get_object_generation(bucket)
    if generation is None:
        return None, 0

    try:
        data = json.loads(content)
        return DeploymentMetadata.from_dict(data), generation
    except (json.JSONDecodeError, KeyError) as e:
        raise MetadataError(
            "Failed to parse deployment metadata",
            f"The file {_gcs_uri(bucket)} is corrupt: {e}\n"
            "Delete it manually and re-run with all desired regions and projects.",
        )


def write_metadata(
    bucket: str,
    metadata: DeploymentMetadata,
    expected_generation: int,
) -> None:
    """Write deployment metadata to GCS with compare-and-swap.

    Retries up to MAX_CAS_ATTEMPTS times on generation conflict.

    Raises:
        MetadataError: If all attempts fail.
    """
    content = json.dumps(metadata.to_dict(), indent=2) + "\n"

    for attempt in range(MAX_CAS_ATTEMPTS):
        if _upload_metadata_cas(bucket, content, expected_generation):
            return

        # Generation conflict — get the current generation
        current_generation = _get_object_generation(bucket)
        expected_generation = current_generation if current_generation is not None else 0

    raise MetadataError(
        "Failed to write deployment metadata",
        f"Could not update {_gcs_uri(bucket)} after {MAX_CAS_ATTEMPTS} attempts.\n"
        "Another process may be modifying the metadata concurrently.",
    )


def terraform_state_exists(bucket: str) -> bool:
    """Check if Terraform state exists in the bucket (under agentless-scanner prefix)."""
    result = subprocess.run(
        [
            "gcloud", "storage", "ls",
            f"gs://{bucket}/{TF_STATE_PREFIX}/",
            "--limit=1",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def delete_metadata(bucket: str) -> bool:
    """Delete config.json from GCS.

    Returns:
        True if deleted or didn't exist, False on failure.
    """
    result = subprocess.run(
        ["gcloud", "storage", "rm", _gcs_uri(bucket), "--quiet"],
        capture_output=True,
        text=True,
    )
    # Success or "not found" are both acceptable
    return result.returncode == 0 or "NotFound" in result.stderr


def merge_with_config(
    existing: Optional[DeploymentMetadata],
    config: Config,
) -> DeploymentMetadata:
    """Merge current run inputs with existing metadata.

    Regions and projects are unioned (additive). Scanner project must match.
    """
    now = _utc_now_iso()

    if existing is None:
        return DeploymentMetadata(
            scanner_project=config.scanner_project,
            regions=list(config.regions),
            projects_to_scan=list(config.all_projects),
            created_at=now,
            modified_at=now,
        )

    if existing.scanner_project != config.scanner_project:
        raise MetadataError(
            "Scanner project mismatch",
            f"Existing deployment uses scanner project '{existing.scanner_project}' "
            f"but this run specifies '{config.scanner_project}'.\n"
            "Use the same scanner project or destroy the existing deployment first.",
        )

    merged_regions = sorted(set(existing.regions) | set(config.regions))
    merged_projects = sorted(set(existing.projects_to_scan) | set(config.all_projects))

    return DeploymentMetadata(
        scanner_project=config.scanner_project,
        regions=merged_regions,
        projects_to_scan=merged_projects,
        created_at=existing.created_at,
        modified_at=now,
    )
