# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.


import json
import os
import tempfile
from typing import Any, Literal, Union

from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.models import ConfigurationScope
from gcp_shared.reporter import StepStatusReporter
from gcp_shared.requests import dd_request

from .models import DataflowConfiguration, ExclusionFilter

RESOURCE_NAME_PREFIX: str = "export-logs-to-datadog"
BUCKET_PREFIX: str = "dataflow-temp"
PUBSUB_TOPIC_ID: str = f"{RESOURCE_NAME_PREFIX}"
PUBSUB_DEAD_LETTER_TOPIC_ID: str = f"{RESOURCE_NAME_PREFIX}-dlq"
SECRET_MANAGER_NAME: str = f"{RESOURCE_NAME_PREFIX}-api-key"
DATAFLOW_JOB_NAME: str = f"{RESOURCE_NAME_PREFIX}-job"
LOG_SINK_NAME: str = f"{RESOURCE_NAME_PREFIX}-log-sink"


def create_dataflow_staging_bucket(
    step_reporter: StepStatusReporter,
    project_id: str,
    service_account_email: str,
    region: str,
) -> None:
    """Create a Dataflow staging bucket."""
    # Bucket names must be globally unique, so we append project_id for uniqueness.
    # This differs from other resources since we don't use the resource name prefix.
    # This is intentional to ensure we stay within the maximum length of 63 characters for a bucket name.
    FULL_BUCKET_NAME = f"{BUCKET_PREFIX}-{project_id}"

    bucket_search = gcloud(
        GcloudCmd("storage buckets", "list")
        .param("--project", project_id)
        .param("--filter", f"name={FULL_BUCKET_NAME}")
    )
    if len(bucket_search) == 1:
        step_reporter.report(
            message=f"Dataflow staging bucket '{FULL_BUCKET_NAME}' already exists, granting storage permissions to service account '{service_account_email}'..."
        )

        gcloud(
            GcloudCmd("storage buckets", "add-iam-policy-binding")
            .arg(FULL_BUCKET_NAME)
            .param("--member", f"serviceAccount:{service_account_email}")
            .param("--role", "roles/storage.objectAdmin")
        )
        return

    step_reporter.report(
        message=f"Creating Dataflow staging bucket '{FULL_BUCKET_NAME}' in region '{region}'..."
    )

    gcloud(
        GcloudCmd("storage buckets", "create")
        .arg(f"gs://{FULL_BUCKET_NAME}")
        .param("--project", project_id)
        .param("--location", region)
        .flag("--uniform-bucket-level-access")
        .param("--soft-delete-duration", "0s")
    )

    step_reporter.report(
        message=f"Granting storage permissions to service account '{service_account_email}' for bucket '{FULL_BUCKET_NAME}'..."
    )
    gcloud(
        GcloudCmd("storage buckets", "add-iam-policy-binding")
        .arg(f"gs://{FULL_BUCKET_NAME}")
        .param("--member", f"serviceAccount:{service_account_email}")
        .param("--role", "roles/storage.objectAdmin")
    )


