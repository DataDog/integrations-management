# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import re
import subprocess
from re import search
from time import sleep
from typing import Any, List, Optional, Type

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
AZ_VERS_TIMEOUT = 5  # seconds


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


def _get_az_version(timeout: int = AZ_VERS_TIMEOUT) -> str:
    """
    Return the raw az version JSON on success, otherwise return a failure
    string starting with "Could not retrieve 'az version': ...".
    """
    try:
        res = subprocess.run(
            ["az", "version", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if res.returncode == 0 and res.stdout:
            return res.stdout.strip()
        return f"Could not retrieve 'az version': exit {res.returncode} stdout: {res.stdout.strip()} stderr: {res.stderr.strip()}"
    except FileNotFoundError:
        return "Could not retrieve 'az version': 'az' executable not found"
    except subprocess.TimeoutExpired:
        return f"Could not retrieve 'az version': timeout after {timeout}s"
    except Exception as exc:
        return f"Could not retrieve 'az version': {exc}"


def _update_error_and_raise(
    error_type: Type[BaseException],
    az_version: str,
    exc_args: Optional[List[Any]] = None,
    msg_idx: int = 0,
    e: Optional[Exception] = None,
) -> None:
    """
    Update the error message with az version information and raise the error.
    Build a new exception and then update the error message to
    ensure a user facing message remains unchanged.
    """
    if exc_args is None:
        exc_args = []
    exc = error_type(*exc_args)
    error_message = exc_args[msg_idx] if len(exc_args) > msg_idx else ""
    updated_message = f"{error_message}\naz version:\n{az_version}"
    if len(exc_args) > msg_idx:
        exc_args[msg_idx] = updated_message
    else:
        exc_args.append(updated_message)
    exc.args = tuple(exc_args)
    if e:
        raise exc from e
    raise exc


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
                _update_error_and_raise(
                    error_type=RuntimeError,
                    az_version=_get_az_version(),
                    exc_args=[f"Command failed: {full_command}\nstdout: {result.stdout}\nstderr: {result.stderr}"],
                )
            return result.stdout
        except subprocess.CalledProcessError as e:
            stderr = str(e.stderr)
            stdout = str(e.stdout)
            az_version = _get_az_version()
            if RESOURCE_NOT_FOUND_ERROR in stderr:
                _update_error_and_raise(
                    error_type=ResourceNotFoundError,
                    az_version=az_version,
                    exc_args=[
                        f"Resource not found when executing '{full_command}'\nstdout: {stdout}\nstderr: {stderr}"
                    ],
                    e=e,
                )
            if any(text in stderr for text in AZURE_THROTTLING_ERRORS):
                if attempt < MAX_RETRIES - 1:
                    log.warning(f"Azure throttling ongoing. Retrying in {delay} seconds...")
                    sleep(delay)
                    delay *= RETRY_DELAY_MULTIPLIER
                    continue
                _update_error_and_raise(
                    error_type=RateLimitExceededError,
                    az_version=az_version,
                    exc_args=["Rate limit exceeded. Please wait a few minutes and try again."],
                    e=e,
                )
            if REFRESH_TOKEN_EXPIRED_ERROR in stderr:
                _update_error_and_raise(error_type=RefreshTokenError, az_version=az_version, exc_args=[stderr], e=e)
            if AUTH_FAILED_ERROR in stderr:
                error_message = f"Insufficient permissions to access resource when executing '{str(cmd)}'"
                error_details = check_access_error(stderr)
                if error_details:
                    error_message = f"{error_message}: {error_details}"
                _update_error_and_raise(error_type=AccessError, az_version=az_version, exc_args=[error_message], e=e)
            if POLICY_ERROR in stderr:
                error_before_and_after_code = stderr.split(f"({POLICY_ERROR}) ")
                policy_error_message = (
                    "\n".join(error_before_and_after_code[1:]) if len(error_before_and_after_code) > 1 else stderr
                )
                _update_error_and_raise(error_type=PolicyError, az_version=az_version, exc_args=[policy_error_message])
            if interactive_authn_command_matches := re.findall(
                r"Run the command below to authenticate interactively.*?:\s*((?:az [^\n]+\n?)+)",
                stderr,
                flags=re.MULTILINE,
            ):
                _update_error_and_raise(
                    error_type=InteractiveAuthenticationRequiredError,
                    az_version=az_version,
                    exc_args=[
                        [line.strip() for line in interactive_authn_command_matches[0].splitlines() if line.strip()],
                        "Interactive authentication required",
                    ],
                    msg_idx=1,
                    e=e,
                )
            if PERMISSION_REQUIRED_ERROR in stderr:
                _update_error_and_raise(
                    error_type=AccessError,
                    az_version=az_version,
                    exc_args=[f"Insufficient permissions to execute '{str(cmd)}'"],
                )
            if DISABLED_SUBSCRIPTION_ERROR in stderr:
                _update_error_and_raise(
                    error_type=DisabledSubscriptionError, az_version=az_version, exc_args=[stderr], e=e
                )
            if can_fail:
                return ""
            log.error(f"Command failed: {full_command}")
            log.error(stderr)
            _update_error_and_raise(
                error_type=RuntimeError,
                az_version=az_version,
                exc_args=[f"Command failed: {full_command}\nstdout: {stdout}\nstderr: {stderr}"],
                e=e,
            )

    raise SystemExit(1)  # unreachable


def execute_json(cmd: Cmd) -> Any:
    if result := execute(cmd):
        return json.loads(result)
