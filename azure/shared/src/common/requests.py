# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""HTTP request utilities for Datadog API communication."""

import json
import os
import ssl
import time
from typing import Any, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


JsonAtom = Union[str, int, bool, None]
JsonDict = dict[str, "Json"]
JsonList = list["Json"]
Json = Union[JsonDict, JsonList, JsonAtom]


def request(
    method: str,
    url: str,
    body: Optional[Json] = None,
    headers: Optional[dict[str, str]] = None,
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
        try:
            with urlopen(
                Request(url, method=method, headers=headers, data=json.dumps(body).encode("utf-8") if body else None),
                context=ssl.create_default_context(),
            ) as response:
                return response.read().decode("utf-8"), response.status
        except URLError as e:
            can_retry = attempt < max_retries - 1
            if isinstance(e, HTTPError) and e.code not in retry_status_codes:
                can_retry = False
            if can_retry:
                time.sleep(base_delay * (2**attempt))
            else:
                raise e
    raise RuntimeError(f"{method} {url}: exceeded max retries")


def dd_request(method: str, path: str, body: Optional[dict[str, Any]] = None) -> tuple[str, int]:
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
