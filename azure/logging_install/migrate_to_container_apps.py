#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""
Migration script to move LFO control plane tasks from Azure Function Apps (Linux Consumption plan)
to Container App Jobs hosted in the existing deployer Container App Environment.

Designed to run in Azure Cloud Shell. Requires Azure CLI (`az`) to be available and authenticated.

Usage:
    python migrate_to_container_apps.py \
        --control-plane-subscription-id <sub-id> \
        --control-plane-resource-group <rg-name>
"""

import argparse
import json
import logging
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lfo-migration")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMAGE_REGISTRY_URL = "datadoghq.azurecr.io"
NEW_DEPLOYER_IMAGE = f"{IMAGE_REGISTRY_URL}/deployer:latest"
LFO_PUBLIC_STORAGE_ACCOUNT_URL = "https://ddazurelfo.blob.core.windows.net"

# Azure built-in role IDs
MONITORING_READER_ID = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
MONITORING_CONTRIBUTOR_ID = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
STORAGE_READER_AND_DATA_ACCESS_ID = "c12c1c16-33a1-487b-954d-41c89c60f349"
SCALING_CONTRIBUTOR_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"
WEBSITE_CONTRIBUTOR_ID = "de139f84-1756-47ae-9be6-808fbbe84772"

# Function App-only settings that should NOT be carried over to Container App Jobs
FUNCTION_APP_ONLY_SETTINGS = {
    "FUNCTIONS_EXTENSION_VERSION",
    "FUNCTIONS_WORKER_RUNTIME",
    "WEBSITE_CONTENTAZUREFILECONNECTIONSTRING",
    "AzureWebJobsFeatureFlags",
    "WEBSITE_CONTENTSHARE",
    "WEBSITE_RUN_FROM_PACKAGE",
    "APPINSIGHTS_INSTRUMENTATIONKEY",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
}

# Settings that should be passed as secretrefs rather than plain env vars
SECRET_SETTINGS = {"AzureWebJobsStorage": "connection-string", "DD_API_KEY": "dd-api-key"}

# Container App Job resource configuration
JOB_CPU = "0.5"
JOB_MEMORY = "1Gi"
JOB_CRON_EXPRESSION = "*/5 * * * *"
JOB_PAUSED_CRON_EXPRESSION = "59 23 31 2 *"  # Feb 31st — effectively never fires
JOB_REPLICA_TIMEOUT = "300"
JOB_REPLICA_RETRY_LIMIT = "1"

# ---------------------------------------------------------------------------
# Azure CLI helpers
# ---------------------------------------------------------------------------


def az(args: str, can_fail: bool = False) -> str:
    """Run an Azure CLI command and return stdout. Raises on non-zero exit unless can_fail is set."""
    full_command = f"az {args}"
    log.debug("Running: %s", full_command)
    result = subprocess.run(full_command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        if can_fail:
            return ""
        log.error("Command failed: %s", full_command)
        log.error("stderr: %s", result.stderr)
        raise RuntimeError(f"Command failed: {full_command}\nstderr: {result.stderr}")
    return result.stdout


def az_json(args: str, can_fail: bool = False):
    """Run an Azure CLI command and parse JSON output."""
    output = az(args, can_fail=can_fail)
    if not output:
        return None
    return json.loads(output)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


def discover_control_plane_id(sub_id: str, rg: str) -> str:
    """Discover the control plane ID by finding Function Apps named resources-task-* in the resource group."""
    output = az(
        f"functionapp list"
        f" --resource-group {shlex.quote(rg)}"
        f" --subscription {shlex.quote(sub_id)}"
        f" --query \"[?starts_with(name, 'resources-task-')].name\""
        f" --output json"
    )
    names = json.loads(output)
    if not names:
        log.error("No Function App matching 'resources-task-*' found in resource group '%s'.", rg)
        sys.exit(1)
    if len(names) > 1:
        log.error("Multiple resources-task Function Apps found: %s. Expected exactly one.", names)
        sys.exit(1)
    # Control plane ID is the suffix after "resources-task-"
    return names[0].removeprefix("resources-task-")


def discover_resource_group_region(sub_id: str, rg: str) -> str:
    """Get the region of a resource group."""
    output = az(
        f"group show"
        f" --name {shlex.quote(rg)}"
        f" --subscription {shlex.quote(sub_id)}"
        f" --query location"
        f" --output tsv"
    )
    return output.strip()


@dataclass
class MigrationContext:
    """Holds all state needed for the migration."""

    control_plane_sub_id: str
    control_plane_rg: str
    control_plane_region: str
    control_plane_id: str

    # Derived names
    deployer_job_name: str = ""
    env_name: str = ""  # discovered from deployer job, not derived
    resources_task_name: str = ""
    scaling_task_name: str = ""
    diagnostic_settings_task_name: str = ""
    asp_name: str = ""
    storage_account_name: str = ""

    # Discovered from existing Function Apps
    monitored_subscriptions: list[str] = field(default_factory=list)

    # Env vars read from the existing Function Apps
    resources_task_env: dict[str, str] = field(default_factory=dict)
    scaling_task_env: dict[str, str] = field(default_factory=dict)
    diagnostic_task_env: dict[str, str] = field(default_factory=dict)

    # New principal IDs (for role assignment)
    new_resources_principal: str = ""
    new_scaling_principal: str = ""
    new_diagnostic_principal: str = ""

    # Old principal IDs (for cleanup of old role assignments)
    old_resources_principal: str = ""
    old_scaling_principal: str = ""
    old_diagnostic_principal: str = ""

    # Rollback tracking
    created_jobs: list[str] = field(default_factory=list)
    assigned_roles: list[tuple[str, str, str]] = field(default_factory=list)  # (scope, principal_id, role_id)
    function_apps_stopped: bool = False
    deployer_paused: bool = False
    deployer_original_cron: str = ""

    def __post_init__(self):
        self.deployer_job_name = f"deployer-task-{self.control_plane_id}"
        self.resources_task_name = f"resources-task-{self.control_plane_id}"
        self.scaling_task_name = f"scaling-task-{self.control_plane_id}"
        self.diagnostic_settings_task_name = f"diagnostic-settings-task-{self.control_plane_id}"
        self.asp_name = f"control-plane-asp-{self.control_plane_id}"
        self.storage_account_name = f"lfostorage{self.control_plane_id}"

    @property
    def all_subscriptions(self) -> set[str]:
        return {self.control_plane_sub_id, *self.monitored_subscriptions}

    @property
    def control_plane_rg_scope(self) -> str:
        return f"/subscriptions/{self.control_plane_sub_id}/resourceGroups/{self.control_plane_rg}"


# ---------------------------------------------------------------------------
# Phase 1: Discovery & Validation
# ---------------------------------------------------------------------------


def validate_azure_cli():
    """Ensure the Azure CLI is available and authenticated."""
    log.info("Validating Azure CLI authentication...")
    output = az("account show --output json", can_fail=True)
    if not output:
        log.error("Azure CLI is not authenticated. Please run 'az login' first.")
        sys.exit(1)
    log.info("Azure CLI authenticated as: %s", json.loads(output).get("user", {}).get("name", "unknown"))


def validate_function_app_exists(name: str, rg: str, sub_id: str) -> bool:
    """Check if a Function App exists."""
    output = az(
        f"functionapp show --name {shlex.quote(name)} --resource-group {shlex.quote(rg)} --subscription {shlex.quote(sub_id)} --output json",
        can_fail=True,
    )
    return bool(output)


def discover_deployer_environment(deployer_job_name: str, rg: str) -> str:
    """Discover the Container App Environment name from the deployer job's environmentId."""
    output = az(
        f"containerapp job show --name {shlex.quote(deployer_job_name)} --resource-group {shlex.quote(rg)}"
        f" --query properties.environmentId --output tsv",
        can_fail=True,
    )
    env_resource_id = output.strip()
    if not env_resource_id:
        return ""
    # environmentId is a full ARM resource ID; extract the environment name (last segment)
    return env_resource_id.rstrip("/").rsplit("/", 1)[-1]


