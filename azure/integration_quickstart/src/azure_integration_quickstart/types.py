#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Container, Iterable
from dataclasses import dataclass
from typing import TypeVar, Union

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
