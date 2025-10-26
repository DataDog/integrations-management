# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.


import json
import os
import tempfile
from typing import Any

from gcp_shared.gcloud import gcloud
from gcp_shared.models import ConfigurationScope
from gcp_shared.reporter import StepStatusReporter
from gcp_shared.requests import dd_request

from .models import ExclusionFilter

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
    step_reporter: StepStatusReporter,
    project_id: str,
) -> None:
    """Create a Pub/Sub topic with a subscription."""
    for topic_id in [PUBSUB_TOPIC_ID, PUBSUB_DEAD_LETTER_TOPIC_ID]:
        subscription_id = f"{topic_id}-subscription"
        topic_full_name = f"projects/{project_id}/topics/{topic_id}"

        step_reporter.report(
            message=f"Checking for Pub/Sub topic '{topic_id}' in project '{project_id}'..."
        )

        topic_search = gcloud(
            f"pubsub topics list --project={project_id} --filter='name:{topic_full_name}'",
        )
        if len(topic_search) != 1:
            step_reporter.report(
                message=f"Creating Pub/Sub topic '{topic_id}' in project '{project_id}'..."
            )
            gcloud(f"pubsub topics create {topic_id} --project={project_id}")

        step_reporter.report(
            message=f"Checking for subscription '{subscription_id}' in project '{project_id}'..."
        )

        subscription_search = gcloud(
            f"pubsub subscriptions list --project={project_id} --filter='name:projects/{project_id}/subscriptions/{subscription_id}'"
        )

        if len(subscription_search) != 1:
            step_reporter.report(
                message=f"Creating subscription '{subscription_id}' for topic '{topic_id}'..."
            )
            gcloud(
                f"pubsub subscriptions create {subscription_id} --topic={topic_id} --project={project_id}"
            )
            continue

        if subscription_search[0].get("topic") != topic_full_name:
            step_reporter.report(
                message=f"Recreating subscription '{subscription_id}' for topic '{topic_id}'..."
            )
            gcloud(
                f"pubsub subscriptions delete {subscription_id} --project={project_id}"
            )
            gcloud(
                f"pubsub subscriptions create {subscription_id} --topic={topic_id} --project={project_id}"
            )


def create_secret_manager_entry(
    step_reporter: StepStatusReporter, project_id: str, service_account_email: str
) -> None:
    """Create secret manager entries for the given project."""
    step_reporter.report(
        message=f"Checking for secret '{SECRET_MANAGER_NAME}' in project '{project_id}'..."
    )

    secrets = gcloud(
        f"secrets list --project={project_id} --filter='name~{SECRET_MANAGER_NAME}'"
    )
    if len(secrets) == 1:
        step_reporter.report(
            message=f"Updating IAM permissions for existing secret '{SECRET_MANAGER_NAME}'..."
        )
        gcloud(
            f'secrets add-iam-policy-binding {SECRET_MANAGER_NAME} \
            --project={project_id} \
            --member="serviceAccount:{service_account_email}" \
            --role="roles/secretmanager.secretAccessor" \
            --condition=None \
            --quiet'
        )
        secret_versions = gcloud(
            f"secrets versions list {SECRET_MANAGER_NAME} --project={project_id}"
        )
        if len(secret_versions) > 0:
            step_reporter.report(
                message=f"Secret '{SECRET_MANAGER_NAME}' already exists with version"
            )
            return

    step_reporter.report(
        message=f"Creating Datadog logs API key '{SECRET_MANAGER_NAME}'..."
    )
    api_key = create_datadog_logs_api_key()

    if len(secrets) == 0:
        step_reporter.report(
            message=f"Creating secret '{SECRET_MANAGER_NAME}' in project '{project_id}'..."
        )
        gcloud(f"secrets create {SECRET_MANAGER_NAME} --project={project_id}")

    step_reporter.report(
        message=f"Setting IAM permissions for secret '{SECRET_MANAGER_NAME}'..."
    )
    gcloud(
        f'secrets add-iam-policy-binding {SECRET_MANAGER_NAME} \
        --project={project_id} \
        --member="serviceAccount:{service_account_email}" \
        --role="roles/secretmanager.secretAccessor" \
        --condition=None \
        --quiet'
    )

    step_reporter.report(message=f"Adding API key to secret '{SECRET_MANAGER_NAME}'...")
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
                "type": "api_keys",
                "attributes": {
                    "name": SECRET_MANAGER_NAME,
                },
            },
        },
    )
    if status != 201:
        raise RuntimeError(f"Failed to create API key: {response}")

    json_response = json.loads(response)
    return json_response.get("data", {}).get("attributes", {}).get("key")


def assign_required_dataflow_roles(
    step_reporter: StepStatusReporter, service_account_email: str, project_id: str
) -> None:
    """Assign the required roles to the service account."""
    for role in ROLES_TO_ADD:
        step_reporter.report(
            message=f"Assigning role [{role}] to service account '{service_account_email}' in project '{project_id}'..."
        )
        gcloud(
            f'projects add-iam-policy-binding "{project_id}" \
            --member="serviceAccount:{service_account_email}" \
            --role="{role}" \
            --condition=None \
            --quiet \
            '
        )


