# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

from azure_integration_quickstart.user_selections import (
    AppRegistrationUserSelections,
    LFOUserSelections,
    UserSelections,
    receive_user_selections,
)

from integration_quickstart.tests.dd_test_case import DDTestCase
from integration_quickstart.tests.test_data import (
    ERROR_403,
    ERROR_404,
    EXAMPLE_WORKFLOW_ID,
    EXAMPLE_WORKFLOW_TYPE,
    LFO_SELECTION,
    LFO_SELECTION_RESPONSE,
    LFO_WORKFLOW_TYPE,
    MGROUP_SELECTION_RESPONSE,
    MGROUP_SELECTIONS,
    OVERLAPPING_SELECTIONS,
    OVERLAPPING_SELECTIONS_RESPONSE,
    SELECTIONS_WITH_LOG_FORWARDING,
    SELECTIONS_WITH_LOG_FORWARDING_RESPONSE,
    SUBSCRIPTION_SELECTION,
    SUBSCRIPTION_SELECTION_RESPONSE,
)


class TestReceiveUserSelections(DDTestCase):
    def setUp(self) -> None:
        self.dd_request_mock: MagicMock = self.patch("azure_integration_quickstart.user_selections.dd_request")

    def assert_selections_equal(self, selections1: UserSelections, selections2: UserSelections):
        """Assert that two UserSelections objects are equal, handling both AppRegistration and LFO types."""
        self.assert_same_scopes(selections1.scopes, selections2.scopes)
        # Check type-specific attributes
        if isinstance(selections1, AppRegistrationUserSelections) and isinstance(
            selections2, AppRegistrationUserSelections
        ):
            self.assertEqual(selections1.app_registration_config, selections2.app_registration_config)
            self.assertEqual(selections1.log_forwarding_config, selections2.log_forwarding_config)
        elif isinstance(selections1, LFOUserSelections) and isinstance(selections2, LFOUserSelections):
            self.assertEqual(selections1.log_forwarding_config, selections2.log_forwarding_config)
        else:
            self.fail(f"Type mismatch: {type(selections1)} vs {type(selections2)}")

    def test_receive_subscriptions(self):
        self.dd_request_mock.return_value = (SUBSCRIPTION_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SUBSCRIPTION_SELECTION)

    def test_receive_mgroup(self):
        self.dd_request_mock.return_value = (MGROUP_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, MGROUP_SELECTIONS)

    def test_receive_overlapping(self):
        self.dd_request_mock.return_value = (OVERLAPPING_SELECTIONS_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, OVERLAPPING_SELECTIONS)

    def test_receive_log_forwarder(self):
        self.dd_request_mock.return_value = (SELECTIONS_WITH_LOG_FORWARDING_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SELECTIONS_WITH_LOG_FORWARDING)

    def test_error(self):
        self.dd_request_mock.side_effect = [ERROR_403, (SUBSCRIPTION_SELECTION_RESPONSE, 200)]
        with self.assertRaises(RuntimeError):
            receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)

    def test_polling(self):
        self.dd_request_mock.side_effect = [ERROR_404, (SUBSCRIPTION_SELECTION_RESPONSE, 200)]
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assert_selections_equal(selections, SUBSCRIPTION_SELECTION)

    def test_receive_lfo_selections(self):
        """Test that LFO workflow type returns LFOUserSelections."""
        self.dd_request_mock.return_value = (LFO_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(LFO_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assertIsInstance(selections, LFOUserSelections)
        self.assert_selections_equal(selections, LFO_SELECTION)
        self.assertIsNotNone(selections.log_forwarding_config)

    def test_app_registration_workflow_returns_app_registration_selections(self):
        """Test that app registration workflow type returns AppRegistrationUserSelections."""
        self.dd_request_mock.return_value = (SUBSCRIPTION_SELECTION_RESPONSE, 200)
        selections = receive_user_selections(EXAMPLE_WORKFLOW_TYPE, EXAMPLE_WORKFLOW_ID)
        self.assertIsInstance(selections, AppRegistrationUserSelections)
        self.assert_selections_equal(selections, SUBSCRIPTION_SELECTION)
