# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Deployment metadata management in Azure Blob Storage.

Stores a config.json blob alongside the Terraform state that tracks all
deployed locations and subscriptions across runs. This enables additive
deployments: each run merges its inputs with the existing metadata so
that previous locations/subscriptions are preserved.

Uses blob ETags for compare-and-swap to prevent concurrent writes from
silently overwriting each other.
"""

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from az_shared.execute_cmd import execute
from common.shell import Cmd

from .config import Config
from .errors import MetadataError
from .state_storage import CONTAINER_NAME


METADATA_BLOB = "config.json"
METADATA_VERSION = 1
MAX_CAS_ATTEMPTS = 3
TF_STATE_BLOB = "datadog-agentless.tfstate"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeploymentMetadata:
    """Tracks the full set of deployed locations and subscriptions."""

    scanner_subscription: str
    locations: list[str]
    subscriptions_to_scan: list[str]
    created_at: str
    modified_at: str

    def to_dict(self) -> dict:
        return {
            "version": METADATA_VERSION,
            "scanner_subscription": self.scanner_subscription,
            "locations": sorted(self.locations),
            "subscriptions_to_scan": sorted(self.subscriptions_to_scan),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "DeploymentMetadata":
        return DeploymentMetadata(
            scanner_subscription=data["scanner_subscription"],
            locations=sorted(data.get("locations", [])),
            subscriptions_to_scan=sorted(data.get("subscriptions_to_scan", [])),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )


def _get_blob_etag(storage_account: str) -> Optional[str]:
    """Get the ETag of config.json, or None if it doesn't exist."""
    try:
        raw = execute(
            Cmd(["az", "storage", "blob", "show"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", METADATA_BLOB)
            .param("--auth-mode", "login")
            .param("--query", "properties.etag")
            .param("--output", "tsv"),
            can_fail=True,
        )
        etag = raw.strip().strip('"')
        return etag if etag else None
    except Exception:
        return None


def _download_metadata(storage_account: str) -> Optional[str]:
    """Download config.json content from blob storage."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        tmp_path = f.name

    try:
        execute(
            Cmd(["az", "storage", "blob", "download"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", METADATA_BLOB)
            .param("--auth-mode", "login")
            .param("--file", tmp_path)
            .flag("--no-progress"),
            can_fail=True,
        )
        content = Path(tmp_path).read_text()
        return content if content else None
    except Exception:
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _upload_metadata_cas(storage_account: str, content: str, etag: Optional[str]) -> bool:
    """Upload config.json with compare-and-swap using blob ETags.

    Args:
        storage_account: Azure Storage Account name.
        content: JSON content to upload.
        etag: Expected current ETag. None for first write (blob doesn't exist).

    Returns:
        True if the upload succeeded, False if it failed (e.g. ETag mismatch).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        cmd = (
            Cmd(["az", "storage", "blob", "upload"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", METADATA_BLOB)
            .param("--file", tmp_path)
            .param("--auth-mode", "login")
            .param("--overwrite", "true")
            .flag("--no-progress")
        )
        if etag:
            cmd = cmd.param("--if-match", etag)

        execute(cmd)
        return True
    except Exception as e:
        print(f"      Warning: metadata upload attempt failed: {e}")
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def read_metadata(storage_account: str) -> tuple[Optional[DeploymentMetadata], Optional[str]]:
    """Read deployment metadata from blob storage.

    Gets the ETag first, then downloads the content. If another process
    writes between these two calls, our ETag will be stale and the CAS
    write will safely fail.

    Returns:
        Tuple of (metadata or None, ETag or None).
    """
    etag = _get_blob_etag(storage_account)
    if etag is None:
        return None, None

    content = _download_metadata(storage_account)
    if content is None:
        return None, None

    try:
        data = json.loads(content)
        return DeploymentMetadata.from_dict(data), etag
    except (json.JSONDecodeError, KeyError) as e:
        raise MetadataError(
            "Failed to parse deployment metadata",
            f"The blob {METADATA_BLOB} in {storage_account}/{CONTAINER_NAME} is corrupt: {e}\n"
            "Delete it manually and re-run with all desired locations and subscriptions.",
        )


def write_metadata(
    storage_account: str,
    metadata: DeploymentMetadata,
    expected_etag: Optional[str],
    config: Optional[Config] = None,
) -> None:
    """Write deployment metadata with compare-and-swap.

    On ETag conflict, re-reads the remote metadata and re-merges with
    the provided config before retrying.

    Raises:
        MetadataError: If all attempts fail.
    """
    for attempt in range(MAX_CAS_ATTEMPTS):
        content = json.dumps(metadata.to_dict(), indent=2) + "\n"

        if _upload_metadata_cas(storage_account, content, expected_etag):
            return

        remote_metadata, expected_etag = read_metadata(storage_account)
        if remote_metadata is not None and config is not None:
            metadata = merge_with_config(remote_metadata, config)

    raise MetadataError(
        "Failed to write deployment metadata",
        f"Could not update {METADATA_BLOB} after {MAX_CAS_ATTEMPTS} attempts.\n"
        "Another process may be modifying the metadata concurrently.",
    )


def terraform_state_exists(storage_account: str) -> bool:
    """Check if Terraform state exists in the container."""
    try:
        result = execute(
            Cmd(["az", "storage", "blob", "show"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", TF_STATE_BLOB)
            .param("--auth-mode", "login"),
            can_fail=True,
        )
        return bool(result)
    except Exception:
        return False


def delete_metadata(storage_account: str) -> bool:
    """Delete config.json from blob storage."""
    try:
        execute(
            Cmd(["az", "storage", "blob", "delete"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", METADATA_BLOB)
            .param("--auth-mode", "login"),
            can_fail=True,
        )
        return True
    except Exception:
        return False


def merge_with_config(
    existing: Optional[DeploymentMetadata],
    config: Config,
) -> DeploymentMetadata:
    """Merge current run inputs with existing metadata.

    Locations and subscriptions are unioned (additive).
    Scanner subscription must match.
    """
    now = _utc_now_iso()

    if existing is None:
        return DeploymentMetadata(
            scanner_subscription=config.scanner_subscription,
            locations=list(config.locations),
            subscriptions_to_scan=list(config.all_subscriptions),
            created_at=now,
            modified_at=now,
        )

    if existing.scanner_subscription != config.scanner_subscription:
        raise MetadataError(
            "Scanner subscription mismatch",
            f"Existing deployment uses scanner subscription '{existing.scanner_subscription}' "
            f"but this run specifies '{config.scanner_subscription}'.\n"
            "Use the same scanner subscription or destroy the existing deployment first.",
        )

    merged_locations = sorted(set(existing.locations) | set(config.locations))
    merged_subs = sorted(set(existing.subscriptions_to_scan) | set(config.all_subscriptions))

    return DeploymentMetadata(
        scanner_subscription=config.scanner_subscription,
        locations=merged_locations,
        subscriptions_to_scan=merged_subs,
        created_at=existing.created_at,
        modified_at=now,
    )