def create_topics_with_subscription(
    step_reporter: StepStatusReporter,
    project_id: str,
    service_account_email: str,
) -> None:
    """Create a Pub/Sub topic with a subscription."""
    for topic_id in [PUBSUB_TOPIC_ID, PUBSUB_DEAD_LETTER_TOPIC_ID]:
        subscription_id = f"{topic_id}-subscription"
        topic_full_name = f"projects/{project_id}/topics/{topic_id}"

        step_reporter.report(
            message=f"Checking for Pub/Sub topic '{topic_id}' in project '{project_id}'..."
        )

        topic_search = gcloud(
            GcloudCmd("pubsub topics", "list")
            .param("--project", project_id)
            .param("--filter", f"name={topic_full_name}")
        )
        if len(topic_search) != 1:
            step_reporter.report(
                message=f"Creating Pub/Sub topic '{topic_id}' in project '{project_id}'..."
            )
            gcloud(
                GcloudCmd("pubsub topics", "create")
                .arg(topic_id)
                .param("--project", project_id)
            )

        if topic_id == PUBSUB_DEAD_LETTER_TOPIC_ID:
            step_reporter.report(
                message=f"Granting publish permissions to service account '{service_account_email}' for dead letter topic '{topic_id}'..."
            )
            gcloud(
                GcloudCmd("pubsub topics", "add-iam-policy-binding")
                .arg(topic_id)
                .param("--project", project_id)
                .param("--member", f"serviceAccount:{service_account_email}")
                .param("--role", "roles/pubsub.publisher")
            )

        step_reporter.report(
            message=f"Checking for subscription '{subscription_id}' in project '{project_id}'..."
        )

        subscription_search = gcloud(
            GcloudCmd("pubsub subscriptions", "list")
            .param("--project", project_id)
            .param(
                "--filter",
                f"name=projects/{project_id}/subscriptions/{subscription_id}",
            )
        )

        if len(subscription_search) != 1:
            step_reporter.report(
                message=f"Creating subscription '{subscription_id}' for topic '{topic_id}'..."
            )
            gcloud(
                GcloudCmd("pubsub subscriptions", "create")
                .arg(subscription_id)
                .param("--topic", topic_id)
                .param("--project", project_id)
            )
        elif subscription_search[0].get("topic") != topic_full_name:
            step_reporter.report(
                message=f"Recreating subscription '{subscription_id}' for topic '{topic_id}'..."
            )
            gcloud(
                GcloudCmd("pubsub subscriptions", "delete")
                .arg(subscription_id)
                .param("--project", project_id)
            )
            gcloud(
                GcloudCmd("pubsub subscriptions", "create")
                .arg(subscription_id)
                .param("--topic", topic_id)
                .param("--project", project_id)
            )

        step_reporter.report(
            message=f"Granting subscriber and viewer permissions to service account '{service_account_email}' for subscription '{subscription_id}'..."
        )

        for role in ["roles/pubsub.subscriber", "roles/pubsub.viewer"]:
            gcloud(
                GcloudCmd("pubsub subscriptions", "add-iam-policy-binding")
                .arg(subscription_id)
                .param("--project", project_id)
                .param("--member", f"serviceAccount:{service_account_email}")
                .param("--role", role)
            )


def create_secret_manager_entry(
    step_reporter: StepStatusReporter, project_id: str, service_account_email: str
) -> None:
    """Create secret manager entries for the given project."""
    step_reporter.report(
        message=f"Checking for secret '{SECRET_MANAGER_NAME}' in project '{project_id}'..."
    )

    secrets = gcloud(
        GcloudCmd("secrets", "list")
        .param("--project", project_id)
        .param("--filter", f"name~{SECRET_MANAGER_NAME}")
    )
    if len(secrets) == 1:
        step_reporter.report(
            message=f"Updating IAM permissions for existing secret '{SECRET_MANAGER_NAME}'..."
        )
        gcloud(
            GcloudCmd("secrets", "add-iam-policy-binding")
            .arg(SECRET_MANAGER_NAME)
            .param("--project", project_id)
            .param("--member", f"serviceAccount:{service_account_email}")
            .param("--role", "roles/secretmanager.secretAccessor")
            .param("--condition", "None")
            .flag("--quiet")
        )
        secret_versions = gcloud(
            GcloudCmd("secrets versions", "list")
            .arg(SECRET_MANAGER_NAME)
            .param("--project", project_id)
        )
        if len(secret_versions) > 0:
            step_reporter.report(
                message=f"Secret '{SECRET_MANAGER_NAME}' already exists with version"
            )
            return

    step_reporter.report(
        message=f"Creating Datadog logs API key '{SECRET_MANAGER_NAME}'..."
    )

    if len(secrets) == 0:
        step_reporter.report(
            message=f"Creating secret '{SECRET_MANAGER_NAME}' in project '{project_id}'..."
        )
        gcloud(
            GcloudCmd("secrets", "create")
            .arg(SECRET_MANAGER_NAME)
            .param("--project", project_id)
        )

    step_reporter.report(
        message=f"Setting IAM permissions for secret '{SECRET_MANAGER_NAME}'..."
    )
    gcloud(
        GcloudCmd("secrets", "add-iam-policy-binding")
        .arg(SECRET_MANAGER_NAME)
        .param("--project", project_id)
        .param("--member", f"serviceAccount:{service_account_email}")
        .param("--role", "roles/secretmanager.secretAccessor")
        .param("--condition", "None")
        .flag("--quiet")
    )

    api_key = find_or_create_datadog_api_key()
    step_reporter.report(message=f"Adding API key to secret '{SECRET_MANAGER_NAME}'...")
    with tempfile.NamedTemporaryFile(mode="w") as tmp_file:
        tmp_file.write(api_key)
        tmp_file.flush()
        gcloud(
            GcloudCmd("secrets versions", "add")
            .arg(SECRET_MANAGER_NAME)
            .param("--project", project_id)
            .param("--data-file", tmp_file.name)
        )


