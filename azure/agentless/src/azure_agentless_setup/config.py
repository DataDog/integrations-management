# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Configuration parsing from environment variables."""

import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .errors import ConfigurationError


MAX_SCANNER_LOCATIONS = 4

CONFIG_BASE_DIR = Path.home() / ".datadog-agentless-setup"

DEFAULT_RESOURCE_GROUP = "datadog-agentless-scanner"

# Length of the install identifier embedded in resource names and local
# paths. Truncated SHA-256 hex; 12 characters matches the existing storage
# account / Key Vault name budget (24 chars, lowercase alphanumeric) and
# keeps the install_id readable in log lines without padding everything.
INSTALL_ID_LEN = 12


def parse_credentials() -> tuple[str, str, str]:
    """Read and validate Datadog credentials from environment variables.

    Returns ``(api_key, app_key, site)``.

    Used by the destroy command, which only needs credentials and not
    the full deploy-time configuration. The deploy path goes through
    :func:`parse_config` instead so it can aggregate credential errors
    with the rest of the env-var validation in a single message.

    Raises:
        ConfigurationError: If any of the three credentials is missing.
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
        raise ConfigurationError(
            "Missing credentials",
            "\n".join(f"  - {e}" for e in errors),
        )

    return api_key, app_key, site


def compute_install_id(scanner_subscription: str, resource_group: str) -> str:
    """Derive a stable per-install identifier from ``(subscription, RG)``.

    Two deploys that share both the scanner subscription and the resource
    group resolve to the same install (same Storage Account, Key Vault,
    local working dir); changing the resource group produces a different
    install. The function is deterministic — no state is needed to
    recompute the identifier on a fresh shell.
    """
    digest = hashlib.sha256(
        f"{scanner_subscription}|{resource_group}".encode()
    ).hexdigest()
    return digest[:INSTALL_ID_LEN]


def get_config_dir(scanner_subscription: str, install_id: str) -> Path:
    """Return the per-install local working directory.

    Nested under the subscription so we can keep enumerating subscriptions
    in destroy (one folder per scanner subscription) while reserving room
    for future multi-install support (one folder per install_id).
    """
    return CONFIG_BASE_DIR / scanner_subscription / install_id


@dataclass
class Config:
    """Configuration for the Azure agentless scanner setup."""

    # Datadog configuration
    api_key: str
    app_key: str
    site: str
    workflow_id: str

    # Azure configuration
    scanner_subscription: str
    locations: list[str]
    subscriptions_to_scan: list[str]
    resource_group: str

    # Optional: custom Azure Storage Account for Terraform state
    state_storage_account: Optional[str] = None

    # Whether ``SCANNER_RESOURCE_GROUP`` was set by the user. Tag-based
    # discovery uses this to decide whether to reuse a tagged RG silently
    # (env var unset → reuse) or fail with a mismatch error (env var set
    # to a different value).
    resource_group_explicit: bool = False

    @property
    def install_id(self) -> str:
        """Stable per-install identifier derived from ``(subscription, RG)``.

        Exposed as a property so callers don't have to keep the field in
        sync with ``resource_group``: ``with_resource_group`` is the only
        way the resource group changes after parsing and the new
        ``install_id`` is recomputed automatically.
        """
        return compute_install_id(self.scanner_subscription, self.resource_group)

    @property
    def all_subscriptions(self) -> list[str]:
        """All subscriptions including scanner subscription (deduplicated)."""
        subs = set(self.subscriptions_to_scan)
        subs.add(self.scanner_subscription)
        return sorted(subs)

    @property
    def other_subscriptions(self) -> list[str]:
        """Subscriptions to scan excluding the scanner subscription."""
        return [s for s in self.subscriptions_to_scan if s != self.scanner_subscription]

    @property
    def scan_scopes(self) -> list[str]:
        """Azure subscription scopes for role assignments."""
        return [f"/subscriptions/{s}" for s in self.all_subscriptions]

    def with_merged(self, locations: list[str], subscriptions_to_scan: list[str]) -> "Config":
        """Return a copy with merged locations and subscriptions."""
        return replace(
            self,
            locations=locations,
            subscriptions_to_scan=subscriptions_to_scan,
        )

    def with_resource_group(self, resource_group: str) -> "Config":
        """Return a copy targeting ``resource_group``.

        Used by tag-based RG discovery to switch to an existing tagged
        resource group when the user did not pin one with
        ``SCANNER_RESOURCE_GROUP``. ``install_id`` is recomputed
        automatically because it's a property.
        """
        return replace(self, resource_group=resource_group)


def parse_config() -> Config:
    """Parse configuration from environment variables.

    Raises:
        ConfigurationError: If required environment variables are missing.
    """
    errors = []

    api_key = os.environ.get("DD_API_KEY", "").strip()
    if not api_key:
        errors.append("DD_API_KEY is required")

    app_key = os.environ.get("DD_APP_KEY", "").strip()
    if not app_key:
        errors.append("DD_APP_KEY is required")

    site = os.environ.get("DD_SITE", "").strip()
    if not site:
        errors.append("DD_SITE is required (e.g., datadoghq.com, datadoghq.eu, us5.datadoghq.com). See https://docs.datadoghq.com/getting_started/site/")

    workflow_id = os.environ.get("WORKFLOW_ID", "").strip()
    if not workflow_id:
        errors.append("WORKFLOW_ID is required")

    scanner_subscription = os.environ.get("SCANNER_SUBSCRIPTION", "").strip()
    if not scanner_subscription:
        errors.append("SCANNER_SUBSCRIPTION is required")

    locations_str = os.environ.get("SCANNER_LOCATIONS", "").strip()
    if not locations_str:
        errors.append("SCANNER_LOCATIONS is required (e.g., eastus or eastus,westeurope)")

    subscriptions_str = os.environ.get("SUBSCRIPTIONS_TO_SCAN", "").strip()
    if not subscriptions_str:
        errors.append("SUBSCRIPTIONS_TO_SCAN is required (comma-separated list)")

    rg_env = os.environ.get("SCANNER_RESOURCE_GROUP", "").strip()
    resource_group = rg_env or DEFAULT_RESOURCE_GROUP
    resource_group_explicit = bool(rg_env)

    if errors:
        usage = """
