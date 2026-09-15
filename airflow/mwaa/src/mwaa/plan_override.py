# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Loads a hand-authored Plan from disk, bypassing compute_plan.

Escape hatch for local/dev testing: `apply` normally always computes its own
Plan from the environment's real, freshly-fetched files (see apply.py's
module docstring for why). Setting PLAN_OVERRIDE_PATH (see apply_command.py)
skips that and applies whatever Plan is in the given file instead, so you can
drive an environment into an arbitrary state -- broken or fixed -- without
first getting its real requirements.txt/constraints.txt/startup script into
that shape.

The expected JSON shape is exactly what `dataclasses.asdict(plan)` produces
(see payload.py, which prints this same shape for every environment during
`scan`) -- copy a printed plan out, edit the pin_diff/content fields, and feed
it back in unchanged.
"""

import json

from .plan import FileChange, Plan, PinDiff
from .version_table import FlaggedVersionEntry


def load_plan_override(path: str) -> Plan:
    """Read a Plan from a JSON file shaped like dataclasses.asdict(Plan(...))."""
    with open(path) as f:
        data = json.load(f)

    matched_table_entry = data.get("matched_table_entry")

    return Plan(
        upgrade_needed=data["upgrade_needed"],
        rationale=data["rationale"],
        source=data["source"],
        matched_table_entry=FlaggedVersionEntry(**matched_table_entry) if matched_table_entry else None,
        source_doc=data["source_doc"],
        file_changes=[
            FileChange(
                path=fc["path"],
                action=fc["action"],
                pin_diff=[PinDiff(**pd) for pd in fc.get("pin_diff", [])],
                content=fc.get("content"),
                notes=fc.get("notes", []),
            )
            for fc in data["file_changes"]
        ],
    )
