# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import patch
from urllib.error import HTTPError

from azure_agentless_setup.agentless_api import (
    activate_scan_options,
    deactivate_scan_options,
)


def _http_error(code: int) -> HTTPError:
    return HTTPError(url="https://example", code=code, msg=str(code), hdrs=None, fp=None)


class TestActivateScanOptions:
    def test_post_then_patch_on_409(self):
        """Already-activated subs (POST 409) fall back to PATCH so re-deploys converge."""
        sub_a = "00000000-0000-0000-0000-aaaaaaaaaaaa"
        sub_b = "00000000-0000-0000-0000-bbbbbbbbbbbb"

        # sub_a: POST succeeds, no PATCH needed.
        # sub_b: POST returns 409, falls back to PATCH which succeeds.
        def fake_dd_request(method, path, body=None):
            if method == "POST" and body["data"]["id"] == sub_a:
                return ("", 201)
            if method == "POST" and body["data"]["id"] == sub_b:
                raise _http_error(409)
            if method == "PATCH" and path.endswith(sub_b):
                return ("", 200)
            raise AssertionError(f"unexpected call: {method} {path}")

        with patch("azure_agentless_setup.agentless_api.dd_request", side_effect=fake_dd_request) as m:
            assert activate_scan_options([sub_a, sub_b]) is True

        calls = [(c.args[0], c.args[1]) for c in m.call_args_list]
        assert calls == [
            ("POST", "/api/v2/agentless_scanning/accounts/azure"),
            ("POST", "/api/v2/agentless_scanning/accounts/azure"),
            ("PATCH", f"/api/v2/agentless_scanning/accounts/azure/{sub_b}"),
        ]

    def test_non_409_post_failure_is_not_retried_and_soft_fails(self):
        """Non-409 errors propagate to the per-subscription error list (soft fail, no PATCH retry)."""
        sub = "00000000-0000-0000-0000-cccccccccccc"

        with patch(
            "azure_agentless_setup.agentless_api.dd_request",
            side_effect=_http_error(500),
        ) as m:
            assert activate_scan_options([sub]) is False

        assert [c.args[0] for c in m.call_args_list] == ["POST"]


class TestDeactivateScanOptions:
    def test_404_treated_as_success_and_other_errors_soft_fail(self):
        """One sub deletes cleanly, one is already absent (404 → success), one fails (500 → error)."""
        sub_ok = "00000000-0000-0000-0000-aaaaaaaaaaaa"
        sub_absent = "00000000-0000-0000-0000-bbbbbbbbbbbb"
        sub_err = "00000000-0000-0000-0000-cccccccccccc"

        def fake_dd_request(method, path, body=None):
            assert method == "DELETE"
            if path.endswith(sub_ok):
                return ("", 204)
            if path.endswith(sub_absent):
                raise _http_error(404)
            if path.endswith(sub_err):
                raise _http_error(500)
            raise AssertionError(f"unexpected call: {method} {path}")

        with patch("azure_agentless_setup.agentless_api.dd_request", side_effect=fake_dd_request) as m:
            assert deactivate_scan_options([sub_ok, sub_absent, sub_err]) is False

        called_paths = [c.args[1] for c in m.call_args_list]
        assert called_paths == [
            f"/api/v2/agentless_scanning/accounts/azure/{sub_ok}",
            f"/api/v2/agentless_scanning/accounts/azure/{sub_absent}",
            f"/api/v2/agentless_scanning/accounts/azure/{sub_err}",
        ]

    def test_all_success_returns_true(self):
        sub_a = "00000000-0000-0000-0000-aaaaaaaaaaaa"
        sub_b = "00000000-0000-0000-0000-bbbbbbbbbbbb"

        with patch(
            "azure_agentless_setup.agentless_api.dd_request",
            return_value=("", 204),
        ):
            assert deactivate_scan_options([sub_a, sub_b]) is True
