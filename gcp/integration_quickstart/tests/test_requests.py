# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from gcp_integration_quickstart.requests import dd_request, request


class TestHTTPFunctions(unittest.TestCase):
    """Test the HTTP request functions."""

    @patch(
        "gcp_integration_quickstart.requests.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("gcp_integration_quickstart.requests.request")
    def test_dd_request_post(self, mock_request):
        """Test dd_request with POST method and body."""
        mock_request.return_value = ("response data", 201)

        result_data, result_status = dd_request(
            "POST", "/test/endpoint", {"test": "data"}
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://api.test.datadog.com/test/endpoint",
            {"test": "data"},
            {
                "Content-Type": "application/json",
                "DD-API-KEY": "test_api_key",
                "DD-APPLICATION-KEY": "test_app_key",
            },
        )
        self.assertEqual(result_data, "response data")
        self.assertEqual(result_status, 201)

    @patch(
        "gcp_integration_quickstart.requests.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("gcp_integration_quickstart.requests.request")
    def test_dd_request_get(self, mock_request):
        """Test dd_request with GET method."""
        mock_request.return_value = ("response data", 200)

        result_data, result_status = dd_request("GET", "/test/endpoint")

        mock_request.assert_called_once_with(
            "GET",
            "https://api.test.datadog.com/test/endpoint",
            None,
            {
                "Content-Type": "application/json",
                "DD-API-KEY": "test_api_key",
                "DD-APPLICATION-KEY": "test_app_key",
            },
        )
        self.assertEqual(result_data, "response data")
        self.assertEqual(result_status, 200)

    @patch("gcp_integration_quickstart.requests.time.sleep")
    @patch("gcp_integration_quickstart.requests.urllib.request.urlopen")
    def test_request_success_no_retry(self, mock_urlopen, mock_sleep):
        """Test request succeeds on first attempt."""
        mock_response = Mock()
        mock_response.read.return_value.decode.return_value = '{"success": true}'
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result_data, result_status = request("GET", "https://example.com")

        self.assertEqual(result_data, '{"success": true}')
        self.assertEqual(result_status, 200)
        mock_urlopen.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("gcp_integration_quickstart.requests.time.sleep")
    @patch("gcp_integration_quickstart.requests.urllib.request.urlopen")
    def test_request_retry_on_server_error(self, mock_urlopen, mock_sleep):
        """Test request retries on 500 server error and eventually succeeds."""

        # First two calls raise HTTPError 500, third succeeds
        mock_response_success = Mock()
        mock_response_success.read.return_value.decode.return_value = (
            '{"success": true}'
        )
        mock_response_success.status = 200

        mock_error_response = Mock()
        mock_error_response.read.return_value.decode.return_value = (
            '{"error": "server error"}'
        )
        mock_error_response.code = 500

        http_error = HTTPError(
            "https://example.com", 500, "Internal Server Error", {}, None
        )
        http_error.read = lambda: b'{"error": "server error"}'
        http_error.code = 500

        mock_success_context = Mock()
        mock_success_context.__enter__ = Mock(return_value=mock_response_success)
        mock_success_context.__exit__ = Mock(return_value=None)

        mock_urlopen.side_effect = [http_error, http_error, mock_success_context]

        result_data, result_status = request("GET", "https://example.com")

        self.assertEqual(result_data, '{"success": true}')
        self.assertEqual(result_status, 200)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("gcp_integration_quickstart.requests.time.sleep")
    @patch("gcp_integration_quickstart.requests.urllib.request.urlopen")
    def test_request_retry_on_url_error(self, mock_urlopen, mock_sleep):
        """Test request retries on URLError (network issues) and eventually succeeds."""

        # First two calls raise HTTPError 500, third succeeds
        mock_response_success = Mock()
        mock_response_success.read.return_value.decode.return_value = (
            '{"success": true}'
        )
        mock_response_success.status = 200

        url_error = URLError("nodename nor servname provided")

        mock_success_context = Mock()
        mock_success_context.__enter__ = Mock(return_value=mock_response_success)
        mock_success_context.__exit__ = Mock(return_value=None)

        mock_urlopen.side_effect = [url_error, url_error, mock_success_context]

        result_data, result_status = request("GET", "https://example.com")

        self.assertEqual(result_data, '{"success": true}')
        self.assertEqual(result_status, 200)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
