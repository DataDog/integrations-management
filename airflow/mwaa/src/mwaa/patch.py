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

from .pins import CONSTRAINT_LINE, normalize_package_name, requirement_line_package
from .plan import EnvVarChange, PinChange, WheelReference
from .startup_script import render_export_line

_PIN_LINE_PARTS = re.compile(r"^(\s*)([A-Za-z0-9_.\-]+)\s*==\s*[A-Za-z0-9_.\-]+(.*)$")


def _render_pin(change: PinChange) -> str:
    return change.package if change.to_version is None else f"{change.package}=={change.to_version}"


def patch_pins(text: str, pin_changes: list[PinChange]) -> str:
    """Rewrite each pinned package's version line in place; append any that don't exist yet.

    Lines are matched by normalized project name (see normalize_package_name),
    so `openlineage_sql==1.3.1` is the line `openlineage-sql` replaces, rewritten
    to the canonical spelling -- and any further line pinning the same project
    is dropped, leaving exactly one.

    A `to_version` of None (see plan.py's unflagged-version path) means "just
    add the bare package name, no version" -- MWAA resolves the version itself
    from its own default constraints.
    """
    changes = {normalize_package_name(change.package): change for change in pin_changes}
    patched = set()
    lines = []
    for line in text.splitlines():
        match = _PIN_LINE_PARTS.match(line)
        name = normalize_package_name(match.group(2)) if match else None
        if name not in changes:
            lines.append(line)
        elif name not in patched:
            indent, trailing = match.group(1), match.group(3)
            lines.append(f"{indent}{_render_pin(changes[name])}{trailing}")
            patched.add(name)

    lines += [_render_pin(change) for name, change in changes.items() if name not in patched]
    return "\n".join(lines) + "\n"


def patch_wheel_references(text: str, wheel_references: list[WheelReference]) -> str:
    """Replace the line that installs each wheel's package (a pin, a bare name, another wheel)
    with the wheel's line; append it if nothing installs that package yet.

    Replacing matters: a leftover `package==1.1.0` pin next to the wheel
    would conflict with it at install time.
    """
    lines = text.splitlines()
    for ref in wheel_references:
        for i, line in enumerate(lines):
            if requirement_line_package(line) == normalize_package_name(ref.package):
                lines[i] = ref.line
                break
        else:
            lines.append(ref.line)
    return "\n".join(lines) + "\n"


def set_constraint_line(text: str, constraint_line: str) -> str:
    """Replace requirements.txt's --constraint line, or prepend one if it has none.

    Replaces rather than skips an existing line: pip honors every
    --constraint it's given, so leaving e.g. the upstream URL in place
    alongside a new line would keep enforcing the very pins being upgraded.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if CONSTRAINT_LINE.match(line):
            lines[i] = constraint_line
            return "\n".join(lines) + "\n"
    return f"{constraint_line}\n{text}"


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
