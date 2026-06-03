# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_lfo_consumption_plan_migration.phases.create_jobs import (
    SECRET_ENV_KEYS,
    _build_env_and_secrets,
)


class TestBuildEnvAndSecrets(TestCase):
    def test_hoists_sensitive_keys_to_secrets(self) -> None:
        env, secrets = _build_env_and_secrets(
            {
                "DD_API_KEY": "supersecret",
                "AzureWebJobsStorage": "DefaultEndpointsProtocol=...",
                "DD_SITE": "datadoghq.com",
                "CONTROL_PLANE_ID": "abc123",
            }
        )
        env_keys = {pair.strip("'").split("=", 1)[0] for pair in env}
        self.assertIn("DD_API_KEY", env_keys)
        self.assertIn("AzureWebJobsStorage", env_keys)
        self.assertIn("CONTROL_PLANE_ID", env_keys)

        # The sensitive ones should now reference secrets.
        api_key_pair = next(p for p in env if p.startswith("DD_API_KEY="))
        self.assertEqual(api_key_pair, "DD_API_KEY=secretref:dd-api-key")
        storage_pair = next(p for p in env if p.startswith("AzureWebJobsStorage="))
        self.assertEqual(storage_pair, "AzureWebJobsStorage=secretref:connection-string")

        # Secrets should contain the actual values.
        joined = " ".join(secrets)
        self.assertIn("dd-api-key=", joined)
        self.assertIn("supersecret", joined)
        self.assertIn("connection-string=", joined)
        self.assertIn("DefaultEndpointsProtocol=...", joined)

    def test_drops_function_runtime_only_keys(self) -> None:
        env, _ = _build_env_and_secrets(
            {
                "FUNCTIONS_EXTENSION_VERSION": "~4",
                "FUNCTIONS_WORKER_RUNTIME": "python",
                "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING": "stuff",
                "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
                "DD_SITE": "datadoghq.com",
            }
        )
        env_keys = {pair.strip("'").split("=", 1)[0] for pair in env}
        for dropped in (
            "FUNCTIONS_EXTENSION_VERSION",
            "FUNCTIONS_WORKER_RUNTIME",
            "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING",
            "AzureWebJobsFeatureFlags",
        ):
            self.assertNotIn(dropped, env_keys)
        self.assertIn("DD_SITE", env_keys)

    def test_no_secrets_when_no_sensitive_keys_present(self) -> None:
        env, secrets = _build_env_and_secrets({"DD_SITE": "datadoghq.com"})
        self.assertEqual(secrets, [])
        self.assertEqual(len(env), 1)

    def test_secret_env_keys_constant_is_consistent(self) -> None:
        # Guard against drift: both sensitive keys must be opted in.
        self.assertEqual(
            set(SECRET_ENV_KEYS.keys()),
            {"DD_API_KEY", "AzureWebJobsStorage"},
        )