def container_app_job_exists(job_name: str, rg: str) -> bool:
    """Check if a Container App Job already exists."""
    output = az(
        f"containerapp job show --name {shlex.quote(job_name)} --resource-group {shlex.quote(rg)} --output json",
        can_fail=True,
    )
    return bool(output)


def get_function_app_principal_id(name: str, rg: str, sub_id: str) -> str:
    """Get the system-assigned managed identity principal ID of a Function App."""
    output = az(
        f"functionapp identity show"
        f" --name {shlex.quote(name)}"
        f" --resource-group {shlex.quote(rg)}"
        f" --subscription {shlex.quote(sub_id)}"
        f" --query principalId"
        f" --output tsv"
    )
    return output.strip()


def get_function_app_env_vars(name: str, rg: str, sub_id: str) -> dict[str, str]:
    """Read all app settings from a Function App."""
    output = az(
        f"functionapp config appsettings list --name {shlex.quote(name)} --resource-group {shlex.quote(rg)} --subscription {shlex.quote(sub_id)} --output json"
    )
    settings = json.loads(output)
    return {s["name"]: s["value"] for s in settings}


def discover(ctx: MigrationContext):
    """Phase 1: Discover existing resources and read configuration."""
    log.info("=" * 60)
    log.info("PHASE 1: Discovery & Validation")
    log.info("=" * 60)

    az(f"account set --subscription {shlex.quote(ctx.control_plane_sub_id)}")

    # Validate Function Apps exist
    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        if not validate_function_app_exists(name, ctx.control_plane_rg, ctx.control_plane_sub_id):
            log.error("Function App '%s' not found. Is this the correct control plane?", name)
            sys.exit(1)
        log.info("Found Function App: %s", name)

    # Discover Container App Environment from the deployer job
    env_name = discover_deployer_environment(ctx.deployer_job_name, ctx.control_plane_rg)
    if not env_name:
        log.error(
            "Could not find deployer job '%s' or its Container App Environment. "
            "Is the deployer deployed in this resource group?",
            ctx.deployer_job_name,
        )
        sys.exit(1)
    ctx.env_name = env_name
    log.info("Discovered Container App Environment from deployer: %s", ctx.env_name)

    # Read env vars from all 3 Function Apps
    log.info("Reading configuration from existing Function Apps...")
    ctx.resources_task_env = get_function_app_env_vars(
        ctx.resources_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )
    ctx.scaling_task_env = get_function_app_env_vars(
        ctx.scaling_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )
    ctx.diagnostic_task_env = get_function_app_env_vars(
        ctx.diagnostic_settings_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )

    # Discover monitored subscriptions
    monitored_subs_str = ctx.resources_task_env.get("MONITORED_SUBSCRIPTIONS", "[]")
    ctx.monitored_subscriptions = json.loads(monitored_subs_str)
    log.info("Discovered %d monitored subscriptions", len(ctx.monitored_subscriptions))

    # Capture old principal IDs for role cleanup during delete phase
    log.info("Capturing existing Function App principal IDs...")
    ctx.old_resources_principal = get_function_app_principal_id(
        ctx.resources_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )
    ctx.old_scaling_principal = get_function_app_principal_id(
        ctx.scaling_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )
    ctx.old_diagnostic_principal = get_function_app_principal_id(
        ctx.diagnostic_settings_task_name, ctx.control_plane_rg, ctx.control_plane_sub_id
    )

    log.info("Discovery complete.")


