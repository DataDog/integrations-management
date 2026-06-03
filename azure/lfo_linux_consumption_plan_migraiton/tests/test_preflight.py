# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_lfo_consumption_plan_migration.preflight import (
    _action_granted,
    _action_granted_by_entry,
    _pattern_matches,
)


class TestPatternMatches(TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(_pattern_matches("Microsoft.App/jobs/read", "Microsoft.App/jobs/read"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(_pattern_matches("microsoft.app/jobs/read", "Microsoft.App/jobs/Read"))

    def test_wildcard_suffix(self) -> None:
        self.assertTrue(_pattern_matches("Microsoft.App/jobs/read", "Microsoft.App/jobs/*"))
        self.assertTrue(_pattern_matches("Microsoft.App/jobs/start/action", "Microsoft.App/jobs/*"))

    def test_wildcard_anywhere(self) -> None:
        self.assertTrue(_pattern_matches("Microsoft.App/jobs/start/action", "*/jobs/*/action"))

    def test_full_wildcard(self) -> None:
        self.assertTrue(_pattern_matches("anything.at.all", "*"))

    def test_no_match(self) -> None:
        self.assertFalse(_pattern_matches("Microsoft.Web/sites/read", "Microsoft.App/jobs/*"))


class TestActionGrantedByEntry(TestCase):
    def test_actions_grant_then_not_actions_revoke(self) -> None:
        entry = {
            "actions": ["*"],
            "notActions": ["Microsoft.Authorization/*/Delete"],
        }
        self.assertTrue(_action_granted_by_entry(entry, "Microsoft.App/jobs/read"))
        self.assertFalse(_action_granted_by_entry(entry, "Microsoft.Authorization/roleAssignments/Delete"))

    def test_no_match_in_actions(self) -> None:
        entry = {"actions": ["Microsoft.Web/*"], "notActions": []}
        self.assertFalse(_action_granted_by_entry(entry, "Microsoft.App/jobs/read"))

    def test_empty_entry(self) -> None:
        self.assertFalse(_action_granted_by_entry({}, "Microsoft.App/jobs/read"))


class TestActionGranted(TestCase):
    def test_union_across_entries(self) -> None:
        # First entry matches Web/*, second entry matches App/jobs/*. An action
        # in App/jobs is granted via the second entry even though the first
        # entry doesn't match it.
        entries = [
            {"actions": ["Microsoft.Web/*"], "notActions": []},
            {"actions": ["Microsoft.App/jobs/*"], "notActions": []},
        ]
        self.assertTrue(_action_granted(entries, "Microsoft.App/jobs/read"))
        self.assertTrue(_action_granted(entries, "Microsoft.Web/sites/read"))
        self.assertFalse(_action_granted(entries, "Microsoft.Storage/storageAccounts/read"))

    def test_not_actions_only_excludes_within_entry(self) -> None:
        # First entry has actions:["*"] but notActions:[Authorization/Delete].
        # Second entry has actions:[Authorization/roleAssignments/delete] with
        # no notActions. The second entry should grant Delete because exclusion
        # is per-entry, not global.
        entries = [
            {"actions": ["*"], "notActions": ["Microsoft.Authorization/*/Delete"]},
            {"actions": ["Microsoft.Authorization/roleAssignments/Delete"], "notActions": []},
        ]
        self.assertTrue(_action_granted(entries, "Microsoft.Authorization/roleAssignments/Delete"))
