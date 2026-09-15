# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Loads a Session from a local JSON file, bypassing session_store.py's tmp file.

Escape hatch for local/dev testing: `apply --session-id <id>` normally loads
the Session that a prior `scan --session-id <id>` persisted. Setting
SESSION_OVERRIDE_PATH swaps that lookup for a hand-authored file instead, so
you can drive an environment into an arbitrary state (broken or fixed)
without first getting a real scan into that shape.

--session-id is still required on `apply` even when this is set -- its value
is simply unused in that case, kept only for a consistent command signature.
--name/--region are unaffected either way; they're not part of what a Session
carries, so they're always supplied as flags regardless of where the Session
came from.

Expected JSON shape is exactly what `scan` persists via session_store.py
(dataclasses.asdict(session)):

    {
      "session_id": "...",
      "region": "us-east-1",
      "environments": [
        {"name": "...", "airflow_version": "...", "already_configured": false, "plan": {...}},
        ...
      ]
    }
"""

import json

from .session import Session, session_from_dict

SESSION_OVERRIDE_ENV_VAR = "SESSION_OVERRIDE_PATH"


def load_session_override(path: str) -> Session:
    """Read a Session from a JSON file shaped as this module's docstring describes."""
    with open(path) as f:
        return session_from_dict(json.load(f))
