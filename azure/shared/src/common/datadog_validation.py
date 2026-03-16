# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Datadog credential validation utilities.

Uses the Datadog API to validate API keys and Application keys.
All functions raise on failure and return silently on success.
"""

import json
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError

from common.requests import request


class DatadogValidationError(Exception):
    """Base exception for Datadog validation failures."""

    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidAPIKeyError(DatadogValidationError):
    """Invalid Datadog API key or site."""

    def __init__(self, site: str):
        super().__init__(
            "Invalid Datadog API key or site",
            f"Please verify your DD_API_KEY and DD_SITE ({site}) are correct.",
        )


class APIKeyMissingRCScopeError(DatadogValidationError):
    """API key is valid but missing Remote Configuration scope."""

    def __init__(self):
        super().__init__(
            "API key missing Remote Configuration scope",
            "Please ensure your DD_API_KEY has Remote Configuration enabled.\n"
            "You can enable it in Datadog under Organization Settings > API Keys.",
        )


class InvalidAppKeyError(DatadogValidationError):
    """Invalid Datadog Application key."""

    def __init__(self):
        super().__init__(
            "Invalid Datadog Application key",
            "Please verify your DD_APP_KEY is correct and belongs to the same organization.",
        )


@dataclass
class APIKeyValidationResult:
    """Result of an API key validation."""

    valid: bool
    scopes: list[str]


def validate_api_key(api_key: str, site: str, require_rc_scope: bool = False) -> APIKeyValidationResult:
    """Validate a Datadog API key.

    Args:
        api_key: The Datadog API key to validate.
        site: The Datadog site (e.g. datadoghq.com).
        require_rc_scope: If True, also check for Remote Configuration scope.

    Returns:
        APIKeyValidationResult with validity and scopes.

    Raises:
        InvalidAPIKeyError: If the API key or site is invalid.
        APIKeyMissingRCScopeError: If require_rc_scope is True and the key lacks the scope.
    """
    try:
        response_body, status = request(
            "GET",
            f"https://api.{site}/api/v2/validate",
            headers={
                "Accept": "application/json",
                "DD-API-KEY": api_key,
            },
        )
    except (HTTPError, URLError):
        raise InvalidAPIKeyError(site)

    if status != 200:
        raise InvalidAPIKeyError(site)

    data = json.loads(response_body)
    scopes = data.get("data", {}).get("attributes", {}).get("api_key_scopes", [])

    if require_rc_scope and "remote_config_read" not in scopes:
        raise APIKeyMissingRCScopeError()

    return APIKeyValidationResult(valid=True, scopes=scopes)


def validate_app_key(api_key: str, app_key: str, site: str) -> None:
    """Validate a Datadog Application key.

    Args:
        api_key: The Datadog API key.
        app_key: The Datadog Application key to validate.
        site: The Datadog site.

    Raises:
        InvalidAppKeyError: If the Application key is invalid.
    """
    try:
        _, status = request(
            "GET",
            f"https://api.{site}/api/v2/validate_keys",
            headers={
                "Accept": "application/json",
                "DD-API-KEY": api_key,
                "DD-APPLICATION-KEY": app_key,
            },
        )
    except (HTTPError, URLError):
        raise InvalidAppKeyError()

    if status != 200:
        raise InvalidAppKeyError()


def validate_api_key_v1(api_key: str, site: str) -> bool:
    """Validate a Datadog API key using the v1 endpoint.

    Simpler validation without scope checks. Used by logging install.

    Args:
        api_key: The Datadog API key to validate.
        site: The Datadog site.

    Returns:
        True if valid.

    Raises:
        DatadogValidationError: If the key or site is invalid.
    """
    try:
        response_body, status = request(
            "GET",
            f"https://api.{site}/api/v1/validate",
            headers={
                "Accept": "application/json",
                "DD-API-KEY": api_key,
            },
        )
    except (HTTPError, URLError) as e:
        raise DatadogValidationError(
            "Failed to validate Datadog credentials",
            f"Unable to reach {site}: {e}",
        )

    if status != 200:
        raise DatadogValidationError(
            "Invalid Datadog API key or site",
            f"Please verify your DD_API_KEY and DD_SITE ({site}) are correct.",
        )

    data = json.loads(response_body)
    if not data.get("valid", False):
        raise DatadogValidationError(
            "Invalid Datadog API key",
            f"API key validation with {site} returned invalid.",
        )

    return True
