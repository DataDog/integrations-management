# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Sequence
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.scopes import Scope
from azure_integration_quickstart.user_selections import UserSelections, receive_user_selections

from integration_quickstart.tests.test_data import (
    ERROR_403,
    ERROR_404,
    EXAMPLE_WORKFLOW_ID,
    MGROUP_SELECTION_RESPONSE,
    MGROUP_SELECTIONS,
    OVERLAPPING_SELECTIONS,
    OVERLAPPING_SELECTIONS_RESPONSE,
    SELECTIONS_WITH_LOG_FORWARDING,
    SELECTIONS_WITH_LOG_FORWARDING_RESPONSE,
    SUBSCRIPTION_SELECTION,
    SUBSCRIPTION_SELECTION_RESPONSE,
)


def scopes_equal(scope1: Scope, scope2: Scope):
    return scope1.id == scope2.id and scope1.name == scope2.name


class TestReceiveUserSelections(TestCase):
    def setUp(self) -> None:
        self.dd_request_mock: MagicMock = self.patch("azure_integration_quickstart.user_selections.dd_request")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_same_scopes(self, scopes1: Sequence[Scope], scopes2: Sequence[Scope]):
        return all([any([scopes_equal(scope1, scope2) for scope2 in scopes2]) for scope1 in scopes1])

    def assert_selections_equal(self, selections1: UserSelections, selections2: UserSelections):
        self.assertEqual(selections1.app_registration_config, selections2.app_registration_config)
        self.assertEqual(selections1.log_forwarding_config, selections2.log_forwarding_config)
        self.assert_same_scopes(selections1.scopes, selections2.scopes)

    def test_receive_subscriptions(self):
        self.dd_request_mock.return_value = (SUBSCRIPTION_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SUBSCRIPTION_SELECTION)

    def test_receive_mgroup(self):
        self.dd_request_mock.return_value = (MGROUP_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, MGROUP_SELECTIONS)

    def test_receive_overlapping(self):
        self.dd_request_mock.return_value = (OVERLAPPING_SELECTIONS_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, OVERLAPPING_SELECTIONS)

    def test_receive_log_forwarder(self):
        self.dd_request_mock.return_value = (SELECTIONS_WITH_LOG_FORWARDING_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SELECTIONS_WITH_LOG_FORWARDING)

    def test_error(self):
        self.dd_request_mock.side_effect = [ERROR_403, (SUBSCRIPTION_SELECTION_RESPONSE, 200)]
        with self.assertRaises(RuntimeError):
            receive_user_selections(EXAMPLE_WORKFLOW_ID)

    def test_polling(self):
        self.dd_request_mock.side_effect = [ERROR_404, (SUBSCRIPTION_SELECTION_RESPONSE, 200)]
        selections = receive_user_selections(EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SUBSCRIPTION_SELECTION)
