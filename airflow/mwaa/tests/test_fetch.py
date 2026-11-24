# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import io
import urllib.error

import pytest

from mwaa import fetch


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (_Response(201), True),
        (_Response(202), True),
        (urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO()), False),
        (urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO()), False),
        (urllib.error.HTTPError("u", 500, "Server Error", {}, io.BytesIO()), None),
        (urllib.error.URLError("unreachable"), None),
        (TimeoutError(), None),
    ],
    ids=["201", "202", "401", "403", "500", "unreachable", "timeout"],
)
def test_check_intake_api_key(monkeypatch, outcome, expected):
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)

    assert fetch.check_intake_api_key("datad0g.com", "k" * 32) is expected
    (request,) = requests
    assert request.full_url == "https://data-obs-intake.datad0g.com/api/v1/lineage"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer " + "k" * 32
