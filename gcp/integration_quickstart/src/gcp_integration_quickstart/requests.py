# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import ssl
import time
import urllib.request
from typing import Any, Optional
from urllib.error import HTTPError, URLError


def request(
    method: str,
    url: str,
    body: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = {},
    max_retries: int = 3,
    base_delay: float = 1.0,
    retry_status_codes: Optional[set[int]] = None,
) -> tuple[str, int]:
    """Submit a request to the given URL with the specified method and body with retry logic."""
    if headers is None:
        headers = {}
    if retry_status_codes is None:
        retry_status_codes = {500, 502, 503, 504}

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            method=method,
            headers=headers,
            data=json.dumps(body).encode("utf-8") if body else None,
        )

        try:
            with urllib.request.urlopen(
                req, context=ssl.create_default_context()
            ) as response:
                data, status = response.read().decode("utf-8"), response.status
                return data, status
        except HTTPError as e:
            data, status = e.read().decode("utf-8"), e.code
            if status in retry_status_codes:
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2**attempt))
                    continue

                raise RuntimeError(f"HTTP error {status}: {data}")

            return data, status
        except URLError as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2**attempt))
                continue

            raise RuntimeError(
                f"Network error after {max_retries} attempts: {e.reason}"
            ) from e


def dd_request(
    method: str,
    path: str,
    body: Optional[dict[str, Any]] = None,
) -> tuple[str, int]:
    """Submit a request to Datadog."""
    return request(
        method,
        f"https://api.{os.environ['DD_SITE']}{path}",
        body,
        {
            "Content-Type": "application/json",
            "DD-API-KEY": os.environ["DD_API_KEY"],
            "DD-APPLICATION-KEY": os.environ["DD_APP_KEY"],
        },
    )
