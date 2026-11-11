# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.logs import log, log_header
from azure_logging_install.configuration import ControlPlane, ControlPlaneType, Configuration
from azure_logging_install.existing_lfo import find_existing_lfo_control_planes, get_current_config_for_control_plane
from azure_logging_install.resource_setup import verify_container_app_env_exists, verify_container_app_job_exists, verify_function_app_exists

from .cleanup import (
    DeleteControlPlaneCacheFileShare,
    DeleteOldFunctionApps,
    RevokeDeployerWebsiteContributorRole,
)
from .create_container_app_job import (
    CreateDiagnosticSettingsTaskContainerAppJob,
    CreateResourcesTaskContainerAppJob,
    CreateScalingTaskContainerAppJob,
)
from .enablement import (
    PauseDeployer,
    PauseOldFunctionApps,
    UnpauseDeployer,
    UnpauseNewContainerAppJobs,
    UpdateDeployerImage,
)
from .grant_permissions import GrantContainerAppJobPermissionsStep
from .prompts import confirm_yes
from .steps import run_cleanup_steps, run_steps, CleanupStep, Step


def run_migration(optional_control_plane_ids: set[str], skip_confirmation: bool, dry_run: bool = False) -> None:
    control_planes: list[ControlPlane] = find_existing_lfo_control_planes(subscriptions=None, control_plane_type=ControlPlaneType.FunctionApps)
    if len(optional_control_plane_ids) > 0:
        control_planes = [c for c in control_planes if c.id in optional_control_plane_ids]

    if len(control_planes) == 0:
        log.info("No eligible Function App LFO installations found to migrate")
        return

    for control_plane in control_planes:
        # A dry run changes nothing, so there's nothing to confirm
        if not (dry_run or skip_confirmation or confirm_yes(
            f"Migrate control plane '{control_plane.id}' in subscription "
            f"'{control_plane.sub_id}', resource group "
            f"'{control_plane.resource_group}' to Container App Jobs?"
        )):
            log.info(f"Skipping migration for control plane {control_plane.id}")
            continue

        try:
            migrate_control_plane(control_plane, dry_run)
        except Exception as e:
            if dry_run:
                log.error(f"Dry run failed for control plane {control_plane.id}: {e}")
                log.error("No changes were made.")
            else:
                log.error(f"Migration failed for control plane {control_plane.id}: {e}")
                log.error("Changes for this installation were rolled back.")
            raise
        else:
            if dry_run:
                log_header(f"Dry run complete for control plane {control_plane.id}. No changes were made.")
            else:
                log_header(f"Success! Control plane {control_plane.id} migrated.")


def migrate_control_plane(control_plane: ControlPlane, dry_run: bool = False) -> None:
    log_header(
        f"{'[DRY RUN] ' if dry_run else ''}Migrating control plane {control_plane.id} in resource group {control_plane.resource_group}, subscription {control_plane.sub_id}"
    )

    function_app_config = get_current_config_for_control_plane(control_plane)
    _verify_function_app_installation(function_app_config)
    caj_config = _build_caj_config(function_app_config)

    migration_steps = _build_migration_steps(caj_config, function_app_config)
    cleanup_steps = _build_cleanup_steps(caj_config, function_app_config)

    if dry_run:
        _log_migration_plan(caj_config, migration_steps, cleanup_steps)
        return

    run_steps(migration_steps)
    run_cleanup_steps(cleanup_steps)


