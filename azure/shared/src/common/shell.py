# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import shlex
from collections.abc import Iterable
from functools import reduce


class Cmd(list[str]):
    """Builder for shell commands."""

    def append(self, token: str) -> "Cmd":
        "Adds a token to the command"
        super().append(token)
        return self

    def flag(self, key: str) -> "Cmd":
        """Adds a flag to the command"""
        return self.append(key)

    def arg(self, value: str, quote: bool = True) -> "Cmd":
        """Adds an argument value to the command"""
        return self.append(shlex.quote(value) if quote else value)

    def param(self, key: str, value: str, quote: bool = True) -> "Cmd":
        """Adds a key-value pair parameter"""
        return self.flag(key).arg(value, quote=quote)

    def param_list(self, key: str, values: Iterable[str], quote: bool = True) -> "Cmd":
        """Adds a list of parameters with the same key"""
        return reduce(lambda c, v: c.arg(v, quote=quote), values, self.flag(key))

    def __str__(self) -> str:
        return " ".join(self)