def pause_deployer(ctx: MigrationContext):
    """Pause the deployer by setting its cron to a never-fires expression."""
    log.info("Pausing deployer job: %s", ctx.deployer_job_name)

    output = az(
        f"containerapp job show"
        f" --name {shlex.quote(ctx.deployer_job_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --query properties.configuration.scheduleTriggerConfig.cronExpression"
        f" --output tsv"
    )
    ctx.deployer_original_cron = output.strip()
    log.info("Saved deployer's original cron expression: %s", ctx.deployer_original_cron)

    az(
        f"containerapp job update"
        f" --name {shlex.quote(ctx.deployer_job_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --cron-expression {shlex.quote(JOB_PAUSED_CRON_EXPRESSION)}"
    )
    ctx.deployer_paused = True
    log.info("Deployer paused.")


def resume_deployer(ctx: MigrationContext):
    """Restore the deployer's original cron expression."""
    cron = ctx.deployer_original_cron or "*/30 * * * *"
    log.info("Resuming deployer with cron expression: %s", cron)
    az(
        f"containerapp job update"
        f" --name {shlex.quote(ctx.deployer_job_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --cron-expression {shlex.quote(cron)}",
        can_fail=True,
    )


# ---------------------------------------------------------------------------
# Phase 2: Create Container App Jobs
# ---------------------------------------------------------------------------


