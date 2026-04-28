# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Datadog Agentless Scanning API client for Azure scan options.

Wraps the public ``/api/v2/agentless_scanning/accounts/azure`` endpoints used to
activate, update and deactivate scan options for Azure subscriptions.
See https://docs.datadoghq.com/api/latest/agentless-scanning/.
"""

from typing import Any
from urllib.error import HTTPError

from common.requests import dd_request


_AZURE_ACCOUNTS_PATH = "/api/v2/agentless_scanning/accounts/azure"
_RESOURCE_TYPE = "azure_scan_options"
_DEFAULT_ATTRIBUTES = {"vuln_host_os": True, "vuln_containers_os": True}

_DOCS_UI_PATH = "Security → Cloud Security → Settings → Azure"


def _format_error(e: Exception) -> str:
    """Render an exception for per-subscription console warnings.

    For ``HTTPError`` we include the response body when present (the default
    ``str(HTTPError)`` only shows the status code, e.g. ``"HTTP Error 500: 500"``,
    which hides the server-side reason).
    """
    if not isinstance(e, HTTPError):
        return str(e)
    body = ""
    try:
        raw = e.read()
        body = raw.decode("utf-8", errors="replace").strip() if raw else ""
    except Exception:
        pass
    return f"HTTP {e.code}: {body}" if body else f"HTTP {e.code}"


def _build_payload(subscription_id: str) -> dict[str, Any]:
    return {
        "data": {
            "type": _RESOURCE_TYPE,
            "id": subscription_id,
            "attributes": dict(_DEFAULT_ATTRIBUTES),
        }
    }


def _activate_one(subscription_id: str) -> None:
    """Activate scan options for a single subscription.

    Tries ``POST`` first; on ``409 Conflict`` (subscription already activated)
    falls back to ``PATCH`` so re-deploys converge on the desired attributes.
    """
    payload = _build_payload(subscription_id)
    try:
        dd_request("POST", _AZURE_ACCOUNTS_PATH, payload)
    except HTTPError as e:
        if e.code != 409:
            raise
        dd_request("PATCH", f"{_AZURE_ACCOUNTS_PATH}/{subscription_id}", payload)


def activate_scan_options(subscription_ids: list[str]) -> bool:
    """Activate Agentless scan options for each subscription via the Datadog API.

    Soft-fails: prints a warning per failing subscription and returns ``False`` if
    any failed. Successful activations are not rolled back.

    Returns:
        True iff every subscription was activated.
    """
    print(f"Activating scan options for {len(subscription_ids)} subscription(s)...")
    errors: list[str] = []
    for sub_id in subscription_ids:
        try:
            _activate_one(sub_id)
            print(f"  ✅ {sub_id}")
        except Exception as e:
            errors.append(sub_id)
            print(f"  ⚠️  {sub_id}: {_format_error(e)}")

    if errors:
        print()
        print(f"⚠️  Failed to activate scan options for {len(errors)} subscription(s).")
        print("   You can activate them manually from the Datadog UI:")
        print(f"   {_DOCS_UI_PATH}")
        print()
        return False

    print("  Scan options activated successfully.")
    print()
    return True


def deactivate_scan_options(subscription_ids: list[str]) -> bool:
    """Deactivate Agentless scan options for each subscription via the Datadog API.

    Soft-fails: prints a warning per failing subscription and returns ``False`` if
    any failed. ``404`` responses are treated as success (already absent).

    Returns:
        True iff every subscription was cleaned up (or already absent).
    """
    print(f"Disabling scan options for {len(subscription_ids)} subscription(s)...")
    errors: list[str] = []
    for sub_id in subscription_ids:
        try:
            dd_request("DELETE", f"{_AZURE_ACCOUNTS_PATH}/{sub_id}")
            print(f"  ✅ {sub_id}")
        except HTTPError as e:
            if e.code == 404:
                print(f"  ✅ {sub_id} (already deactivated)")
                continue
            errors.append(sub_id)
            print(f"  ⚠️  {sub_id}: {_format_error(e)}")
        except Exception as e:
            errors.append(sub_id)
            print(f"  ⚠️  {sub_id}: {_format_error(e)}")

    if errors:
        print()
        print(f"⚠️  Failed to disable scan options for {len(errors)} subscription(s).")
        print("   You can disable them manually from the Datadog UI:")
        print(f"   {_DOCS_UI_PATH}")
        print()
        return False

    print("  Scan options disabled successfully.")
    print()
    return True
