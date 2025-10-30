#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import re
import ssl
import time
from collections.abc import Container, Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional, TypeVar, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_WORKERS = 50

T = TypeVar("T")


@dataclass
class UnionContainer(Container[T]):
    """A container comprised of other containers."""

    containers: Iterable[Container[T]]

    def __contains__(self, item: T) -> bool:
        return any(item in container for container in self.containers)


JsonAtom = Union[str, int, bool, None]
JsonDict = dict[str, "Json"]
JsonList = list["Json"]
Json = Union[JsonDict, JsonList, JsonAtom]


@lru_cache(maxsize=256)
def compile_wildcard(pattern: str) -> re.Pattern:
    """Convert a wildcard expression into a regular expression."""
    return re.compile("^{}$".format(re.escape(pattern).replace(r"\*", ".*")))


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
    # We should never hit this.
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