def find_or_create_datadog_api_key() -> str:
    """Find or create a Datadog API key."""
    response, status = dd_request(
        "GET",
        f"/api/v2/api_keys?filter={SECRET_MANAGER_NAME}",
    )
    if status != 200:
        raise RuntimeError(f"Failed to search API keys: {response}")

    json_response = json.loads(response)
    api_key_info: list[dict[str, Any]] = list(
        filter(
            lambda key: key.get("attributes", {}).get("name") == SECRET_MANAGER_NAME,
            json_response.get("data", []),
        )
    )

    if len(api_key_info) > 0:
        response, status = dd_request(
            "GET",
            f"/api/v2/api_keys/{api_key_info[0].get('id')}",
        )
        if status != 200:
            raise RuntimeError("Failed to get API key")
    else:
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

    return json.loads(response).get("data", {}).get("attributes", {}).get("key")


def assign_required_dataflow_roles(
    step_reporter: StepStatusReporter, service_account_email: str, project_id: str
) -> None:
    """Assign the required roles to the service account."""
    dataflow_worker_role = "roles/dataflow.worker"

    step_reporter.report(
        message=f"Assigning role [{dataflow_worker_role}] to service account '{service_account_email}' in project '{project_id}'..."
    )
    gcloud(
        GcloudCmd("projects", "add-iam-policy-binding")
        .arg(project_id)
        .param("--member", f"serviceAccount:{service_account_email}")
        .param("--role", dataflow_worker_role)
        .param("--condition", "None")
        .flag("--quiet")
    )


def _build_log_sink_cmd(
    action: Union[Literal["create"], Literal["update"]],
    default_project_id: str,
    resource_container_type: str,
    resource_container_id: str,
    filter_args: list[str],
    exclusion_args: list[str],
) -> GcloudCmd:
    """Helper to build a log sink command with common flags."""
    build_log_sink_cmd = (
        GcloudCmd("logging sinks", action)
        .arg(LOG_SINK_NAME)
        .arg(
            f"pubsub.googleapis.com/projects/{default_project_id}/topics/{PUBSUB_TOPIC_ID}"
        )
        .param(f"--{resource_container_type}", resource_container_id)
    )

    if resource_container_type == "folder":
        build_log_sink_cmd.flag("--include-children")

    for arg in filter_args:
        build_log_sink_cmd.flag(arg)

    for arg in exclusion_args:
        build_log_sink_cmd.flag(arg)

    build_log_sink_cmd.flag("--quiet")

    return build_log_sink_cmd


def create_log_sinks(
    step_reporter: StepStatusReporter,
    default_project_id: str,
    configuration_scope: ConfigurationScope,
    inclusion_filter: str,
    exclusion_filters: list[ExclusionFilter],
) -> None:
    """Create log sinks for the given project."""

    filter_args = [] if not inclusion_filter else [f"--log-filter={inclusion_filter}"]
    create_exclusion_args = [
        f"--exclusion=name={exclusion.name},filter={exclusion.filter}"
        for exclusion in exclusion_filters
    ]

    update_exclusion_args = ["--clear-exclusions"] + [
        f"--add-exclusion=name={exclusion.name},filter={exclusion.filter}"
        for exclusion in exclusion_filters
    ]

    for resource_container in [
        *configuration_scope.folders,
        *configuration_scope.projects,
    ]:
        step_reporter.report(
            message=f"Checking for log sink '{LOG_SINK_NAME}' in {resource_container.resource_container_type} '{resource_container.name}'..."
        )
        matched_log_sinks = gcloud(
            GcloudCmd("logging sinks", "list")
            .param(
                f"--{resource_container.resource_container_type}", resource_container.id
            )
            .param("--filter", f"name={LOG_SINK_NAME}")
        )
        if len(matched_log_sinks) == 1:
            step_reporter.report(
                message=f"Updating log sink '{LOG_SINK_NAME}' in {resource_container.resource_container_type} '{resource_container.name}'..."
            )
            update_log_sink_cmd = _build_log_sink_cmd(
                action="update",
                default_project_id=default_project_id,
                resource_container_type=resource_container.resource_container_type,
                resource_container_id=resource_container.id,
                filter_args=filter_args,
                exclusion_args=update_exclusion_args,
            )
            gcloud(update_log_sink_cmd)
            step_reporter.report(
                message=f"Log sink '{LOG_SINK_NAME}' updated in {resource_container.resource_container_type} '{resource_container.name}'"
            )
        else:
            step_reporter.report(
                message=f"Creating log sink '{LOG_SINK_NAME}' in {resource_container.resource_container_type} '{resource_container.name}'..."
            )
            create_log_sink_cmd = _build_log_sink_cmd(
                action="create",
                default_project_id=default_project_id,
                resource_container_type=resource_container.resource_container_type,
                resource_container_id=resource_container.id,
                filter_args=filter_args,
                exclusion_args=create_exclusion_args,
            )
            gcloud(create_log_sink_cmd)

        sink_info = gcloud(
            GcloudCmd("logging sinks", "describe")
            .arg(LOG_SINK_NAME)
            .param(
                f"--{resource_container.resource_container_type}", resource_container.id
            ),
            "writerIdentity",
        )
        if writer_identity := sink_info.get("writerIdentity"):
            step_reporter.report(
                message=f"Granting publish permissions to writer identity in {resource_container.resource_container_type} '{resource_container.name}'..."
            )
            gcloud(
                GcloudCmd("pubsub topics", "add-iam-policy-binding")
                .arg(PUBSUB_TOPIC_ID)
                .param("--project", default_project_id)
                .param("--member", writer_identity)
                .param("--role", "roles/pubsub.publisher")
            )


