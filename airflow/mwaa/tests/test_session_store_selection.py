# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import urllib.error
from unittest.mock import patch

from mwaa.network_session_store import NetworkSessionStore
from mwaa.session_store import FilesystemSessionStore
from mwaa.session_store_selection import select_session_store


def test_offline_always_returns_filesystem_store():
    store = select_session_store(offline=True, dd_site=None, dd_api_key=None)
    assert isinstance(store, FilesystemSessionStore)


def test_reachable_intake_returns_network_store():
    with patch("mwaa.session_store_selection._intake_reachable", return_value=True):
        store = select_session_store(offline=False, dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")
    assert isinstance(store, NetworkSessionStore)


def test_unreachable_intake_falls_back_to_filesystem(capsys):
    with patch("mwaa.session_store_selection._intake_reachable", return_value=False):
        store = select_session_store(offline=False, dd_site="datadoghq.com", dd_api_key="fake-dd-api-key")
    assert isinstance(store, FilesystemSessionStore)
    assert "falling back to local filesystem storage" in capsys.readouterr().out


def test_intake_reachable_true_on_any_http_response():
    from mwaa.session_store_selection import _intake_reachable

    with patch("mwaa.session_store_selection.urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 403, "forbidden", {}, None)):
        assert _intake_reachable("datadoghq.com") is True


def test_intake_reachable_false_on_connection_error():
    from mwaa.session_store_selection import _intake_reachable

    with patch("mwaa.session_store_selection.urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
        assert _intake_reachable("datadoghq.com") is False