def build_env_vars(env: dict[str, str]) -> list[str]:
    """Convert a Function App env var dict to Container App Job --env-vars format.

    Secrets are referenced via secretref, Function App-only settings are excluded.
    """
    env_var_args = []
    for key, value in env.items():
        if key in FUNCTION_APP_ONLY_SETTINGS:
            continue
        if key in SECRET_SETTINGS:
            env_var_args.append(f"{key}=secretref:{SECRET_SETTINGS[key]}")
        else:
            env_var_args.append(shlex.quote(f"{key}={value}"))
    return env_var_args


def build_secrets(env: dict[str, str]) -> list[str]:
    """Build the --secrets arguments from the Function App env vars."""
    secrets = []
    for setting_name, secret_name in SECRET_SETTINGS.items():
        value = env.get(setting_name, "")
        if value:
            secrets.append(shlex.quote(f"{secret_name}={value}"))
    return secrets


def create_container_app_job(ctx: MigrationContext, job_name: str, image: str, env_vars: list[str], secrets: list[str]):
    """Create a single Container App Job."""
    if container_app_job_exists(job_name, ctx.control_plane_rg):
        log.info("Container App Job '%s' already exists — skipping creation", job_name)
        # Still track it for potential rollback
        ctx.created_jobs.append(job_name)
        return

    log.info("Creating Container App Job: %s", job_name)

    env_vars_str = " ".join(env_vars)
    secrets_str = " ".join(secrets)

    az(
        f"containerapp job create"
        f" --name {shlex.quote(job_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --environment {shlex.quote(ctx.env_name)}"
        f" --trigger-type Schedule"
        f" --cron-expression {shlex.quote(JOB_PAUSED_CRON_EXPRESSION)}"
        f" --image {shlex.quote(image)}"
        f" --cpu {JOB_CPU}"
        f" --memory {JOB_MEMORY}"
        f" --replica-timeout {JOB_REPLICA_TIMEOUT}"
        f" --replica-retry-limit {JOB_REPLICA_RETRY_LIMIT}"
        f" --parallelism 1"
        f" --replica-completion-count 1"
        f" --mi-system-assigned"
        f" --env-vars {env_vars_str}"
        f" --secrets {secrets_str}"
    )
    ctx.created_jobs.append(job_name)
    log.info("Created Container App Job: %s", job_name)


def get_container_app_job_principal_id(job_name: str, rg: str) -> str:
    """Get the system-assigned managed identity principal ID of a Container App Job."""
    output = az(
        f"containerapp job show --name {shlex.quote(job_name)} --resource-group {shlex.quote(rg)} --query identity.principalId --output tsv"
    )
    return output.strip()