def create_dataflow_job(
    step_reporter: StepStatusReporter,
    project_id: str,
    service_account_email: str,
    region: str,
    dataflow_configuration: DataflowConfiguration,
) -> None:
    """Create a Dataflow job."""

    step_reporter.report(message=f"Enabling Dataflow API for project '{project_id}'")

    gcloud(
        GcloudCmd("services", "enable")
        .arg("dataflow.googleapis.com")
        .param("--project", project_id)
        .flag("--quiet")
    )

    step_reporter.report(
        message=f"Checking for existing Dataflow job '{DATAFLOW_JOB_NAME}' in project '{project_id}'..."
    )

    matched_dataflow_jobs = gcloud(
        GcloudCmd("dataflow jobs", "list")
        .param("--project", project_id)
        .param("--region", region)
        .param(
            "--filter",
            f"name={DATAFLOW_JOB_NAME} AND state=RUNNING",
        )
    )
    if len(matched_dataflow_jobs) >= 1:
        step_reporter.report(
            message=f"Dataflow job '{DATAFLOW_JOB_NAME}' already exists and is running"
        )
        return

    step_reporter.report(
        message=f"Creating Dataflow job '{DATAFLOW_JOB_NAME}' in region '{region}'..."
    )

    create_dataflow_job_cmd = (
        GcloudCmd("dataflow jobs", "run")
        .arg(DATAFLOW_JOB_NAME)
        .param(
            "--gcs-location",
            f"gs://dataflow-templates-{region}/latest/Cloud_PubSub_to_Datadog",
        )
        .param("--region", region)
        .param("--project", project_id)
        .param("--service-account-email", service_account_email)
        .param("--staging-location", f"gs://{BUCKET_PREFIX}-{project_id}")
        .param("--max-workers", str(dataflow_configuration.max_workers))
        .param("--num-workers", str(dataflow_configuration.num_workers))
        .param(
            "--parameters",
            (
                f"inputSubscription=projects/{project_id}/subscriptions/{PUBSUB_TOPIC_ID}-subscription,"
                f"url=https://http-intake.logs.{os.environ.get('DD_SITE')},"
                f"apiKeySource=SECRET_MANAGER,"
                f"apiKeySecretId=projects/{project_id}/secrets/{SECRET_MANAGER_NAME}/versions/latest,"
                f"outputDeadletterTopic=projects/{project_id}/topics/{PUBSUB_DEAD_LETTER_TOPIC_ID},"
                f"batchCount={dataflow_configuration.batch_size},"
                f"parallelism={dataflow_configuration.parallelism}"
            ),
        )
    )

    if dataflow_configuration.is_dataflow_prime_enabled:
        step_reporter.report(message="Enabling Dataflow Prime for the job...")
        create_dataflow_job_cmd.param("--additional-experiments", "enable_prime")
    elif dataflow_configuration.machine_type:
        step_reporter.report(
            message=f"Setting worker machine type to '{dataflow_configuration.machine_type}'..."
        )
        create_dataflow_job_cmd.param(
            "--worker-machine-type", dataflow_configuration.machine_type
        )

    if dataflow_configuration.is_streaming_engine_enabled:
        step_reporter.report(message="Enabling Streaming Engine for the job...")
        create_dataflow_job_cmd.param(
            "--additional-experiments", "enable_streaming_engine"
        )

    gcloud(create_dataflow_job_cmd)

    step_reporter.report(
        message=f"Successfully created Dataflow job '{DATAFLOW_JOB_NAME}'"
    )
