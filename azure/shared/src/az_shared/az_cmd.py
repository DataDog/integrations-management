# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import re
import subprocess
from collections.abc import Iterable
from re import search
from time import sleep
from typing import Any, Optional

from common.shell import Cmd

from .errors import (
    AccessError,
    DisabledSubscriptionError,
    InteractiveAuthenticationRequiredError,
    PolicyError,
    RateLimitExceededError,
    RefreshTokenError,
    ResourceNotFoundError,
)
from .logs import log

AUTH_FAILED_ERROR = "AuthorizationFailed"
PERMISSION_REQUIRED_ERROR = "permission is needed"
AZURE_THROTTLING_ERRORS = ["TooManyRequests", "Too Many Requests", "ResourceCollectionRequestsThrottled"]
REFRESH_TOKEN_EXPIRED_ERROR = "AADSTS700082"
RESOURCE_NOT_FOUND_ERROR = "ResourceNotFound"
POLICY_ERROR = "RequestDisallowedByPolicy"
DISABLED_SUBSCRIPTION_ERROR = "DisabledSubscription"

INITIAL_RETRY_DELAY = 2  # seconds
RETRY_DELAY_MULTIPLIER = 2
MAX_RETRIES = 7


class AzCmd(Cmd):
    """Builder for Azure CLI commands."""

    def __init__(self, service: str, action: str):
        """Initialize with service and action (e.g., 'functionapp', 'create')."""
        super().__init__([service] + action.split())

    def __str__(self) -> str:
        return "az " + super().__str__()

    def param(self, key: str, value: str, quote: bool = False) -> "Cmd":
        """Adds a key-value pair parameter"""
        return super().param(key, value, quote=quote)

    def param_list(self, key: str, values: Iterable[str], quote: bool = False) -> "Cmd":
        """Adds a list of parameters with the same key"""
        return super().param_list(key, values, quote=quote)


def check_access_error(stderr: str) -> Optional[str]:
    # Sample:
    # (AuthorizationFailed) The client 'user@example.com' with object id '00000000-0000-0000-0000-000000000000'
    # does not have authorization to perform action 'Microsoft.Storage/storageAccounts/read'
    # over scope '/subscriptions/00000000-0000-0000-0000-000000000000' or the scope is invalid.
    # If access was recently granted, please refresh your credentials.

    client_match = search(r"client '([^']*)'", stderr)
    action_match = search(r"action '([^']*)'", stderr)
    scope_match = search(r"scope '([^']*)'", stderr)

    if not (action_match and scope_match and client_match):
        return

    client = client_match.group(1)
    action = action_match.group(1)
    scope = scope_match.group(1)
    return f"Insufficient permissions for {client} to perform {action} on {scope}"


def set_subscription(sub_id: str):
    """Set the active Azure subscription."""
    log.debug(f"Setting active subscription to {sub_id}")
    execute(AzCmd("account", "set").param("--subscription", sub_id))


def list_users_subscriptions() -> dict[str, str]:
    user_subs = execute(AzCmd("account", "list").param("--output", "json"))
    subs_json = json.loads(user_subs)
    return {sub["id"]: sub["name"] for sub in subs_json}


def execute(cmd: Cmd, can_fail: bool = False) -> str:
    """Run an Azure CLI command and return output or raise error."""

    full_command = str(cmd)
    log.debug(f"Running: {full_command}")
    delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(full_command, shell=True, check=True, capture_output=True, text=True)
            if result.returncode != 0 and not can_fail:
                log.error(f"Command failed: {full_command}")
                log.error(result.stderr)
                raise RuntimeError(f"Command failed: {full_command}\nstdout: {result.stdout}\nstderr: {result.stderr}")
            return result.stdout
        except subprocess.CalledProcessError as e:
            stderr = str(e.stderr)
            stdout = str(e.stdout)
            if RESOURCE_NOT_FOUND_ERROR in stderr:
                raise ResourceNotFoundError(
                    f"Resource not found when executing '{full_command}'\nstdout: {stdout}\nstderr: {stderr}"
                ) from e
            if any(text in stderr for text in AZURE_THROTTLING_ERRORS):
                if attempt < MAX_RETRIES - 1:
                    log.warning(f"Azure throttling ongoing. Retrying in {delay} seconds...")
                    sleep(delay)
                    delay *= RETRY_DELAY_MULTIPLIER
                    continue
                raise RateLimitExceededError("Rate limit exceeded. Please wait a few minutes and try again.") from e
            if REFRESH_TOKEN_EXPIRED_ERROR in stderr:
                raise RefreshTokenError(stderr) from e
            if AUTH_FAILED_ERROR in stderr:
                error_message = f"Insufficient permissions to access resource when executing '{str(cmd)}'"
                error_details = check_access_error(stderr)
                if error_details:
                    raise AccessError(f"{error_message}: {error_details}") from e
                raise AccessError(error_message) from e
            if POLICY_ERROR in stderr:
                error_before_and_after_code = stderr.split(f"({POLICY_ERROR}) ")
                policy_error_message = (
                    "\n".join(error_before_and_after_code[1:]) if len(error_before_and_after_code) > 1 else stderr
                )
                raise PolicyError(policy_error_message)
            if interactive_authn_command_matches := re.findall(
                r"Run the command below to authenticate interactively.*?:\s*((?:az [^\n]+\n?)+)",
                stderr,
                flags=re.MULTILINE,
            ):
                raise InteractiveAuthenticationRequiredError(
                    [line.strip() for line in interactive_authn_command_matches[0].splitlines() if line.strip()],
                    "Interactive authentication required",
                ) from e
            if PERMISSION_REQUIRED_ERROR in stderr:
                raise AccessError(f"Insufficient permissions to execute '{str(cmd)}'")
            if DISABLED_SUBSCRIPTION_ERROR in stderr:
                raise DisabledSubscriptionError(stderr) from e
            if can_fail:
                return ""
            log.error(f"Command failed: {full_command}")
            log.error(stderr)
            raise RuntimeError(f"Command failed: {full_command}\nstdout: {stdout}\nstderr: {stderr}") from e

    raise SystemExit(1)  # unreachable


def execute_json(cmd: Cmd) -> Any:
    if result := execute(cmd):
        return json.loads(result)
