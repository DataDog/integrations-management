# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Applies a Plan's changes to real file text, line by line.

Runs at apply time, against freshly-fetched current content -- never against
anything captured during a scan, which may be stale by the time a plan is
reviewed and applied. Only lines that actually need to change are touched;
everything else (comments, ordering, unrelated packages, unrelated startup.sh
content) is preserved byte-for-byte. That last one used to not be true --
startup.sh updates replaced the whole file -- until patch_env_vars replaced
render-the-whole-script with the same add-or-replace-in-place approach
patch_pins already used for package pins.
"""

import re

from .plan import EnvVarChange, PinChange
from .startup_script import render_export_line

_UNPINNED_PREFIX = "unpinned"


def _pin_line_pattern(package: str) -> "re.Pattern[str]":
    return re.compile(rf"^(\s*){re.escape(package)}\s*==\s*[A-Za-z0-9_.\-]+(.*)$", re.IGNORECASE | re.MULTILINE)


def patch_pins(text: str, pin_changes: list[PinChange]) -> str:
    """Rewrite each pinned package's version line in place; append any that don't exist yet.

    A `to_version` starting with "unpinned" (see plan.py's unflagged-version
    path) means "just add the bare package name, no version" -- MWAA resolves
    the version itself from its own default constraints.
    """
    lines = text.splitlines()
    remaining = {change.package: change for change in pin_changes}

    for i, line in enumerate(lines):
        for package, change in list(remaining.items()):
            match = _pin_line_pattern(package).match(line)
            if not match:
                continue
            indent, trailing = match.group(1), match.group(2)
            if change.to_version.startswith(_UNPINNED_PREFIX):
                lines[i] = f"{indent}{package}{trailing}"
            else:
                lines[i] = f"{indent}{package}=={change.to_version}{trailing}"
            del remaining[package]
            break

    if remaining:
        for package, change in remaining.items():
            if change.to_version.startswith(_UNPINNED_PREFIX):
                lines.append(package)
            else:
                lines.append(f"{package}=={change.to_version}")

    return "\n".join(lines) + "\n"


def ensure_constraint_line(text: str, constraint_target: str) -> str:
    """Prepend a --constraint line if the file doesn't already have one."""
    if re.search(r"^\s*--constraint\b", text, re.MULTILINE):
        return text
    return f'--constraint "{constraint_target}"\n{text}'


def _export_line_pattern(name: str) -> "re.Pattern[str]":
    return re.compile(rf"^\s*export\s+{re.escape(name)}=.*$", re.MULTILINE)


def patch_env_vars(text: "str | None", env_var_changes: list[EnvVarChange]) -> str:
    """Rewrite each variable's export line in place; append any that don't exist yet.

    `text` may be empty/None -- a brand-new startup.sh. change.to_value is
    written verbatim, placeholder included when the change is secret;
    apply.py's interpolate_api_key substitutes the real value afterward, the
    same way it already does for a full-file render.
    """
    lines = (text or "").splitlines()
    if not lines:
        lines = ["#!/bin/sh"]

    for change in env_var_changes:
        new_line = render_export_line(change.name, change.to_value)
        pattern = _export_line_pattern(change.name)
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)

    return "\n".join(lines) + "\n"
