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
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from az_shared.execute_cmd import execute
from common.shell import Cmd

from .config import Config, compute_install_id
from .errors import MetadataError
from .state_storage import CONTAINER_NAME


METADATA_BLOB = "config.json"
METADATA_VERSION = 1
MAX_CAS_ATTEMPTS = 3
TF_STATE_BLOB = "datadog-agentless.tfstate"


class MetadataReadStatus(Enum):
    """Outcome of an attempt to read deployment metadata from blob storage.

    The MISSING / ERROR distinction matters: MISSING is the legitimate
    "first deploy" path, while ERROR (auth, network, throttling, ...) must
    not be silently treated as MISSING — that could mask an existing
    deployment and let a re-run shrink locations/subscriptions.
    """

    MISSING = "missing"
    PRESENT = "present"
    ERROR = "error"


@dataclass(frozen=True)
class MetadataReadResult:
    """Result of read_metadata().

    On PRESENT, ``metadata`` and ``etag`` are populated.
    On MISSING / ERROR, ``metadata`` is None; ``error_detail`` is set on ERROR.
    """

    status: MetadataReadStatus
    metadata: Optional["DeploymentMetadata"] = None
    etag: Optional[str] = None
    error_detail: Optional[str] = None


def rg_mismatch_detail(
    *,
    existing_rg: str,
    requested_rg: str,
    scanner_subscription: str,
) -> str:
    """Render the standard "resource group mismatch" detail message.

    Shared between deploy and destroy so users see identical guidance on
    both paths. Datadog supports a single Agentless Scanner deployment per
    scanner subscription, so the recommended remediation is to re-use the
    existing resource group; deleting and re-creating the deployment in a
    different one is only an option if the relocation is intentional.
    """
    return (
        f"An Agentless Scanner deployment already exists in scanner\n"
        f"subscription {scanner_subscription}, in resource group:\n"
        f"  - existing:  {existing_rg}\n"
        f"but this run is targeting:\n"
        f"  - requested: {requested_rg}\n"
        f"\n"
        f"Only one Agentless Scanner deployment is supported per scanner\n"
        f"subscription, and its Terraform state, Storage Account and Key\n"
        f"Vault are tied to the existing resource group.\n"
        f"\n"
        f"Recommended: re-use the existing resource group by setting:\n"
        f"  SCANNER_RESOURCE_GROUP={existing_rg}\n"
        f"(or unset SCANNER_RESOURCE_GROUP if {existing_rg} is the default).\n"
        f"Re-running `deploy` against the existing resource group will\n"
        f"additively merge any new locations or subscriptions you pass in.\n"
        f"\n"
        f"Only if you really need to relocate the deployment to a different\n"
        f"resource group: first run `destroy` against {existing_rg}, then\n"
        f"re-run `deploy` with the new SCANNER_RESOURCE_GROUP value."
    )


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
    resource_group: Optional[str] = None

    @property
    def install_id(self) -> Optional[str]:
        """Derived ``install_id`` for this deployment.

        Not stored as a field: it's a pure function of ``scanner_subscription``
        and ``resource_group``. ``to_dict`` writes it out for human
        inspection and for support workflows that grep the blob; readers
        ignore the value on disk and always recompute (this also keeps us
        safe if the on-disk value ever drifts).
        """
        if not (self.scanner_subscription and self.resource_group):
            return None
        return compute_install_id(self.scanner_subscription, self.resource_group)

    def to_dict(self) -> dict:
        return {
            "version": METADATA_VERSION,
            "install_id": self.install_id,
            "scanner_subscription": self.scanner_subscription,
            "resource_group": self.resource_group,
            "locations": sorted(self.locations),
            "subscriptions_to_scan": sorted(self.subscriptions_to_scan),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "DeploymentMetadata":
        return DeploymentMetadata(
            scanner_subscription=data["scanner_subscription"],
            resource_group=data.get("resource_group"),
            locations=sorted(data.get("locations", [])),
            subscriptions_to_scan=sorted(data.get("subscriptions_to_scan", [])),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )


_BLOB_MISSING_MARKERS = (
    "blobnotfound",
    "containernotfound",
    "the specified blob does not exist",
    "the specified container does not exist",
    "resourcenotfound",
    "the specified resource does not exist",
)


def _classify_blob_show_failure(stderr: str) -> tuple[MetadataReadStatus, Optional[str]]:
    """Map an ``az storage blob show`` failure to MISSING vs ERROR.

    Returns ``(status, error_detail)``. ``error_detail`` is populated on
    ERROR so callers can surface it to the user.
    """
    s = (stderr or "").lower()
    if any(marker in s for marker in _BLOB_MISSING_MARKERS):
        return MetadataReadStatus.MISSING, None
    detail = (stderr or "").strip() or "az storage blob show failed"
    return MetadataReadStatus.ERROR, detail


def _show_metadata_blob(storage_account: str) -> MetadataReadResult:
    """Look up the metadata blob's ETag and classify the outcome.

    Bypasses ``az_shared.execute`` so we can read stderr and distinguish
    a legitimate 404 (BlobNotFound / ContainerNotFound / ResourceNotFound)
    from auth/network/throttling failures. Treating the latter as MISSING
    would be unsafe — it could trick a re-deploy into thinking it's a
    first run and forget locations/subscriptions tracked in the existing
    blob.
    """
    cmd = str(
        Cmd(["az", "storage", "blob", "show"])
        .param("--account-name", storage_account)
        .param("--container-name", CONTAINER_NAME)
        .param("--name", METADATA_BLOB)
        .param("--auth-mode", "login")
        .param("--query", "properties.etag")
        .param("--output", "tsv")
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        etag = (result.stdout or "").strip().strip('"') or None
        return MetadataReadResult(MetadataReadStatus.PRESENT, etag=etag)

    status, detail = _classify_blob_show_failure(result.stderr or "")
    return MetadataReadResult(status, error_detail=detail)


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
        else:
            cmd = cmd.param("--if-none-match", "*")

        execute(cmd)
        return True
    except Exception as e:
        print(f"      Warning: metadata upload attempt failed: {e}")
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def read_metadata(storage_account: str) -> MetadataReadResult:
    """Read deployment metadata from blob storage.

    Gets the ETag first, then downloads the content. If another process
    writes between these two calls our ETag is stale and the CAS write
    will safely fail.

    Returns a tri-state ``MetadataReadResult``:

      * ``MISSING`` — the blob (or its container / storage account) does
        not exist; this is the typical first-deploy path.
      * ``PRESENT`` — the blob exists and was parsed; ``metadata`` and
        ``etag`` are populated.
      * ``ERROR`` — the read failed for a non-404 reason; callers must
        not silently treat this as MISSING (see ``MetadataReadStatus``).
    """
    show = _show_metadata_blob(storage_account)
    if show.status != MetadataReadStatus.PRESENT:
        return show

    content = _download_metadata(storage_account)
    if content is None:
        # ETag fetch worked, content download didn't: classify as ERROR so
        # the caller doesn't proceed as "first deploy".
        return MetadataReadResult(
            MetadataReadStatus.ERROR,
            etag=show.etag,
            error_detail=f"failed to download {METADATA_BLOB} from {storage_account}/{CONTAINER_NAME}",
        )

    try:
        data = json.loads(content)
        return MetadataReadResult(
            MetadataReadStatus.PRESENT,
            metadata=DeploymentMetadata.from_dict(data),
            etag=show.etag,
        )
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

        remote = read_metadata(storage_account)
        expected_etag = remote.etag
        if remote.status == MetadataReadStatus.PRESENT and remote.metadata is not None and config is not None:
            metadata = merge_with_config(remote.metadata, config)

    raise MetadataError(
        "Failed to write deployment metadata",
        f"Could not update {METADATA_BLOB} after {MAX_CAS_ATTEMPTS} attempts.\n"
        "Another process may be modifying the metadata concurrently.",
    )


def terraform_state_exists(storage_account: str) -> bool:
    """Check whether the Terraform state blob exists.

    Distinguishes a genuine 404 (BlobNotFound / ContainerNotFound /
    ResourceNotFound) from auth / network / throttling failures by
    reading stderr directly, mirroring :func:`_show_metadata_blob`. The
    previous implementation swallowed every failure and returned
    ``False``, which on the destroy path turned a missing Storage Blob
    Data Contributor role into the misleading "No Terraform state found
    in storage account" message. Raises :class:`MetadataError` on
    non-404 failures so the caller surfaces the real problem.
    """
    cmd = str(
        Cmd(["az", "storage", "blob", "show"])
        .param("--account-name", storage_account)
        .param("--container-name", CONTAINER_NAME)
        .param("--name", TF_STATE_BLOB)
        .param("--auth-mode", "login")
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return True

    status, detail = _classify_blob_show_failure(result.stderr or "")
    if status == MetadataReadStatus.MISSING:
        return False

    raise MetadataError(
        f"Could not check Terraform state in {storage_account}",
        f"{detail or 'unknown error'}\n"
        "If this is a permissions error, the current user needs\n"
        "'Storage Blob Data Contributor' on the storage account. The wizard\n"
        "tries to grant it automatically; if you see this message, the\n"
        "grant may have failed or not yet propagated. Re-run after a few\n"
        "seconds, or ask a subscription Owner to assign the role manually.",
    )


def delete_metadata(storage_account: str) -> bool:
    """Delete config.json from blob storage.

    Returns:
        True if deleted, False if the az CLI reported failure.
    """
    try:
        execute(
            Cmd(["az", "storage", "blob", "delete"])
            .param("--account-name", storage_account)
            .param("--container-name", CONTAINER_NAME)
            .param("--name", METADATA_BLOB)
            .param("--auth-mode", "login"),
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
            resource_group=config.resource_group,
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
        resource_group=existing.resource_group or config.resource_group,
        locations=merged_locations,
        subscriptions_to_scan=merged_subs,
        created_at=existing.created_at,
        modified_at=now,
    )