def create_jobs(ctx: MigrationContext):
    """Phase 2: Create the 3 Container App Jobs."""
    log.info("=" * 60)
    log.info("PHASE 2: Create Container App Jobs")
    log.info("=" * 60)

    task_configs = [
        (ctx.resources_task_name, f"{IMAGE_REGISTRY_URL}/resources-task:latest", ctx.resources_task_env),
        (ctx.scaling_task_name, f"{IMAGE_REGISTRY_URL}/scaling-task:latest", ctx.scaling_task_env),
        (ctx.diagnostic_settings_task_name, f"{IMAGE_REGISTRY_URL}/diagnostic-settings-task:latest", ctx.diagnostic_task_env),
    ]

    for job_name, image, env in task_configs:
        env_vars = build_env_vars(env)
        secrets = build_secrets(env)
        create_container_app_job(ctx, job_name, image, env_vars, secrets)

    # Retrieve new principal IDs
    log.info("Retrieving new managed identity principal IDs...")
    ctx.new_resources_principal = get_container_app_job_principal_id(ctx.resources_task_name, ctx.control_plane_rg)
    ctx.new_scaling_principal = get_container_app_job_principal_id(ctx.scaling_task_name, ctx.control_plane_rg)
    ctx.new_diagnostic_principal = get_container_app_job_principal_id(
        ctx.diagnostic_settings_task_name, ctx.control_plane_rg
    )
    log.info("New principal IDs retrieved.")


# ---------------------------------------------------------------------------
# Phase 3: Assign Roles
# ---------------------------------------------------------------------------


def role_exists(role_id: str, scope: str, principal_id: str) -> bool:
    """Check if a role assignment already exists."""
    output = az(
        f"role assignment list"
        f" --assignee {shlex.quote(principal_id)}"
        f" --role {shlex.quote(role_id)}"
        f" --scope {shlex.quote(scope)}"
        f' --query "length([])"'
        f" --output tsv",
        can_fail=True,
    )
    try:
        return int(output.strip()) > 0
    except (ValueError, AttributeError):
        return False


def remove_role(scope: str, principal_id: str, role_id: str):
    """Remove a role assignment for a principal at a given scope."""
    output = az(
        f"role assignment list"
        f" --assignee {shlex.quote(principal_id)}"
        f" --role {shlex.quote(role_id)}"
        f" --scope {shlex.quote(scope)}"
        f" --query [].id"
        f" --output tsv",
        can_fail=True,
    )
    for assignment_id in output.strip().splitlines():
        assignment_id = assignment_id.strip()
        if assignment_id:
            log.info("Removing role assignment: %s", assignment_id)
            az(f"role assignment delete --ids {shlex.quote(assignment_id)}", can_fail=True)


def assign_role(ctx: MigrationContext, scope: str, principal_id: str, role_id: str):
    """Assign a role to a principal. Idempotent — skips if already assigned."""
    if role_exists(role_id, scope, principal_id):
        log.debug("Role assignment already exists: role=%s principal=%s scope=%s — skipping", role_id, principal_id, scope)
        return

    log.info("Assigning role %s to principal %s at scope %s", role_id, principal_id, scope)
    az(
        f"role assignment create"
        f" --assignee-object-id {shlex.quote(principal_id)}"
        f" --assignee-principal-type ServicePrincipal"
        f" --role {shlex.quote(role_id)}"
        f" --scope {shlex.quote(scope)}"
        f" --description {shlex.quote(f'ddlfo{ctx.control_plane_id}')}"
    )
    ctx.assigned_roles.append((scope, principal_id, role_id))


