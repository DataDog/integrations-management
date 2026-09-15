# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Loads a PlanBundle from a local JSON file, bypassing compute_plan.

Escape hatch for local/dev testing: `apply` normally always computes its own
Plan from the environment's real, freshly-fetched files (see apply.py's
module docstring for why), and always needs --name/--region on top of that.
Setting PLAN_OVERRIDE_PATH (see apply_config.py/apply_command.py) skips both:
the file carries a whole PlanBundle -- which environment, which region, and
the plan to apply to it -- so you can drive an environment into an arbitrary
state (broken or fixed) with nothing else on the command line.

This is NOT a special case bolted onto PlanBundle -- reading one whole from
local disk is just today's one way to obtain one, alongside `apply` computing
its own. A future backend that hands back a plan for a given session id would
produce the exact same PlanBundle shape, over a different transport; that
code would belong here or beside it, not fork the concept.

Expected JSON shape:

    {
      "environment_name": "my-mwaa-environment",
      "region": "us-east-1",
      "dd_site": "datadoghq.com",   # optional, defaults to datadoghq.com
      "plan": { ... same shape as dataclasses.asdict(plan), see payload.py ... }
    }

The `plan` value is exactly what `scan` already prints per environment
(`dataclasses.asdict(plan)`) -- copy one out, nest it under `plan`, add
`environment_name`/`region`, and edit the pin_diff/content fields as needed.
"""

import json

from .plan import FileChange, Plan, PinDiff, PlanBundle
from .version_table import FlaggedVersionEntry

PLAN_OVERRIDE_ENV_VAR = "PLAN_OVERRIDE_PATH"


def _load_plan(plan_data: dict) -> Plan:
    matched_table_entry = plan_data.get("matched_table_entry")
    return Plan(
        upgrade_needed=plan_data["upgrade_needed"],
        rationale=plan_data["rationale"],
        source=plan_data["source"],
        matched_table_entry=FlaggedVersionEntry(**matched_table_entry) if matched_table_entry else None,
        source_doc=plan_data["source_doc"],
        file_changes=[
            FileChange(
                path=fc["path"],
                action=fc["action"],
                pin_diff=[PinDiff(**pd) for pd in fc.get("pin_diff", [])],
                content=fc.get("content"),
                notes=fc.get("notes", []),
            )
            for fc in plan_data["file_changes"]
        ],
    )


def load_plan_override(path: str) -> PlanBundle:
    """Read a PlanBundle from a JSON file shaped as this module's docstring describes."""
    with open(path) as f:
        data = json.load(f)

    return PlanBundle(
        environment_name=data["environment_name"],
        region=data["region"],
        dd_site=data.get("dd_site", "datadoghq.com"),
        plan=_load_plan(data["plan"]),
    )
