# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.session import Session
from mwaa.session_store import FilesystemSessionStore, SessionNotFoundError


def make_session(session_id: str = "session-1") -> Session:
    return Session(session_id=session_id, region="us-east-1", environments=[])


def test_save_then_load_round_trips():
    store = FilesystemSessionStore()
    session = make_session()

    store.save(session)

    assert store.load(session.session_id) == session


def test_load_raises_when_session_not_found():
    store = FilesystemSessionStore()
    with pytest.raises(SessionNotFoundError, match="no-such-session"):
        store.load("no-such-session")
