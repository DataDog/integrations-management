# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for common.requests auth header construction."""

import os
from unittest import TestCase
from unittest.mock import patch as mock_patch

from common.requests import dd_auth_headers


class TestDdAuthHeaders(TestCase):
    def test_access_token_uses_bearer_and_omits_key_headers(self):
        env = {"DD_ACCESS_TOKEN": "ddpat_abc", "DD_API_KEY": "k", "DD_APP_KEY": "a"}
        with mock_patch.dict(os.environ, env, clear=True):
            headers = dd_auth_headers()
        self.assertEqual(headers["Authorization"], "Bearer ddpat_abc")
        self.assertNotIn("DD-API-KEY", headers)
        self.assertNotIn("DD-APPLICATION-KEY", headers)

    def test_without_access_token_uses_classic_key_pair(self):
        env = {"DD_API_KEY": "k", "DD_APP_KEY": "a"}
        with mock_patch.dict(os.environ, env, clear=True):
            headers = dd_auth_headers()
        self.assertEqual(headers["DD-API-KEY"], "k")
        self.assertEqual(headers["DD-APPLICATION-KEY"], "a")
        self.assertNotIn("Authorization", headers)

    def test_blank_access_token_falls_back_to_key_pair(self):
        env = {"DD_ACCESS_TOKEN": "   ", "DD_API_KEY": "k", "DD_APP_KEY": "a"}
        with mock_patch.dict(os.environ, env, clear=True):
            headers = dd_auth_headers()
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["DD-API-KEY"], "k")
