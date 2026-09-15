# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Applies a Plan's abstract pin diffs to real file text, line by line.

Runs at apply time, against freshly-fetched current content -- never against
anything captured during a scan, which may be stale by the time a plan is
reviewed and applied. Only lines that actually need to change are touched;
everything else (comments, ordering, unrelated packages) is preserved
byte-for-byte.
"""

import re

from .plan import PinDiff

_UNPINNED_PREFIX = "unpinned"
_ADDED_PINS_MARKER = "# Added by Datadog Data Observability onboarding"


def _pin_line_pattern(package: str) -> "re.Pattern[str]":
    return re.compile(rf"^(\s*){re.escape(package)}\s*==\s*[A-Za-z0-9_.\-]+(.*)$", re.IGNORECASE | re.MULTILINE)


def patch_pins(text: str, pin_diffs: list[PinDiff]) -> str:
    """Rewrite each pinned package's version line in place; append any that don't exist yet.

    A `to_version` starting with "unpinned" (see plan.py's unflagged-version
    path) means "just add the bare package name, no version" -- MWAA resolves
    the version itself from its own default constraints.
    """
    lines = text.splitlines()
    remaining = {diff.package: diff for diff in pin_diffs}

    for i, line in enumerate(lines):
        for package, diff in list(remaining.items()):
            match = _pin_line_pattern(package).match(line)
            if not match:
                continue
            indent, trailing = match.group(1), match.group(2)
            if diff.to_version.startswith(_UNPINNED_PREFIX):
                lines[i] = f"{indent}{package}{trailing}"
            else:
                lines[i] = f"{indent}{package}=={diff.to_version}{trailing}"
            del remaining[package]
            break

    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(_ADDED_PINS_MARKER)
        for package, diff in remaining.items():
            if diff.to_version.startswith(_UNPINNED_PREFIX):
                lines.append(package)
            else:
                lines.append(f"{package}=={diff.to_version}")

    return "\n".join(lines) + "\n"


def ensure_constraint_line(text: str, constraint_target: str) -> str:
    """Prepend a --constraint line if the file doesn't already have one."""
    if re.search(r"^\s*--constraint\b", text, re.MULTILINE):
        return text
    return f'--constraint "{constraint_target}"\n{text}'
