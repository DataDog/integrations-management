# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import urllib.error
from unittest.mock import patch

import pytest

from mwaa.network_session_store import NetworkSessionStore, SessionStoreError
from mwaa.session import Session
from mwaa.session_store import SessionNotFoundError


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self) -> bytes:
        return self._body


def make_session(session_id: str = "session-1") -> Session:
    return Session(session_id=session_id, region="us-east-1", environments=[])


def test_save_posts_to_the_data_obs_intake_host():
    store = NetworkSessionStore(dd_site="datad0g.com", dd_api_key="fake-dd-api-key")

    with patch("mwaa.network_session_store.urllib.request.urlopen", return_value=_FakeResponse(b"{}")) as mock_urlopen:
        store.save(make_session())

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://data-obs-intake.datad0g.com/api/v1/webhook/airflow/config-sessions"
    assert request.get_header("Dd-api-key") == "fake-dd-api-key"
    assert request.get_method() == "POST"


def test_save_raises_session_store_error_on_transport_failure():
    store = NetworkSessionStore(dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")

    with patch("mwaa.network_session_store.urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
        with pytest.raises(SessionStoreError):
            store.save(make_session())


def test_load_returns_the_session_from_the_response_body():
    store = NetworkSessionStore(dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")
    body = json.dumps({"session_id": "session-1", "region": "us-east-1", "environments": []}).encode("utf-8")

    with patch("mwaa.network_session_store.urllib.request.urlopen", return_value=_FakeResponse(body)) as mock_urlopen:
        session = store.load("session-1")

    assert session == make_session("session-1")
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://data-obs-intake.datadoghq.com/api/v1/webhook/airflow/config-sessions/session-1"
    assert request.get_method() == "GET"


def test_load_raises_session_not_found_on_404():
    store = NetworkSessionStore(dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")
    error = urllib.error.HTTPError("url", 404, "not found", {}, None)

    with patch("mwaa.network_session_store.urllib.request.urlopen", side_effect=error):
        with pytest.raises(SessionNotFoundError):
            store.load("no-such-session")


def test_load_raises_session_store_error_on_other_http_errors():
    store = NetworkSessionStore(dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")
    error = urllib.error.HTTPError("url", 500, "server error", {}, None)

    with patch("mwaa.network_session_store.urllib.request.urlopen", side_effect=error):
        with pytest.raises(SessionStoreError):
            store.load("session-1")
