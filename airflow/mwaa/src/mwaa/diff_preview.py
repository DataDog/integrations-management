# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Renders a unified-diff-style preview of a file change, for humans to read.

Uses stdlib difflib rather than shelling out to `diff` -- AWS CloudShell has
`diff` but not `patch`, and this tool needs to run with nothing but python3
and boto3 available. This is display-only: nothing in this tool ever
*applies* a textual diff (see patch.py, which rewrites known pin lines
directly instead) -- unified diff format is used here purely because it's
the most familiar way to show someone what's about to change.
"""

import difflib
import re
from typing import Optional


def render_unified_diff(path: str, old_text: str, new_text: str) -> str:
    """Render a unified diff between old and new content for one file.

    Returns an empty string if the two are identical.
    """
    diff_lines = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff_lines)


# a literal value assigned to any *API_KEY variable (OPENLINEAGE_API_KEY, DD_API_KEY, ...; not
# a $variable or $(...)), and a JSON transport's apiKey/apikey/api_key value, its quotes
# backslash-escaped too when the JSON sits inside a double-quoted shell string
_KEY_EXPORT = re.compile(r"""(\b[A-Z_]*API_KEY=['"]?)([^'"\s#;$`]+)""")
_KEY_FIELD = re.compile(r"""(\\?"(?:apiKey|apikey|api_key)\\?"\s*:\s*\\?")([^"\\]*)(\\?")""")


def mask_key(key: str) -> str:
    """`****` plus the last 4 characters, the way the Datadog UI shows a key."""
    return "****" + key[-4:] if len(key) >= 8 else "****"


def mask_secrets(text: str, dd_api_key: Optional[str]) -> str:
    """`text` as safe to print: the Datadog API key masked wherever it appears.

    Covers the key this run was given, and any literal API key a startup
    script's lines carry -- a customer's old one in a diff's `-` line too.
    Display-only: what's written to S3 keeps the real key.
    """
    if dd_api_key:
        text = text.replace(dd_api_key, mask_key(dd_api_key))
    text = _KEY_EXPORT.sub(lambda m: m.group(1) + _masked(m.group(2)), text)
    return _KEY_FIELD.sub(lambda m: m.group(1) + _masked(m.group(2)) + m.group(3), text)


def _masked(value: str) -> str:
    # already masked, or the <DD_API_KEY> placeholder
    return value if value.startswith(("****", "<")) else mask_key(value)
