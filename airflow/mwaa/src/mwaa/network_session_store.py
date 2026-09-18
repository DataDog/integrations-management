# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""SessionStore backed by the real Data Observability config-sessions intake API.

    POST /api/v1/webhook/airflow/config-sessions            -- save (create or replace)
    GET  /api/v1/webhook/airflow/config-sessions/{session_id} -- load

Host is always the `data-obs-intake` subdomain of whatever --dd-site names --
the same pattern startup_script.py uses for OPENLINEAGE_URL, so a session
submitted while testing against datad0g.com lands on the same site its
startup.sh points at. Auth is the DD-API-KEY header; the API derives the
Datadog organization from the key itself, so nothing about which org this is
needs to (or may) appear in the payload.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict

from .session import Session, session_from_dict
from .session_store import SessionNotFoundError, SessionStore

_PATH = "/api/v1/webhook/airflow/config-sessions"


class SessionStoreError(Exception):
    """The intake API request failed for a reason other than "session not found"."""


class NetworkSessionStore(SessionStore):
    def __init__(self, dd_site: str, dd_api_key: str, timeout: float = 30.0):
        self._base_url = f"https://data-obs-intake.{dd_site}{_PATH}"
        self._dd_api_key = dd_api_key
        self._timeout = timeout

    def save(self, session: Session) -> None:
        body = json.dumps(asdict(session)).encode("utf-8")
        request = urllib.request.Request(
            self._base_url,
            data=body,
            headers={"Content-Type": "application/json", "DD-API-KEY": self._dd_api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise SessionStoreError(f"could not submit session {session.session_id!r} to the intake API: {exc}") from exc

    def load(self, session_id: str) -> Session:
        url = f"{self._base_url}/{urllib.parse.quote(session_id, safe='')}"
        request = urllib.request.Request(url, headers={"DD-API-KEY": self._dd_api_key}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SessionNotFoundError(f"No session found for {session_id!r}. Run `scan --session-id {session_id}` first.") from exc
            raise SessionStoreError(f"could not retrieve session {session_id!r} from the intake API: {exc}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SessionStoreError(f"could not reach the intake API for session {session_id!r}: {exc}") from exc
        return session_from_dict(data)
