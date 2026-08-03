# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Ensure a usable Terraform binary is available before running Terraform.

Google Cloud Shell no longer ships a real Terraform binary: `/google/bin/terraform`
is a small shell stub that prints HashiCorp install instructions and exits 0. That
means `command -v terraform` and the exit code both look fine, but `terraform init`
and `terraform apply` become silent no-ops (the deploy reports success while creating
nothing).

This module detects that case by inspecting `terraform version` output and, when the
binary on PATH is not a real Terraform, installs one into `$HOME/bin` (which persists
across Cloud Shell sessions) and places it ahead of the stub on PATH.
"""

import hashlib
import os
import platform
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from .errors import TerraformError
from .reporter import Reporter
from .shell import run_command


TERRAFORM_VERSION = os.environ.get("TERRAFORM_VERSION", "").strip() or "1.12.2"

# $HOME/bin persists across Cloud Shell sessions, unlike /usr or /google.
LOCAL_BIN_DIR = Path.home() / "bin"
TERRAFORM_BIN = LOCAL_BIN_DIR / "terraform"

_RELEASES_BASE = "https://releases.hashicorp.com/terraform"
_DOWNLOAD_TIMEOUT = 60


def _info(reporter: Optional[Reporter], message: str) -> None:
    reporter.info(message) if reporter else print(message)


def _success(reporter: Optional[Reporter], message: str) -> None:
    reporter.success(message) if reporter else print(message)


def _terraform_reports_version() -> bool:
    """Return True if the `terraform` on PATH is a real, working Terraform.

    The Cloud Shell stub exits 0, so the exit code is not a reliable signal. A
    real binary prints a line like "Terraform v1.12.2"; the stub prints HashiCorp
    install instructions instead.
    """
    try:
        result = run_command(["terraform", "version"], capture_output=True)
    except (OSError, FileNotFoundError):
        return False
    output = f"{result.stdout}\n{result.stderr}"
    return result.success and "Terraform v" in output


def _platform_slug() -> str:
    """Return the HashiCorp platform slug for the current OS/arch (e.g. linux_amd64)."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = "amd64"
    return f"linux_{arch}"


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as resp:
        if resp.status != 200:
            raise TerraformError(f"Failed to download {url} (HTTP {resp.status})")
        with open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)


def _expected_sha256(sums_url: str, zip_name: str) -> str:
    """Fetch the official SHA256SUMS file and return the digest for zip_name."""
    with urllib.request.urlopen(sums_url, timeout=_DOWNLOAD_TIMEOUT) as resp:
        sums = resp.read().decode("utf-8")
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == zip_name:
            return parts[0]
    raise TerraformError(f"Checksum for {zip_name} not found in {sums_url}")


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _install_terraform(reporter: Optional[Reporter]) -> None:
    """Download, verify, and install Terraform into $HOME/bin."""
    slug = _platform_slug()
    zip_name = f"terraform_{TERRAFORM_VERSION}_{slug}.zip"
    base = f"{_RELEASES_BASE}/{TERRAFORM_VERSION}"
    zip_url = f"{base}/{zip_name}"
    sums_url = f"{base}/terraform_{TERRAFORM_VERSION}_SHA256SUMS"

    LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / zip_name

        _info(reporter, f"Downloading Terraform {TERRAFORM_VERSION} ({slug})...")
        _download(zip_url, zip_path)

        expected = _expected_sha256(sums_url, zip_name)
        actual = _sha256_of(zip_path)
        if actual != expected:
            raise TerraformError(
                "Terraform checksum verification failed",
                f"Expected {expected}, got {actual} for {zip_name}.",
            )

        with zipfile.ZipFile(zip_path) as zf:
            zf.extract("terraform", tmp_path)

        extracted = tmp_path / "terraform"
        shutil.move(str(extracted), str(TERRAFORM_BIN))
        TERRAFORM_BIN.chmod(
            TERRAFORM_BIN.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )


def _prepend_local_bin_to_path() -> None:
    """Put $HOME/bin at the front of PATH for the current process.

    This must win over /google/bin (the stub) for subsequent `terraform` calls.
    """
    bin_str = str(LOCAL_BIN_DIR)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if parts and parts[0] == bin_str:
        return
    parts = [p for p in parts if p != bin_str]
    os.environ["PATH"] = os.pathsep.join([bin_str, *parts])


def _persist_path() -> None:
    """Persist $HOME/bin on PATH for future Cloud Shell sessions.

    The binary lives in $HOME (persistent), so only PATH ordering needs to
    survive. Prepend it in ~/.bashrc ahead of the stub. Best-effort: the current
    session already has PATH set regardless.
    """
    marker = "# Added by Datadog Agentless Scanner setup (prefer $HOME/bin terraform)"
    block = f'{marker}\nexport PATH="$HOME/bin:$PATH"\n'
    bashrc = Path.home() / ".bashrc"
    try:
        existing = bashrc.read_text() if bashrc.exists() else ""
        if marker in existing:
            return
        with open(bashrc, "a") as f:
            f.write(f"\n{block}")
    except OSError:
        pass


def ensure_terraform(reporter: Optional[Reporter] = None) -> None:
    """Ensure a usable Terraform binary is on PATH, installing one if needed.

    Args:
        reporter: Optional reporter for styled console output. Falls back to
            plain print when absent (e.g. the destroy path has no Reporter).

    Raises:
        TerraformError: If Terraform is missing and cannot be installed.
    """
    if _terraform_reports_version():
        _success(reporter, "Terraform is available")
        return

    _info(
        reporter,
        "Terraform is not usable in this environment "
        "(Cloud Shell ships a placeholder). Installing a local copy...",
    )

    try:
        _install_terraform(reporter)
    except (urllib.error.URLError, OSError, zipfile.BadZipFile, KeyError) as e:
        raise TerraformError(
            "Failed to install Terraform",
            f"{e}\n\nInstall Terraform manually and re-run the command:\n"
            "  https://developer.hashicorp.com/terraform/install",
        )

    _prepend_local_bin_to_path()
    _persist_path()

    if not _terraform_reports_version():
        raise TerraformError(
            "Terraform installation did not produce a working binary",
            f"Expected a usable terraform at {TERRAFORM_BIN}.",
        )

    _success(reporter, f"Terraform {TERRAFORM_VERSION} installed to {TERRAFORM_BIN}")