def create_log_sinks(
    step_reporter: StepStatusReporter,
    default_project_id: str,
    configuration_scope: ConfigurationScope,
    inclusion_filter: str,
    exclusion_filters: list[ExclusionFilter],
) -> None:
    """Create log sinks for the given project."""
    log_sink_name: str = "datadog-log-sink"

    filter_args = ""
    if inclusion_filter:
        filter_args += f" --log-filter='{inclusion_filter}'"

    exclusion_args = ""
    for exclusion in exclusion_filters:
        exclusion_parts = [f"name='{exclusion.name}'", f"filter='{exclusion.filter}'"]
        exclusion_args += f" --exclusion={','.join(exclusion_parts)}"

    for folder in configuration_scope.folders:
        step_reporter.report(
            message=f"Checking for log sink '{log_sink_name}' in folder '{folder.name}'..."
        )
        matched_log_sinks = gcloud(
            f"logging sinks list --folder={folder.id} --filter='name:{log_sink_name}'"
        )
        if len(matched_log_sinks) == 1:
            step_reporter.report(
                message=f"Log sink '{log_sink_name}' already exists in folder '{folder.name}'"
            )
            continue

        step_reporter.report(
            message=f"Creating log sink '{log_sink_name}' in folder '{folder.name}'..."
        )
        gcloud(
            f"logging sinks create {log_sink_name} \
            pubsub.googleapis.com/projects/{default_project_id}/topics/{PUBSUB_TOPIC_ID} \
            --folder={folder.id} \
            --include-children{filter_args}{exclusion_args} \
            --quiet"
        )

        sink_info = gcloud(
            f"logging sinks describe {log_sink_name} --folder={folder.id}",
            *["writerIdentity"],
        )
        if writer_identity := sink_info.get("writerIdentity"):
            step_reporter.report(
                message=f"Granting publish permissions to writer identity in folder '{folder.name}'..."
            )
            gcloud(
                f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} \
                --project={default_project_id} \
                --member={writer_identity} \
                --role=roles/pubsub.publisher"
            )

    for project in configuration_scope.projects:
        step_reporter.report(
            message=f"Checking for log sink '{log_sink_name}' in project '{project.name}'..."
        )
        matched_log_sinks = gcloud(
            f"logging sinks list --project={project.id} --filter='name:{log_sink_name}'"
        )
        if len(matched_log_sinks) == 1:
            step_reporter.report(
                message=f"Log sink '{log_sink_name}' already exists in project '{project.name}'"
            )
            continue

        step_reporter.report(
            message=f"Creating log sink '{log_sink_name}' in project '{project.name}'..."
        )
        gcloud(
            f"logging sinks create {log_sink_name} \
            pubsub.googleapis.com/projects/{default_project_id}/topics/{PUBSUB_TOPIC_ID} \
            --project={project.id}{filter_args}{exclusion_args} \
            --quiet"
        )

        sink_info = gcloud(
            f"logging sinks describe {log_sink_name} --project={project.id}",
            *["writerIdentity"],
        )
        if writer_identity := sink_info.get("writerIdentity"):
            step_reporter.report(
                message=f"Granting publish permissions to writer identity in project '{project.name}'..."
            )
            gcloud(
                f"pubsub topics add-iam-policy-binding {PUBSUB_TOPIC_ID} \
                --project={default_project_id} \
                --member={writer_identity} \
                --role=roles/pubsub.publisher"
            )


def create_dataflow_job(
    step_reporter: StepStatusReporter,
    project_id: str,
    service_account_email: str,
    region: str,
    is_dataflow_prime_enabled: bool,
) -> None:
    """Create a Dataflow job."""

    step_reporter.report(message=f"Enabling Dataflow API for project '{project_id}'")

    gcloud(
        f"services enable dataflow.googleapis.com \
                    --project={project_id} \
                    --quiet"
    )

    dataflow_job_name: str = "pubsub-to-datadog-job"

    step_reporter.report(
        message=f"Checking for existing Dataflow job '{dataflow_job_name}' in project '{project_id}'..."
    )

    matched_dataflow_jobs = gcloud(
        f"dataflow jobs list --project={project_id} --region={region} "
        f"--filter='name:{dataflow_job_name} AND NOT (state=DONE OR state=FAILED OR state=CANCELLED OR state=DRAINED OR state=UPDATED)'"
    )
    if len(matched_dataflow_jobs) >= 1:
        step_reporter.report(
            message=f"Dataflow job '{dataflow_job_name}' already exists and is running"
        )
        return

    step_reporter.report(
        message=f"Creating Dataflow job '{dataflow_job_name}' in region '{region}'..."
    )

    parameters = (
        f"inputSubscription=projects/{project_id}/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
        f"url=https://http-intake.logs.{os.environ.get('DD_SITE')},"
        f"apiKeySource=SECRET_MANAGER,"
        f"apiKeySecretId=projects/{project_id}/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
        f"outputDeadletterTopic=projects/{project_id}/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID}"
    )

    dataflow_create_job_command = f"dataflow jobs run {dataflow_job_name} \
        --gcs-location=gs://dataflow-templates-{region}/latest/Cloud_PubSub_to_Datadog \
        --region={region} \
        --project={project_id} \
        --service-account-email={service_account_email} \
        --parameters {parameters}"

    if is_dataflow_prime_enabled:
        step_reporter.report(message="Enabling Dataflow Prime for the job...")
        dataflow_create_job_command += " --additional-experiments=enable_prime"

    gcloud(dataflow_create_job_command)

    step_reporter.report(
        message=f"Successfully created Dataflow job '{dataflow_job_name}'"
    )
