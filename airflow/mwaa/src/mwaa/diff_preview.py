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
