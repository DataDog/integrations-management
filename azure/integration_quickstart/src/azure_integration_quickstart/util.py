# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import re
from collections.abc import Container, Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from common.requests import Json, JsonAtom, JsonDict, JsonList, dd_request, request  # noqa: F401

MAX_WORKERS = 50

T = TypeVar("T")


@dataclass
class UnionContainer(Container[T]):
    """A container comprised of other containers."""

    containers: Iterable[Container[T]]

    def __contains__(self, item: T) -> bool:
        return any(item in container for container in self.containers)


@lru_cache(maxsize=256)
def compile_wildcard(pattern: str) -> re.Pattern:
    """Convert a wildcard expression into a regular expression."""
    return re.compile("^{}$".format(re.escape(pattern).replace(r"\*", ".*")))