def assign_roles(ctx: MigrationContext):
    """Phase 3: Assign roles to the new Container App Job identities.

    Mirrors the role assignments from role_setup.py grant_subscriptions_permissions():
      - resources-task: Monitoring Reader at subscription scope
      - scaling-task: Contributor at resource group scope
      - diagnostic-settings-task: Monitoring Contributor at subscription scope,
                                   Storage Blob Data Reader at resource group scope
    """
    log.info("=" * 60)
    log.info("PHASE 3: Assign Roles to New Identities")
    log.info("=" * 60)

    for sub_id in ctx.all_subscriptions:
        subscription_scope = f"/subscriptions/{sub_id}"
        resource_group_scope = f"{subscription_scope}/resourceGroups/{ctx.control_plane_rg}"

        log.info("Assigning roles in subscription: %s", sub_id)

        # resources-task: Monitoring Reader at subscription scope
        assign_role(ctx, subscription_scope, ctx.new_resources_principal, MONITORING_READER_ID)

        # scaling-task: Contributor at resource group scope
        assign_role(ctx, resource_group_scope, ctx.new_scaling_principal, SCALING_CONTRIBUTOR_ID)

        # diagnostic-settings-task: Monitoring Contributor at subscription scope
        assign_role(ctx, subscription_scope, ctx.new_diagnostic_principal, MONITORING_CONTRIBUTOR_ID)

        # diagnostic-settings-task: Storage Blob Data Reader at resource group scope
        assign_role(ctx, resource_group_scope, ctx.new_diagnostic_principal, STORAGE_READER_AND_DATA_ACCESS_ID)

    log.info("Role assignments complete.")


# ---------------------------------------------------------------------------
# Phase 4: Stop Function Apps
# ---------------------------------------------------------------------------


def stop_function_apps(ctx: MigrationContext):
    """Phase 4: Stop the existing Function Apps so they no longer execute."""
    log.info("=" * 60)
    log.info("PHASE 4: Stop Function Apps")
    log.info("=" * 60)

    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        log.info("Stopping Function App: %s", name)
        az(
            f"functionapp stop"
            f" --name {shlex.quote(name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --subscription {shlex.quote(ctx.control_plane_sub_id)}"
        )

    log.info("All Function Apps stopped.")


def start_function_apps(ctx: MigrationContext):
    """Re-start the Function Apps (used during rollback)."""
    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        log.info("Starting Function App: %s", name)
        az(
            f"functionapp start"
            f" --name {shlex.quote(name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --subscription {shlex.quote(ctx.control_plane_sub_id)}",
            can_fail=True,
        )


# ---------------------------------------------------------------------------
# Phase 5: Trigger & Validate Container App Jobs
# ---------------------------------------------------------------------------

EXECUTION_POLL_INTERVAL = 10  # seconds
EXECUTION_TIMEOUT = 600  # seconds


def trigger_and_wait(job_name: str, rg: str) -> tuple[bool, str]:
    """Trigger a Container App Job execution and wait for it to complete.

    Returns (success, status) where success is True if the execution succeeded.
    """
    log.info("Triggering execution of Container App Job: %s", job_name)
    output = az(
        f"containerapp job start"
        f" --name {shlex.quote(job_name)}"
        f" --resource-group {shlex.quote(rg)}"
        f" --output json"
    )
    result = json.loads(output)
    execution_name = result.get("name", "")
    if not execution_name:
        return False, "Failed to get execution name from job start response"

    log.info("Execution started: %s — polling for completion...", execution_name)

    start_time = time.time()
    while time.time() - start_time < EXECUTION_TIMEOUT:
        exec_output = az_json(
            f"containerapp job execution show"
            f" --name {shlex.quote(job_name)}"
            f" --resource-group {shlex.quote(rg)}"
            f" --job-execution-name {shlex.quote(execution_name)}"
            f" --output json",
            can_fail=True,
        )
        if not exec_output:
            time.sleep(EXECUTION_POLL_INTERVAL)
            continue

        status = exec_output.get("properties", {}).get("status", "Unknown")
        log.debug("Execution %s status: %s", execution_name, status)

        if status == "Succeeded":
            log.info("Execution %s completed successfully", execution_name)
            return True, status
        elif status in ("Failed", "Degraded"):
            log.error("Execution %s failed with status: %s", execution_name, status)
            return False, status

        time.sleep(EXECUTION_POLL_INTERVAL)

    return False, f"Timed out after {EXECUTION_TIMEOUT}s"


def validate_jobs(ctx: MigrationContext) -> list[str]:
    """Phase 5: Trigger each Container App Job and validate successful execution.

    Returns a list of job names that failed (empty if all succeeded).
    """
    log.info("=" * 60)
    log.info("PHASE 5: Trigger & Validate Container App Jobs")
    log.info("=" * 60)

    failures = []
    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        success, status = trigger_and_wait(name, ctx.control_plane_rg)
        if not success:
            failures.append(f"{name}: {status}")

    return failures