Usage:
  DD_API_KEY=xxx DD_APP_KEY=xxx DD_SITE=datadoghq.com \\
  WORKFLOW_ID=<uuid> \\
  SCANNER_SUBSCRIPTION=<subscription-id> SCANNER_LOCATIONS=eastus \\
  SUBSCRIPTIONS_TO_SCAN=sub1,sub2,sub3 \\
  python azure_agentless_setup.pyz deploy"""

        raise ConfigurationError(
            "Missing required configuration",
            "\n".join(f"  - {e}" for e in errors) + "\n" + usage,
        )

    locations = list(dict.fromkeys(
        loc.strip() for loc in locations_str.split(",") if loc.strip()
    ))

    if not locations:
        raise ConfigurationError(
            "Invalid configuration",
            "SCANNER_LOCATIONS must contain at least one location",
        )

    if len(locations) > MAX_SCANNER_LOCATIONS:
        raise ConfigurationError(
            "Invalid configuration",
            f"SCANNER_LOCATIONS cannot exceed {MAX_SCANNER_LOCATIONS} locations (got {len(locations)})",
        )

    subscriptions_to_scan = list(dict.fromkeys(
        s.strip() for s in subscriptions_str.split(",") if s.strip()
    ))

    if not subscriptions_to_scan:
        raise ConfigurationError(
            "Invalid configuration",
            "SUBSCRIPTIONS_TO_SCAN must contain at least one subscription",
        )

    state_storage_account = os.environ.get("TF_STATE_STORAGE_ACCOUNT", "").strip() or None

    return Config(
        api_key=api_key,
        app_key=app_key,
        site=site,
        workflow_id=workflow_id,
        scanner_subscription=scanner_subscription,
        locations=locations,
        subscriptions_to_scan=subscriptions_to_scan,
        resource_group=resource_group,
        state_storage_account=state_storage_account,
        resource_group_explicit=resource_group_explicit,
    )
