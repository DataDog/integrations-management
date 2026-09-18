# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""SessionStore: where a Session gets persisted and read back.

`scan` writes one, `apply` reads it (and re-writes it, to seal one
environment -- see session.py's seal_applied). Both commands are written
against this interface, never a concrete class, so choosing which backing
store to use (see session_store_selection.py) is a config decision, not a
branch scattered through scan.py/apply_command.py.

FilesystemSessionStore lives here since it's the simplest possible
implementation and has no dependencies of its own; NetworkSessionStore (the
real Data Observability intake API) is its own module, since it needs
urllib and its own error handling.
"""

import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import asdict

from .session import Session, session_from_dict


class SessionNotFoundError(Exception):
    """Raised when a SessionStore has no session for the given id."""


class SessionStore(ABC):
    """Persists and retrieves a Session, keyed by its session_id."""

    @abstractmethod
    def save(self, session: Session) -> None:
        """Persist `session`, replacing anything already stored under its session_id."""

    @abstractmethod
    def load(self, session_id: str) -> Session:
        """Retrieve a previously-saved Session.

        Raises:
            SessionNotFoundError: If no session with this id has been saved.
        """


class FilesystemSessionStore(SessionStore):
    """A local tmp file, keyed by session id.

    The original (and, before there was a backend, only) implementation.
    Still used for local dev/testing via --offline, and as the automatic
    fallback when the network intake API isn't reachable -- see
    session_store_selection.py.
    """

    def _path(self, session_id: str) -> str:
        return os.path.join(tempfile.gettempdir(), f"mwaa-session-{session_id}.json")

    def save(self, session: Session) -> None:
        with open(self._path(session.session_id), "w") as f:
            json.dump(asdict(session), f)

    def load(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not os.path.exists(path):
            raise SessionNotFoundError(f"No session found for '{session_id}'. Run `scan --session-id {session_id}` first.")
        with open(path) as f:
            return session_from_dict(json.load(f))
