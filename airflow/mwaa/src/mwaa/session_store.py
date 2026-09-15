# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Persists a Session locally, keyed by session id.

Stands in for a real backend: `scan` would eventually POST a session and the
Configure Airflow UI would poll for it by session id; `apply` would fetch it
the same way. Until that exists, both sides read/write the same tmp file.
"""

import json
import os
import tempfile
from dataclasses import asdict

from .session import Session, session_from_dict


class SessionNotFoundError(Exception):
    """Raised when --session-id doesn't match a session `scan` has persisted."""


def _session_path(session_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"mwaa-session-{session_id}.json")


def save_session(session: Session) -> str:
    """Write a Session to its tmp-file path, returning that path."""
    path = _session_path(session.session_id)
    with open(path, "w") as f:
        json.dump(asdict(session), f)
    return path


def load_session(session_id: str) -> Session:
    """Read back a Session persisted by save_session.

    Raises:
        SessionNotFoundError: If no session with this id has been persisted
            (or the process wrote it to a different machine/container).
    """
    path = _session_path(session_id)
    if not os.path.exists(path):
        raise SessionNotFoundError(f"No session found for '{session_id}'. Run `scan --session-id {session_id}` first.")

    with open(path) as f:
        return session_from_dict(json.load(f))
