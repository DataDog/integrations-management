# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import Mock, call, patch

from gcp_log_forwarding_quickstart.dataflow_configuration import (
    PUBSUB_DEAD_LETTER_TOPIC_ID,
    PUBSUB_TOPIC_ID,
    ROLES_TO_ADD,
    SECRET_MANAGER_NAME,
    assign_required_dataflow_roles,
    create_datadog_logs_api_key,
    create_dataflow_job,
    create_log_sinks,
    create_secret_manager_entry,
    create_topics_with_subscription,
)
from gcp_log_forwarding_quickstart.models import ExclusionFilter
from gcp_shared.models import ConfigurationScope, Folder, Project


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
            [],
            None,
            [],
            None,
        ]

        step_reporter = Mock()

        create_topics_with_subscription(step_reporter, "test-project")

        # Verify all calls were made in sequence (both topics and subscriptions)
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"pubsub topics list --project=test-project --filter='name:projects/test-project/topics/{PUBSUB_TOPIC_ID}'"
                ),
                call(f"pubsub topics create {PUBSUB_TOPIC_ID} --project=test-project"),
                call(
                    f"pubsub subscriptions list --project=test-project --filter='name:projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription'"
                ),
                call(
                    f"pubsub subscriptions create {PUBSUB_TOPIC_ID}-subscription --topic={PUBSUB_TOPIC_ID} --project=test-project"
                ),
                call(
                    f"pubsub topics list --project=test-project --filter='name:projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}'"
                ),
                call(
                    f"pubsub topics create {PUBSUB_DEAD_LETTER_TOPIC_ID} --project=test-project"
                ),
                call(
                    f"pubsub subscriptions list --project=test-project --filter='name:projects/test-project/subscriptions/{PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription'"
                ),
                call(
                    f"pubsub subscriptions create {PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription --topic={PUBSUB_DEAD_LETTER_TOPIC_ID} --project=test-project"
                ),
            ]
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_topics_with_subscription_uses_existing_topic(self, mock_gcloud):
        """Test using an existing topic."""

        mock_gcloud.side_effect = [
            [{"name": f"projects/test-project/topics/{PUBSUB_TOPIC_ID}"}],
            [{"topic": f"projects/test-project/topics/{PUBSUB_TOPIC_ID}"}],
            [{"name": f"projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"}],
            [{"topic": f"projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"}],
        ]

        step_reporter = Mock()

        create_topics_with_subscription(step_reporter, "test-project")

        # Verify only checks were made, no creation
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"pubsub topics list --project=test-project --filter='name:projects/test-project/topics/{PUBSUB_TOPIC_ID}'"
                ),
                call(
                    f"pubsub subscriptions list --project=test-project --filter='name:projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription'"
                ),
                call(
                    f"pubsub topics list --project=test-project --filter='name:projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}'"
                ),
                call(
                    f"pubsub subscriptions list --project=test-project --filter='name:projects/test-project/subscriptions/{PUBSUB_DEAD_LETTER_TOPIC_ID}-subscription'"
                ),
            ]
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
            [{"name": correct_dead_letter_topic}],
            [{"topic": correct_dead_letter_topic}],
        ]

        step_reporter = Mock()

        create_topics_with_subscription(step_reporter, "test-project")

        # Verify subscription was deleted and recreated
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"pubsub subscriptions delete {PUBSUB_TOPIC_ID}-subscription --project=test-project"
                ),
                call(
                    f"pubsub subscriptions create {PUBSUB_TOPIC_ID}-subscription --topic={PUBSUB_TOPIC_ID} --project=test-project"
                ),
            ]
        )


class TestCreateSecretManagerEntry(unittest.TestCase):
    """Test the create_secret_manager_entry function."""

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.create_datadog_logs_api_key"
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

        # Verify API key was not created
        mock_create_api_key.assert_not_called()

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.create_datadog_logs_api_key"
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
        mock_gcloud.assert_has_calls(
            [call(f"secrets create {SECRET_MANAGER_NAME} --project=test-project")]
        )

    @patch(
        "gcp_log_forwarding_quickstart.dataflow_configuration.create_datadog_logs_api_key"
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

        # Verify version was added with the temp file
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"secrets versions add {SECRET_MANAGER_NAME} --project=test-project --data-file=/tmp/test"
                )
            ]
        )


