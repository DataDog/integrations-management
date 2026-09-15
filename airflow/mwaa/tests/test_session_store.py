# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.session import Session
from mwaa.session_store import SessionNotFoundError, load_session, save_session


def make_session(session_id: str = "session-1") -> Session:
    return Session(session_id=session_id, region="us-east-1", environments=[])


def test_save_then_load_round_trips():
    session = make_session()

    path = save_session(session)

    assert load_session(session.session_id) == session
    assert path.endswith(f"{session.session_id}.json")


def test_load_raises_when_session_not_found():
    with pytest.raises(SessionNotFoundError, match="no-such-session"):
        load_session("no-such-session")
