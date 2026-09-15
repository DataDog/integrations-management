# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Redacts secret-looking values out of raw file content before it's included in a payload.

Startup scripts routinely export live credentials (Datadog API keys, database
passwords, etc.) directly as shell variables. This payload is meant to
eventually be phoned home and persisted -- and even before that, printed
locally where it could end up pasted into a ticket or a chat -- so nothing
that looks like a secret should survive into it verbatim.
"""

import re

_SECRET_MARKERS = ("API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD")
_ASSIGNMENT_LINE = re.compile(r'^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)=(.*)$', re.MULTILINE)


def _looks_like_secret_name(name: str) -> bool:
    return any(marker in name.upper() for marker in _SECRET_MARKERS)


def redact_secrets(text: "str | None") -> "str | None":
    """Replace the value of any `NAME=value` or `export NAME=value` line whose
    NAME looks like a secret with a length-preserving placeholder.
    """
    if text is None:
        return None

    def _redact_line(match: "re.Match[str]") -> str:
        prefix, name, value = match.group(1), match.group(2), match.group(3)
        if not _looks_like_secret_name(name):
            return match.group(0)
        return f"{prefix}{name}=<redacted:{len(value)} chars>"

    return _ASSIGNMENT_LINE.sub(_redact_line, text)
