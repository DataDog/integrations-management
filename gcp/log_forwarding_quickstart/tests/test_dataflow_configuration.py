# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import Mock, patch

from gcp_log_forwarding_quickstart.dataflow_configuration import (
    DATAFLOW_JOB_NAME,
    LOG_SINK_NAME,
    PUBSUB_DEAD_LETTER_TOPIC_ID,
    PUBSUB_TOPIC_ID,
    SECRET_MANAGER_NAME,
    assign_required_dataflow_roles,
    create_dataflow_job,
    create_dataflow_staging_bucket,
    create_log_sinks,
    create_secret_manager_entry,
    create_topics_with_subscription,
    find_or_create_datadog_api_key,
)
from gcp_log_forwarding_quickstart.models import DataflowConfiguration, ExclusionFilter
from gcp_shared.models import ConfigurationScope, Folder, Project


class TestCreateDataflowStagingBucket(unittest.TestCase):
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_dataflow_staging_bucket_creates_new(self, mock_gcloud):
        mock_gcloud.side_effect = [
            [],
            None,
            None,
        ]

        step_reporter = Mock()

        create_dataflow_staging_bucket(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 3)
        self.assertEqual(
            actual_commands[0],
            "storage buckets list --project test-project --filter name=dataflow-temp-test-project",
        )
        self.assertEqual(
            actual_commands[1],
            "storage buckets create gs://dataflow-temp-test-project --project test-project --location us-central1 --uniform-bucket-level-access --soft-delete-duration 0s",
        )
        self.assertEqual(
            actual_commands[2],
            "storage buckets add-iam-policy-binding gs://dataflow-temp-test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/storage.objectAdmin",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_dataflow_staging_bucket_uses_existing(self, mock_gcloud):
        mock_gcloud.side_effect = [
            [{"name": "dataflow-temp-test-project"}],
            None,
        ]

        step_reporter = Mock()

        create_dataflow_staging_bucket(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 2)
        self.assertEqual(
            actual_commands[0],
            "storage buckets list --project test-project --filter name=dataflow-temp-test-project",
        )
        self.assertEqual(
            actual_commands[1],
            "storage buckets add-iam-policy-binding gs://dataflow-temp-test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/storage.objectAdmin",
        )


class TestCreateTopicsWithSubscription(unittest.TestCase):
    """Test the create_topics_with_subscription function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_topics_with_subscription_creates_new_topic(self, mock_gcloud):
        """Test creating a new topic and subscription."""
        mock_gcloud.side_effect = [
            [],
            None,
            [],
            None,
            None,
            None,
            [],
            None,
            None,
            [],
            None,
            None,
            None,
        ]

        step_reporter = Mock()

        create_topics_with_subscription(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 13)
        self.assertEqual(
            actual_commands[0],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[1],
            f"pubsub topics create {PUBSUB_TOPIC_ID} --project test-project",
        )
        self.assertEqual(
            actual_commands[2],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub subscriptions create {PUBSUB_TOPIC_ID}-subscription --topic {PUBSUB_TOPIC_ID} --project test-project",
        )
        self.assertEqual(
            actual_commands[4],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[5],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )
        self.assertEqual(
            actual_commands[6],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[7],
            f"pubsub topics create {PUBSUB_DEAD_LETTER_TOPIC_ID} --project test-project",
        )
        self.assertEqual(
            actual_commands[8],
            f"pubsub topics add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )
        self.assertEqual(
            actual_commands[9],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[10],
            f"pubsub subscriptions create {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --topic {PUBSUB_DEAD_LETTER_TOPIC_ID} --project test-project",
        )
        self.assertEqual(
            actual_commands[11],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[12],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_topics_with_subscription_uses_existing_topic(self, mock_gcloud):
        """Test using an existing topic."""

        mock_gcloud.side_effect = [
            [{"name": f"projects/test-project/topics/{PUBSUB_TOPIC_ID}"}],
            [{"topic": f"projects/test-project/topics/{PUBSUB_TOPIC_ID}"}],
            None,
            None,
            [{"name": f"projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"}],
            None,
            [{"topic": f"projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"}],
            None,
            None,
        ]

        step_reporter = Mock()

        create_topics_with_subscription(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 9)
        self.assertEqual(
            actual_commands[0],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[1],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[2],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )
        self.assertEqual(
            actual_commands[4],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[5],
            f"pubsub topics add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )
        self.assertEqual(
            actual_commands[6],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[7],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[8],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_topics_with_subscription_recreates_subscription(self, mock_gcloud):
        """Test recreating subscription when topic mismatch."""
        wrong_topic = "projects/test-project/topics/wrong-topic"
        correct_topic = f"projects/test-project/topics/{PUBSUB_TOPIC_ID}"
        correct_dead_letter_topic = (
            f"projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"
        )

        mock_gcloud.side_effect = [
            [{"name": correct_topic}],
            [{"topic": wrong_topic}],
            None,
            None,
            None,
            None,
            [{"name": correct_dead_letter_topic}],
            None,
            [{"topic": correct_dead_letter_topic}],
            None,
            None,
        ]

        step_reporter = Mock()

        create_topics_with_subscription(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 11)
        self.assertEqual(
            actual_commands[0],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[1],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[2],
            f"pubsub subscriptions delete {PUBSUB_TOPIC_ID}-subscription --project test-project",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub subscriptions create {PUBSUB_TOPIC_ID}-subscription --topic {PUBSUB_TOPIC_ID} --project test-project",
        )
        self.assertEqual(
            actual_commands[4],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[5],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )
        self.assertEqual(
            actual_commands[6],
            f"pubsub topics list --project test-project --filter name=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}",
        )
        self.assertEqual(
            actual_commands[7],
            f"pubsub topics add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )
        self.assertEqual(
            actual_commands[8],
            f"pubsub subscriptions list --project test-project --filter name=projects/test-project/subscriptions/{PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription",
        )
        self.assertEqual(
            actual_commands[9],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.subscriber",
        )
        self.assertEqual(
            actual_commands[10],
            f"pubsub subscriptions add-iam-policy-binding {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/pubsub.viewer",
        )


class TestCreateSecretManagerEntry(unittest.TestCase):
    """Test the create_secret_manager_entry function."""

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.find_or_create_datadog_api_key"
    )
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_secret_manager_entry_uses_existing_secret(
        self, mock_gcloud, mock_create_api_key
    ):
        """Test using an existing secret with versions."""

        mock_gcloud.side_effect = [
            [{"name": f"projects/test-project/secrets/{SECRET_MANAGER_NAME}"}],
            None,
            [{"name": "version1"}],
        ]

        step_reporter = Mock()

        create_secret_manager_entry(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        mock_create_api_key.assert_not_called()

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.find_or_create_datadog_api_key"
    )
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.tempfile.NamedTemporaryFile"
    )
    def test_create_secret_manager_entry_creates_new_secret(
        self, mock_tempfile, mock_gcloud, mock_create_api_key
    ):
        """Test creating a new secret."""
        mock_create_api_key.return_value = "test-api-key"
        mock_tmp = Mock()
        mock_tmp.__enter__ = Mock(return_value=mock_tmp)
        mock_tmp.__exit__ = Mock(return_value=False)
        mock_tmp.name = "/tmp/test"
        mock_tempfile.return_value = mock_tmp

        mock_gcloud.side_effect = [
            [],
            None,
            None,
            None,
        ]

        step_reporter = Mock()

        create_secret_manager_entry(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        mock_create_api_key.assert_called_once()

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"secrets list --project test-project --filter 'name~{SECRET_MANAGER_NAME}'",
        )
        self.assertEqual(
            actual_commands[1],
            f"secrets create {SECRET_MANAGER_NAME} --project test-project",
        )
        self.assertEqual(
            actual_commands[2],
            f"secrets add-iam-policy-binding {SECRET_MANAGER_NAME} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor --condition None --quiet",
        )
        self.assertEqual(
            actual_commands[3],
            f"secrets versions add {SECRET_MANAGER_NAME} --project test-project --data-file /tmp/test",
        )

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.find_or_create_datadog_api_key"
    )
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.tempfile.NamedTemporaryFile"
    )
    def test_create_secret_manager_entry_adds_version_to_existing(
        self, mock_tempfile, mock_gcloud, mock_create_api_key
    ):
        """Test adding version to existing secret with no versions."""
        mock_create_api_key.return_value = "test-api-key"
        mock_tmp = Mock()
        mock_tmp.__enter__ = Mock(return_value=mock_tmp)
        mock_tmp.__exit__ = Mock(return_value=False)
        mock_tmp.name = "/tmp/test"
        mock_tempfile.return_value = mock_tmp

        mock_gcloud.side_effect = [
            [{"name": f"projects/test-project/secrets/{SECRET_MANAGER_NAME}"}],
            None,
            [],
            None,
            None,
        ]

        step_reporter = Mock()

        create_secret_manager_entry(
            step_reporter, "test-project", "test-sa@project.iam.gserviceaccount.com"
        )

        mock_create_api_key.assert_called_once()

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 5)
        self.assertEqual(
            actual_commands[0],
            f"secrets list --project test-project --filter 'name~{SECRET_MANAGER_NAME}'",
        )
        self.assertEqual(
            actual_commands[1],
            f"secrets add-iam-policy-binding {SECRET_MANAGER_NAME} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor --condition None --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"secrets versions list {SECRET_MANAGER_NAME} --project test-project",
        )
        self.assertEqual(
            actual_commands[3],
            f"secrets add-iam-policy-binding {SECRET_MANAGER_NAME} --project test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor --condition None --quiet",
        )
        self.assertEqual(
            actual_commands[4],
            f"secrets versions add {SECRET_MANAGER_NAME} --project test-project --data-file /tmp/test",
        )


class TestFindOrCreateDatadogApiKey(unittest.TestCase):
    """Test the find_or_create_datadog_api_key function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_find_or_create_datadog_api_key_uses_existing(self, mock_dd_request):
        """Test using an existing API key."""
        mock_dd_request.side_effect = [
            (
                json.dumps(
                    {
                        "data": [
                            {
                                "id": "existing-key-id",
                                "attributes": {"name": SECRET_MANAGER_NAME},
                            }
                        ]
                    }
                ),
                200,
            ),
            (
                json.dumps({"data": {"attributes": {"key": "existing-api-key-value"}}}),
                200,
            ),
        ]

        result = find_or_create_datadog_api_key()

        self.assertEqual(result, "existing-api-key-value")

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_find_or_create_datadog_api_key_creates_new(self, mock_dd_request):
        """Test creating a new API key."""
        mock_dd_request.side_effect = [
            (json.dumps({"data": []}), 200),
            (
                json.dumps({"data": {"attributes": {"key": "new-api-key-value"}}}),
                201,
            ),
        ]

        result = find_or_create_datadog_api_key()

        self.assertEqual(result, "new-api-key-value")

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_find_or_create_datadog_api_key_search_error(self, mock_dd_request):
        """Test error handling when searching for keys fails."""
        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        with self.assertRaises(RuntimeError) as ctx:
            find_or_create_datadog_api_key()

        self.assertIn("Failed to search API keys", str(ctx.exception))


class TestAssignRequiredDataflowRoles(unittest.TestCase):
    """Test the assign_required_dataflow_roles function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_assign_required_dataflow_roles_success(self, mock_gcloud):
        """Test successfully assigning all required roles."""
        mock_gcloud.return_value = None

        step_reporter = Mock()

        assign_required_dataflow_roles(
            step_reporter, "test-sa@project.iam.gserviceaccount.com", "test-project"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 1)
        self.assertEqual(
            actual_commands[0],
            "projects add-iam-policy-binding test-project --member serviceAccount:test-sa@project.iam.gserviceaccount.com --role roles/dataflow.worker --condition None --quiet",
        )


class TestCreateLogSinks(unittest.TestCase):
    """Test the create_log_sinks function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_for_projects(self, mock_gcloud):
        """Test creating log sinks for projects."""

        mock_gcloud.side_effect = [
            [],
            None,
            {
                "writerIdentity": "serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com"
            },
            None,
        ]

        step_reporter = Mock()
        project = Project(
            id="test-project",
            name="Test Project",
            parent_id="parent123",
            is_already_monitored=False,
        )
        configuration_scope = ConfigurationScope(projects=[project], folders=[])

        create_log_sinks(
            step_reporter,
            "default-project",
            configuration_scope,
            inclusion_filter="",
            exclusion_filters=[],
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"logging sinks list --project test-project --filter name={LOG_SINK_NAME}",
        )
        self.assertEqual(
            actual_commands[1],
            f"logging sinks create {LOG_SINK_NAME} pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} --project test-project --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"logging sinks describe {LOG_SINK_NAME} --project test-project",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} --project default-project --member serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_for_folders(self, mock_gcloud):
        """Test creating log sinks for folders."""

        mock_gcloud.side_effect = [
            [],
            None,
            {
                "writerIdentity": "serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com"
            },
            None,
        ]

        step_reporter = Mock()
        folder = Folder(
            id="folder123",
            name="Test Folder",
            parent_id="parent456",
            child_scopes=[],
        )
        configuration_scope = ConfigurationScope(projects=[], folders=[folder])

        create_log_sinks(
            step_reporter,
            "default-project",
            configuration_scope,
            inclusion_filter="",
            exclusion_filters=[],
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"logging sinks list --folder folder123 --filter name={LOG_SINK_NAME}",
        )
        self.assertEqual(
            actual_commands[1],
            f"logging sinks create {LOG_SINK_NAME} pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} --folder folder123 --include-children --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"logging sinks describe {LOG_SINK_NAME} --folder folder123",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} --project default-project --member serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_updates_existing_project(self, mock_gcloud):
        """Test updating sink when it already exists in project."""

        mock_gcloud.side_effect = [
            [{"name": "datadog-log-sink"}],
            None,
            {
                "writerIdentity": "serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com"
            },
            None,
        ]

        step_reporter = Mock()
        project = Project(
            id="test-project",
            name="Test Project",
            parent_id="parent123",
            is_already_monitored=False,
        )
        configuration_scope = ConfigurationScope(projects=[project], folders=[])

        create_log_sinks(
            step_reporter,
            "default-project",
            configuration_scope,
            inclusion_filter="",
            exclusion_filters=[],
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"logging sinks list --project test-project --filter name={LOG_SINK_NAME}",
        )
        self.assertEqual(
            actual_commands[1],
            f"logging sinks update {LOG_SINK_NAME} pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} --project test-project --clear-exclusions --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"logging sinks describe {LOG_SINK_NAME} --project test-project",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} --project default-project --member serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_updates_existing_folder(self, mock_gcloud):
        """Test updating sink when it already exists in folder."""

        mock_gcloud.side_effect = [
            [{"name": "datadog-log-sink"}],
            None,
            {
                "writerIdentity": "serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com"
            },
            None,
        ]

        step_reporter = Mock()
        folder = Folder(
            id="folder123",
            name="Test Folder",
            parent_id="parent456",
            child_scopes=[],
        )
        configuration_scope = ConfigurationScope(projects=[], folders=[folder])

        create_log_sinks(
            step_reporter,
            "default-project",
            configuration_scope,
            inclusion_filter="",
            exclusion_filters=[],
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"logging sinks list --folder folder123 --filter name={LOG_SINK_NAME}",
        )
        self.assertEqual(
            actual_commands[1],
            f"logging sinks update {LOG_SINK_NAME} pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} --folder folder123 --include-children --clear-exclusions --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"logging sinks describe {LOG_SINK_NAME} --folder folder123",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} --project default-project --member serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_with_filters(self, mock_gcloud):
        """Test creating log sinks with inclusion and exclusion filters."""

        mock_gcloud.side_effect = [
            [],
            None,
            {
                "writerIdentity": "serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com"
            },
            None,
        ]

        step_reporter = Mock()
        project = Project(
            id="test-project",
            name="Test Project",
            parent_id="parent123",
            is_already_monitored=False,
        )
        configuration_scope = ConfigurationScope(projects=[project], folders=[])
        exclusion_filters = [
            ExclusionFilter(filter="resource.type=test", name="test-exclusion")
        ]

        create_log_sinks(
            step_reporter,
            "default-project",
            configuration_scope,
            inclusion_filter="severity>=ERROR",
            exclusion_filters=exclusion_filters,
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            f"logging sinks list --project test-project --filter name={LOG_SINK_NAME}",
        )
        self.assertEqual(
            actual_commands[1],
            f"logging sinks create {LOG_SINK_NAME} pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} --project test-project '--log-filter=severity>=ERROR' --exclusion=name=test-exclusion,filter=resource.type=test --quiet",
        )
        self.assertEqual(
            actual_commands[2],
            f"logging sinks describe {LOG_SINK_NAME} --project test-project",
        )
        self.assertEqual(
            actual_commands[3],
            f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} --project default-project --member serviceAccount:test-writer@gcp-sa.iam.gserviceaccount.com --role roles/pubsub.publisher",
        )


class TestCreateDataflowJob(unittest.TestCase):
    """Test the create_dataflow_job function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.os.environ.get")
    def test_create_dataflow_job_creates_new_job(self, mock_env_get, mock_gcloud):
        """Test creating a new Dataflow job."""
        mock_env_get.return_value = "datadoghq.com"

        mock_gcloud.side_effect = [
            None,
            [],
            None,
        ]

        step_reporter = Mock()

        dataflow_config = DataflowConfiguration(
            is_dataflow_prime_enabled=False,
            is_streaming_engine_enabled=False,
            max_workers=5,
            num_workers=1,
            machine_type="n1-standard-1",
            parallelism=1,
            batch_size=100,
        )

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            dataflow_config,
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        expected_params = (
            f"inputSubscription=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
            f"url=https://http-intake.logs.datadoghq.com,"
            f"apiKeySource=SECRET_MANAGER,"
            f"apiKeySecretId=projects/test-project/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
            f"outputDeadletterTopic=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID},"
            f"batchCount=100,"
            f"parallelism=1"
        )

        self.assertEqual(len(actual_commands), 3)
        self.assertEqual(
            actual_commands[0],
            "services enable dataflow.googleapis.com --project test-project --quiet",
        )
        self.assertEqual(
            actual_commands[1],
            f"dataflow jobs list --project test-project --region us-central1 --filter 'name={DATAFLOW_JOB_NAME} AND state=RUNNING'",
        )
        self.assertEqual(
            actual_commands[2],
            f"dataflow jobs run {DATAFLOW_JOB_NAME} --gcs-location gs://dataflow-templates-us-central1/latest/Cloud_PubSub_to_Datadog --region us-central1 --project test-project --service-account-email test-sa@project.iam.gserviceaccount.com --staging-location gs://dataflow-temp-test-project --max-workers 5 --num-workers 1 --parameters {expected_params} --worker-machine-type n1-standard-1",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_dataflow_job_uses_existing(self, mock_gcloud):
        """Test skipping creation when job already exists."""

        mock_gcloud.side_effect = [
            None,
            [{"name": "pubsub-to-datadog-job", "state": "RUNNING"}],
        ]

        step_reporter = Mock()

        dataflow_config = DataflowConfiguration(is_dataflow_prime_enabled=False)

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            dataflow_config,
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 2)
        self.assertEqual(
            actual_commands[0],
            "services enable dataflow.googleapis.com --project test-project --quiet",
        )
        self.assertEqual(
            actual_commands[1],
            f"dataflow jobs list --project test-project --region us-central1 --filter 'name={DATAFLOW_JOB_NAME} AND state=RUNNING'",
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.os.environ.get")
    def test_create_dataflow_job_with_prime_enabled(self, mock_env_get, mock_gcloud):
        """Test creating a Dataflow job with Prime enabled."""
        mock_env_get.return_value = "datadoghq.com"

        mock_gcloud.side_effect = [
            None,
            [],
            None,
        ]

        step_reporter = Mock()

        dataflow_config = DataflowConfiguration(
            is_dataflow_prime_enabled=True,
            is_streaming_engine_enabled=False,
            max_workers=5,
            num_workers=1,
            machine_type="n1-standard-1",
            parallelism=1,
            batch_size=100,
        )

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            dataflow_config,
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        expected_params = (
            f"inputSubscription=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
            f"url=https://http-intake.logs.datadoghq.com,"
            f"apiKeySource=SECRET_MANAGER,"
            f"apiKeySecretId=projects/test-project/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
            f"outputDeadletterTopic=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID},"
            f"batchCount=100,"
            f"parallelism=1"
        )

        self.assertEqual(len(actual_commands), 3)
        self.assertEqual(
            actual_commands[0],
            "services enable dataflow.googleapis.com --project test-project --quiet",
        )
        self.assertEqual(
            actual_commands[1],
            f"dataflow jobs list --project test-project --region us-central1 --filter 'name={DATAFLOW_JOB_NAME} AND state=RUNNING'",
        )
        self.assertEqual(
            actual_commands[2],
            f"dataflow jobs run {DATAFLOW_JOB_NAME} --gcs-location gs://dataflow-templates-us-central1/latest/Cloud_PubSub_to_Datadog --region us-central1 --project test-project --service-account-email test-sa@project.iam.gserviceaccount.com --staging-location gs://dataflow-temp-test-project --max-workers 5 --num-workers 1 --parameters {expected_params} --additional-experiments enable_prime",
        )


if __name__ == "__main__":
    unittest.main()
