# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.


from ..shared.gcloud import gcloud
from ..shared.requests import dd_request
import json
import tempfile
from typing import Any
from ..shared.models import ConfigurationScope
import os

ROLES_TO_ADD: list[str] = [
    "roles/dataflow.admin",
    "roles/dataflow.worker",
    "roles/pubsub.viewer",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/storage.objectAdmin",
]

PUBSUB_TOPIC_ID: str = "export-logs-to-datadog"
PUBSUB_DEAD_LETTER_TOPIC_ID: str = "export-failed-logs-to-datadog"
SECRET_MANAGER_NAME: str = "gcp-dataflow-logs-api-key"


def create_topics_with_subscription(
    project_id: str,
) -> None:
    """Create a Pub/Sub topic with a subscription."""
    for topic_id in [PUBSUB_TOPIC_ID, PUBSUB_DEAD_LETTER_TOPIC_ID]:
        subscription_id = f"{topic_id}-subscription"
        topic_full_name = f"projects/{project_id}/topics/{topic_id}"

        topic_search = gcloud(
            f"pubsub topics list --project={project_id} --filter='name:{topic_full_name}'",
        )
        if len(topic_search) != 1:
            gcloud(f"pubsub topics create {topic_id} --project={project_id}")

        subscription_search = gcloud(
            f"pubsub subscriptions list --project={project_id} --filter='name:projects/{project_id}/subscriptions/{subscription_id}'"
        )

        if len(subscription_search) != 1:
            gcloud(
                f"pubsub subscriptions create {subscription_id} --topic={topic_id} --project={project_id}"
            )
            return

        if subscription_search[0].get("topic") != topic_full_name:
            gcloud(
                f"pubsub subscriptions delete {subscription_id} --project={project_id}"
            )
            gcloud(
                f"pubsub subscriptions create {subscription_id} --topic={topic_id} --project={project_id}"
            )


def create_secret_manager_entry(project_id: str, service_account_email: str) -> None:
    """Create secret manager entries for the given project."""
    secrets = gcloud(
        f"secrets list --project={project_id} --filter='name~{SECRET_MANAGER_NAME}'"
    )
    if len(secrets) == 1:
        return

    api_key = create_datadog_logs_api_key()

    gcloud(f"secrets create {SECRET_MANAGER_NAME} --project={project_id}")
    gcloud(
        f'secrets add-iam-policy-binding {SECRET_MANAGER_NAME} \
        --project={project_id} \
        --member="serviceAccount:{service_account_email}" \
        --role="roles/secretmanager.secretAccessor" \
        --condition=None \
        --quiet'
    )
    with tempfile.NamedTemporaryFile(mode="w") as tmp_file:
        tmp_file.write(api_key)
        tmp_file.flush()
        gcloud(
            f"secrets versions add {SECRET_MANAGER_NAME} --project={project_id} --data-file={tmp_file.name}"
        )


def create_datadog_logs_api_key() -> str:
    """Create a Datadog logs API key."""
    response, status = dd_request(
        "GET",
        f"/api/v2/api_keys?filter={SECRET_MANAGER_NAME}",
    )
    if status != 200:
        raise RuntimeError(f"Failed to get API key: {response}")

    json_response = json.loads(response)
    data: list[dict[str, Any]] = list(
        filter(
            lambda key: key.get("attributes", {}).get("name") == SECRET_MANAGER_NAME,
            json_response.get("data", []),
        )
    )

    if len(data) > 0:
        api_key_id = data[0].get("id")
        response, status = dd_request(
            "GET",
            f"/api/v2/api_keys/{api_key_id}",
        )
        if status != 200:
            raise RuntimeError(f"Failed to get API key: {response}")

        json_response = json.loads(response)
        return json_response.get("data", {}).get("attributes", {}).get("key")

    response, status = dd_request(
        "POST",
        "/api/v2/api_keys",
        {
            "data": {
                "type": "api_key",
                "attributes": {
                    "name": SECRET_MANAGER_NAME,
                },
                "type": "api_keys",
            },
        },
    )
    if status != 201:
        raise RuntimeError(f"Failed to create API key: {response}")

    json_response = json.loads(response)
    return json_response.get("data", {}).get("attributes", {}).get("key")


def assign_required_dataflow_roles(service_account_email: str, project_id: str) -> None:
    """Assign the required roles to the service account."""
    for role in ROLES_TO_ADD:
        gcloud(
            f'projects add-iam-policy-binding "{project_id}" \
            --member="serviceAccount:{service_account_email}" \
            --role="{role}" \
            --condition=None \
            --quiet \
            '
        )


def create_log_sinks(
    default_project_id: str, configuration_scope: ConfigurationScope
) -> None:
    """Create log sinks for the given project."""
    log_sink_name: str = "datadog-log-sink"

    for folder in configuration_scope.folders:
        matched_log_sinks = gcloud(
            f"logging sinks list --folder={folder.id} --filter='name:{log_sink_name}'"
        )
        if len(matched_log_sinks) == 1:
            continue

        gcloud(
            f"logging sinks create {log_sink_name} \
            pubsub.googleapis.com/projects/{default_project_id}/topics/{PUBSUB_TOPIC_ID} \
            --folder={folder.id} \
            --include-children \
            --quiet"
        )

        sink_info = gcloud(
            f"logging sinks describe {log_sink_name} --folder={folder.id}",
            *["writerIdentity"],
        )
        if writer_identity := sink_info.get("writerIdentity"):
            gcloud(
                f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} \
                --project={default_project_id} \
                --member={writer_identity} \
                --role=roles/pubsub.publisher"
            )

    for project in configuration_scope.projects:
        matched_log_sinks = gcloud(
            f"logging sinks list --project={project.id} --filter='name:{log_sink_name}'"
        )
        if len(matched_log_sinks) == 1:
            continue

        gcloud(
            f"logging sinks create {log_sink_name} \
            pubsub.googleapis.com/projects/{default_project_id}/topics/{PUBSUB_TOPIC_ID} \
            --project={project.id} \
            --quiet"
        )

        sink_info = gcloud(
            f"logging sinks describe {log_sink_name} --project={project.id}",
            *["writerIdentity"],
        )
        if writer_identity := sink_info.get("writerIdentity"):
            gcloud(
                f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} \
                --project={default_project_id} \
                --member={writer_identity} \
                --role=roles/pubsub.publisher"
            )


def create_dataflow_job(
    project_id: str,
    service_account_email: str,
    region: str,
) -> None:
    """Create a Dataflow job."""

    dataflow_job_name: str = "pubsub-to-datadog-job"
    matched_dataflow_jobs = gcloud(
        f"dataflow jobs list --project={project_id} --region={region} "
        f"--filter='name:{dataflow_job_name} AND NOT (state=DONE OR state=FAILED OR state=CANCELLED OR state=DRAINED OR state=UPDATED)'"
    )
    if len(matched_dataflow_jobs) >= 1:
        return

    parameters = (
        f"inputSubscription=projects/{project_id}/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
        f"url=https://http-intake.logs.{os.environ.get('DD_SITE')}"
        f"apiKeySource=SECRET_MANAGER,"
        f"apiKeySecretId=projects/{project_id}/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
        f"outputDeadletterTopic=projects/{project_id}/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"
    )

    gcloud(
        f"dataflow jobs run {dataflow_job_name} \
        --gcs-location=gs://dataflow-templates-{region}/latest/Cloud_PubSub_to_Datadog \
        --region={region} \
        --project={project_id} \
        --service-account-email={service_account_email} \
        --parameters {parameters}"
    )