# ---------------------------------------------------------------------------
# Phase 6: Activate Container App Jobs
# ---------------------------------------------------------------------------


def activate_jobs(ctx: MigrationContext):
    """Phase 6: Update jobs from the paused cron schedule to the real schedule."""
    log.info("=" * 60)
    log.info("PHASE 6: Activate Container App Jobs")
    log.info("=" * 60)

    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        log.info("Activating Container App Job: %s", name)
        az(
            f"containerapp job update"
            f" --name {shlex.quote(name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --cron-expression {shlex.quote(JOB_CRON_EXPRESSION)}"
        )

    # Update the deployer to the new image and restore its cron schedule
    deployer_cron = ctx.deployer_original_cron or "*/30 * * * *"
    log.info("Updating deployer image to %s and restoring cron to %s", NEW_DEPLOYER_IMAGE, deployer_cron)
    az(
        f"containerapp job update"
        f" --name {shlex.quote(ctx.deployer_job_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --image {shlex.quote(NEW_DEPLOYER_IMAGE)}"
        f" --cron-expression {shlex.quote(deployer_cron)}"
    )
    ctx.deployer_paused = False

    log.info("All jobs activated.")


# ---------------------------------------------------------------------------
# Phase 7: Delete Old Resources
# ---------------------------------------------------------------------------


def delete_old_resources(ctx: MigrationContext):
    """Phase 7: Delete old Function Apps, their role assignments, ASP, and file shares."""
    log.info("=" * 60)
    log.info("PHASE 7: Delete Old Resources")
    log.info("=" * 60)

    # Remove old Function App role assignments
    log.info("Removing old Function App role assignments...")
    for sub_id in ctx.all_subscriptions:
        subscription_scope = f"/subscriptions/{sub_id}"
        resource_group_scope = f"{subscription_scope}/resourceGroups/{ctx.control_plane_rg}"

        remove_role(subscription_scope, ctx.old_resources_principal, MONITORING_READER_ID)
        remove_role(resource_group_scope, ctx.old_scaling_principal, SCALING_CONTRIBUTOR_ID)
        remove_role(subscription_scope, ctx.old_diagnostic_principal, MONITORING_CONTRIBUTOR_ID)
        remove_role(resource_group_scope, ctx.old_diagnostic_principal, STORAGE_READER_AND_DATA_ACCESS_ID)

    # Delete Function Apps
    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        log.info("Deleting Function App: %s", name)
        az(
            f"functionapp delete"
            f" --name {shlex.quote(name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --subscription {shlex.quote(ctx.control_plane_sub_id)}",
            can_fail=True,
        )

    # Delete App Service Plan
    log.info("Deleting App Service Plan: %s", ctx.asp_name)
    az(
        f"appservice plan delete"
        f" --name {shlex.quote(ctx.asp_name)}"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --subscription {shlex.quote(ctx.control_plane_sub_id)}"
        f" --yes",
        can_fail=True,
    )

    # Delete file share (no longer needed; blob container is kept)
    log.info("Deleting file share: control-plane-cache")
    az(
        f"storage share-rm delete"
        f" --storage-account {shlex.quote(ctx.storage_account_name)}"
        f" --name control-plane-cache"
        f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
        f" --yes",
        can_fail=True,
    )

    # Remove deployer's Website Contributor role assignment — it was only needed
    # to manage the Function Apps which no longer exist. The deployer's managed
    # identity persists, so this won't be auto-cleaned.
    log.info("Removing deployer's Website Contributor role assignment...")
    deployer_principal = get_container_app_job_principal_id(ctx.deployer_job_name, ctx.control_plane_rg)
    if deployer_principal:
        az(
            f"role assignment delete"
            f" --assignee {shlex.quote(deployer_principal)}"
            f" --role {shlex.quote(WEBSITE_CONTRIBUTOR_ID)}"
            f" --scope {shlex.quote(ctx.control_plane_rg_scope)}",
            can_fail=True,
        )

    log.info("Old resources deleted.")