class TestCreateDatadogLogsApiKey(unittest.TestCase):
    """Test the create_datadog_logs_api_key function."""

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_create_datadog_logs_api_key_uses_existing(self, mock_dd_request):
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

        result = create_datadog_logs_api_key()

        self.assertEqual(result, "existing-api-key-value")

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_create_datadog_logs_api_key_creates_new(self, mock_dd_request):
        """Test creating a new API key."""
        mock_dd_request.side_effect = [
            (json.dumps({"data": []}), 200),
            (
                json.dumps({"data": {"attributes": {"key": "new-api-key-value"}}}),
                201,
            ),
        ]

        result = create_datadog_logs_api_key()

        self.assertEqual(result, "new-api-key-value")

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.dd_request")
    def test_create_datadog_logs_api_key_get_error(self, mock_dd_request):
        """Test error handling when getting keys fails."""
        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        with self.assertRaises(RuntimeError) as ctx:
            create_datadog_logs_api_key()

        self.assertIn("Failed to get API key", str(ctx.exception))


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

        # Verify all roles were assigned with exact calls
        expected_calls = [
            call(
                f'projects add-iam-policy-binding "test-project" \
            --member="serviceAccount:test-sa@project.iam.gserviceaccount.com" \
            --role="{role}" \
            --condition=None \
            --quiet \
            '
            )
            for role in ROLES_TO_ADD
        ]
        mock_gcloud.assert_has_calls(expected_calls)


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

        # Verify sink was created with exact command
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"logging sinks create datadog-log-sink \
            pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} \
            --project=test-project \
            --quiet"
                )
            ]
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

        # Verify sink was created with --include-children flag
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"logging sinks create datadog-log-sink \
            pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} \
            --folder=folder123 \
            --include-children \
            --quiet"
                )
            ]
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_log_sinks_uses_existing(self, mock_gcloud):
        """Test skipping creation when sink already exists."""

        mock_gcloud.return_value = [{"name": "datadog-log-sink"}]

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

        # Only one call (the check), no create
        mock_gcloud.assert_has_calls(
            [
                call(
                    "logging sinks list --project=test-project --filter='name:datadog-log-sink'"
                )
            ]
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

        # Verify filters were included in the exact call
        mock_gcloud.assert_has_calls(
            [
                call(
                    f"logging sinks create datadog-log-sink \
            pubsub.googleapis.com/projects/default-project/topics/{PUBSUB_TOPIC_ID} \
            --project=test-project --log-filter='severity>=ERROR' --exclusion=name='test-exclusion',filter='resource.type=test' \
            --quiet"
                )
            ]
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

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            False,
        )

        # Verify API was enabled and job was created
        expected_params = (
            f"inputSubscription=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
            f"url=https://http-intake.logs.datadoghq.com,"
            f"apiKeySource=SECRET_MANAGER,"
            f"apiKeySecretId=projects/test-project/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
            f"outputDeadletterTopic=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"
        )
        mock_gcloud.assert_has_calls(
            [
                call(
                    "services enable dataflow.googleapis.com \
                    --project=test-project \
                    --quiet"
                ),
                call(
                    "dataflow jobs list --project=test-project --region=us-central1 --filter='name:pubsub-to-datadog-job AND NOT (state=DONE OR state=FAILED OR state=CANCELLED OR state=DRAINED OR state=UPDATED)'"
                ),
                call(
                    f"dataflow jobs run pubsub-to-datadog-job \
        --gcs-location=gs://dataflow-templates-us-central1/latest/Cloud_PubSub_to_Datadog \
        --region=us-central1 \
        --project=test-project \
        --service-account-email=test-sa@project.iam.gserviceaccount.com \
        --parameters {expected_params}"
                ),
            ]
        )

    @patch("gcp_log_forwarding_quickstart.dataflow_configuration.gcloud")
    def test_create_dataflow_job_uses_existing(self, mock_gcloud):
        """Test skipping creation when job already exists."""

        mock_gcloud.side_effect = [
            None,
            [{"name": "pubsub-to-datadog-job", "state": "RUNNING"}],
        ]

        step_reporter = Mock()

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            False,
        )

        # Verify API was enabled and existing job was checked, no create
        mock_gcloud.assert_has_calls(
            [
                call(
                    "services enable dataflow.googleapis.com \
                    --project=test-project \
                    --quiet"
                ),
                call(
                    "dataflow jobs list --project=test-project --region=us-central1 --filter='name:pubsub-to-datadog-job AND NOT (state=DONE OR state=FAILED OR state=CANCELLED OR state=DRAINED OR state=UPDATED)'"
                ),
            ]
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

        create_dataflow_job(
            step_reporter,
            "test-project",
            "test-sa@project.iam.gserviceaccount.com",
            "us-central1",
            True,
        )

        expected_params = (
            f"inputSubscription=projects/test-project/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
            f"url=https://http-intake.logs.datadoghq.com,"
            f"apiKeySource=SECRET_MANAGER,"
            f"apiKeySecretId=projects/test-project/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
            f"outputDeadletterTopic=projects/test-project/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"
        )
        mock_gcloud.assert_has_calls(
            [
                call(
                    "services enable dataflow.googleapis.com \
                    --project=test-project \
                    --quiet"
                ),
                call(
                    "dataflow jobs list --project=test-project --region=us-central1 --filter='name:pubsub-to-datadog-job AND NOT (state=DONE OR state=FAILED OR state=CANCELLED OR state=DRAINED OR state=UPDATED)'"
                ),
                call(
                    f"dataflow jobs run pubsub-to-datadog-job \
        --gcs-location=gs://dataflow-templates-us-central1/latest/Cloud_PubSub_to_Datadog \
        --region=us-central1 \
        --project=test-project \
        --service-account-email=test-sa@project.iam.gserviceaccount.com \
        --parameters {expected_params} --additional-experiments=enable_prime"
                ),
            ]
        )


if __name__ == "__main__":
    unittest.main()
