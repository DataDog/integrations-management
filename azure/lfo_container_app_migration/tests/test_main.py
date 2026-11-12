# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_lfo_container_app_migration.main import parse_arguments


class TestParseArguments(TestCase):
    def parse(self, *args: str):
        with mock_patch("sys.argv", ["azure_lfo_container_app_migration.pyz", *args]):
            return parse_arguments()

    def test_dry_run_is_the_default(self):
        self.assertTrue(self.parse().dry_run)

    def test_dry_run_flag_keeps_dry_run(self):
        self.assertTrue(self.parse("--dry-run").dry_run)

    def test_no_dry_run_flag_migrates(self):
        self.assertFalse(self.parse("--no-dry-run").dry_run)