# ---------------------------------------------------------------------------
# Phase 8: Verification
# ---------------------------------------------------------------------------


def verify(ctx: MigrationContext):
    """Phase 8: Verify the new Container App Jobs are provisioned and active."""
    log.info("=" * 60)
    log.info("PHASE 8: Verification")
    log.info("=" * 60)

    for name in [ctx.resources_task_name, ctx.scaling_task_name, ctx.diagnostic_settings_task_name]:
        output = az_json(
            f"containerapp job show"
            f" --name {shlex.quote(name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --query '{{name:name, status:properties.provisioningState, trigger:properties.configuration.triggerType}}'"
            f" --output json"
        )
        if output:
            log.info("Container App Job %s: status=%s, trigger=%s", output.get("name"), output.get("status"), output.get("trigger"))
        else:
            log.warning("Could not verify Container App Job: %s", name)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback(ctx: MigrationContext):
    """Undo any changes made during the migration and re-enable Function Apps."""
    log.warning("Rolling back migration changes...")

    # Re-start Function Apps if they were stopped
    if ctx.function_apps_stopped:
        log.info("Re-starting Function Apps...")
        start_function_apps(ctx)

    # Remove any role assignments we created for the new jobs
    for scope, principal_id, role_id in reversed(ctx.assigned_roles):
        log.info("Rolling back role assignment: role=%s principal=%s scope=%s", role_id, principal_id, scope)
        remove_role(scope, principal_id, role_id)

    # Delete any Container App Jobs we created
    for job_name in reversed(ctx.created_jobs):
        log.info("Rolling back Container App Job: %s", job_name)
        az(
            f"containerapp job delete"
            f" --name {shlex.quote(job_name)}"
            f" --resource-group {shlex.quote(ctx.control_plane_rg)}"
            f" --yes",
            can_fail=True,
        )

    # Resume the deployer with its original cron (image unchanged on rollback)
    if ctx.deployer_paused:
        log.info("Resuming deployer...")
        resume_deployer(ctx)

    log.warning("Rollback complete. Original Function Apps and deployer are unchanged.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate LFO control plane tasks from Function Apps to Container App Jobs."
    )
    parser.add_argument(
        "--control-plane-subscription-id",
        required=True,
        help="Azure subscription ID hosting the control plane.",
    )
    parser.add_argument(
        "--control-plane-resource-group",
        required=True,
        help="Resource group containing the control plane resources.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    validate_azure_cli()

    sub_id = args.control_plane_subscription_id
    rg = args.control_plane_resource_group

    log.info("Discovering control plane ID and region...")
    control_plane_id = discover_control_plane_id(sub_id, rg)
    control_plane_region = discover_resource_group_region(sub_id, rg)
    log.info("Discovered control plane ID: %s", control_plane_id)
    log.info("Discovered control plane region: %s", control_plane_region)

    ctx = MigrationContext(
        control_plane_sub_id=sub_id,
        control_plane_rg=rg,
        control_plane_region=control_plane_region,
        control_plane_id=control_plane_id,
    )

    try:
        discover(ctx)
        pause_deployer(ctx)
        create_jobs(ctx)
        assign_roles(ctx)
        stop_function_apps(ctx)
        ctx.function_apps_stopped = True

        failures = validate_jobs(ctx)
        if failures:
            log.error("Container App Job validation failed:")
            for failure in failures:
                log.error("  - %s", failure)
            raise RuntimeError("One or more Container App Jobs failed validation")

        activate_jobs(ctx)
        delete_old_resources(ctx)
        verify(ctx)
    except Exception:
        log.exception("Migration failed!")
        rollback(ctx)
        sys.exit(1)

    log.info("=" * 60)
    log.info("Migration complete!")
    log.info("3 control plane tasks are now running as Container App Jobs")
    log.info("in environment: %s", ctx.env_name)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
