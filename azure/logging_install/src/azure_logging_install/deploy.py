from logging import getLogger

from .az_cmd import AzCmd, execute, set_subscription
from .configuration import Configuration
from .resource_setup import (
    create_blob_container,
    create_container_app_environment,
    create_container_app_job,
    create_file_share,
    create_function_apps,
    create_storage_account,
    wait_for_storage_account_ready,
)
from .role_setup import (
    create_initial_deploy_role,
)

log = getLogger("installer")


def deploy_lfo_deployer(config: Configuration):
    """Deploy all container job infrastructure."""
    create_initial_deploy_role(config)

    log.info("Creating container app environment...")
    create_container_app_environment(
        config.control_plane_env_name,
        config.control_plane_rg,
        config.control_plane_region,
    )

    log.info("Creating container app job...")
    create_container_app_job(config)

    log.info("Container App job + identity setup complete")


def deploy_control_plane(config: Configuration):
    """Deploy all control plane infrastructure: storage, functions, and containers."""
    log.info("Deploying storage account...")
    set_subscription(config.control_plane_sub_id)
    create_storage_account(
        config.control_plane_cache_storage_name,
        config.control_plane_rg,
        config.control_plane_region,
    )
    wait_for_storage_account_ready(
        config.control_plane_cache_storage_name, config.control_plane_rg
    )
    create_blob_container(
        config.control_plane_cache_storage_name,
        config.get_control_plane_cache_key(),
    )
    create_file_share(
        config.control_plane_cache_storage_name,
        config.control_plane_rg,
    )
    log.info("Storage account setup completed")

    log.info("Creating Function Apps...")
    create_function_apps(config)

    log.info("Deploying Container App infrastructure for deployer job...")
    deploy_lfo_deployer(config)

    log.info("Control plane infrastructure deployment completed")


def run_initial_deploy(
    deployer_job_name: str, control_plane_rg: str, control_plane_sub_id: str
):
    """Trigger the initial deployment by starting the deployer container app job."""
    log.info("Triggering initial deployment by starting deployer container app job...")

    try:
        execute(
            AzCmd("containerapp", "job start")
            .param("--name", deployer_job_name)
            .param("--resource-group", control_plane_rg)
            .param("--subscription", control_plane_sub_id)
            .flag("--no-wait")
        )
        log.info(f"Successfully started deployer job: {deployer_job_name}")
    except Exception as e:
        log.error(f"Failed to start deployer container app job: {e}")
        raise RuntimeError(f"Could not trigger initial deployment: {e}") from e