def _log_migration_plan(caj_config: Configuration, migration_steps: list[Step], cleanup_steps: list[CleanupStep]) -> None:
    """Logs the settings the new Container App Jobs would get and every step that would run, without changing anything."""
    log_header("DRY RUN: settings that would be copied from the Function Apps")
    api_key = caj_config.datadog_api_key
    monitored_subs = caj_config.monitored_subscriptions
    log.info(f"Monitored subscriptions ({len(monitored_subs)}): {', '.join(monitored_subs) or 'NONE'}")
    log.info(f"Datadog site: {caj_config.datadog_site}")
    log.info(f"Datadog API key: {f'set (ending in {api_key[-4:]})' if api_key else 'NOT SET'}")
    log.info(f"Resource tag filters: {caj_config.resource_tag_filters or '(none)'}")
    log.info(f"PII scrubber rules: {'set' if caj_config.pii_scrubber_rules else '(none)'}")
    log.info(f"Datadog telemetry: {caj_config.datadog_telemetry}")
    log.info(f"Log level: {caj_config.log_level}")
    if not api_key:
        log.warning("No Datadog API key was found on the Function Apps. The new tasks would not be able to send data to Datadog.")
    if not monitored_subs:
        log.warning("No monitored subscriptions were found on the Function Apps. The new tasks would not forward logs from any subscription.")

    log_header(
        "DRY RUN: migration steps (if a step fails, completed steps are rolled back; "
        "resource groups created in monitored subscriptions are kept)"
    )
    for i, step in enumerate(migration_steps, start=1):
        log.info(f"{i}. {step.describe()}")

    log_header("DRY RUN: cleanup steps (run after a successful migration; cannot be undone)")
    for i, step in enumerate(cleanup_steps, start=1):
        log.info(f"{i}. {step.describe()}")

    warnings = [warning for step in migration_steps for warning in step.dry_run_warnings]
    for warning in warnings:
        log.warning(warning)
    if warnings:
        log.warning(f"{len(warnings)} problem(s) found above. The migration would likely fail and roll back.")
    log.info(
        "Note: the dry run doesn't check whether you have permission to create the Container App Jobs, "
        "resource groups and role assignments listed above."
    )


def _build_migration_steps(caj_config: Configuration, function_app_config: Configuration) -> list[Step]:
    return [
        CreateResourcesTaskContainerAppJob(caj_config),
        CreateDiagnosticSettingsTaskContainerAppJob(caj_config),
        CreateScalingTaskContainerAppJob(caj_config),
        GrantContainerAppJobPermissionsStep(caj_config),
        PauseDeployer(caj_config),
        PauseOldFunctionApps(function_app_config),
        UnpauseNewContainerAppJobs(caj_config),
        UpdateDeployerImage(caj_config, function_app_config),
        UnpauseDeployer(caj_config),
    ]


def _build_cleanup_steps(caj_config: Configuration, function_app_config: Configuration) -> list[CleanupStep]:
    return [
        DeleteOldFunctionApps(function_app_config),
        DeleteControlPlaneCacheFileShare(caj_config),
        RevokeDeployerWebsiteContributorRole(caj_config),
    ]


def _verify_function_app_installation(config: Configuration) -> None:
    # validate deployer exists
    verify_container_app_env_exists(config.control_plane_env_name, config.control_plane.resource_group, config.control_plane.sub_id)
    verify_container_app_job_exists(config.deployer_job_name, config.control_plane.resource_group, config.control_plane.sub_id)

    # validate the 3 function app tasks exists
    verify_function_app_exists(config.control_plane.resources_task_name, config.control_plane.resource_group, config.control_plane.sub_id)
    verify_function_app_exists(config.control_plane.diagnostic_settings_task_name, config.control_plane.resource_group, config.control_plane.sub_id)
    verify_function_app_exists(config.control_plane.scaling_task_name, config.control_plane.resource_group, config.control_plane.sub_id)


def _build_caj_config(function_app_config: Configuration) -> Configuration:
    """Build a Container App Job configuration with the same options as the Function App Configuration"""
    function_app_control_plane = function_app_config.control_plane
    caj_control_plane = ControlPlane(
        id=function_app_control_plane.id,
        sub_id=function_app_control_plane.sub_id,
        resource_group=function_app_control_plane.resource_group,
        region=function_app_control_plane.region,
        type=ControlPlaneType.ContainerAppJobs,
    )

    return Configuration(
        control_plane=caj_control_plane,
        monitored_subs=function_app_config.monitored_subs,
        datadog_api_key=function_app_config.datadog_api_key,
        datadog_site=function_app_config.datadog_site,
        resource_tag_filters=function_app_config.resource_tag_filters,
        pii_scrubber_rules=function_app_config.pii_scrubber_rules,
        datadog_telemetry=function_app_config.datadog_telemetry,
        log_level=function_app_config.log_level,
    )
