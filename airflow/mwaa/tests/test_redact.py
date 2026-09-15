# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.redact import redact_secrets


def test_redacts_exported_api_key():
    text = "export OPENLINEAGE_API_KEY=00000000000000000000000000000000\n"
    redacted = redact_secrets(text)
    assert "00000000000000000000000000000000" not in redacted
    assert "export OPENLINEAGE_API_KEY=<redacted:32 chars>" in redacted


def test_redacts_password_and_token_and_secret_variants():
    text = (
        "export DB_PASSWORD=hunter2\n"
        "MY_TOKEN=abc123\n"
        "export SOME_SECRET=xyz\n"
    )
    redacted = redact_secrets(text)
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "xyz" not in redacted


def test_leaves_non_secret_assignments_untouched():
    text = "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\nexport FOO=bar\n"
    assert redact_secrets(text) == text


def test_handles_none():
    assert redact_secrets(None) is None
