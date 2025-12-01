from os import environ

from az_shared.az_cmd import execute, execute_json
from common.shell import Cmd


def list_extension_versions(subscription: str, resource_group: str, cluster_name: str) -> list:
    return execute_json(
        Cmd(["az", "k8s-extension", "extension-types", "list-by-cluster"])
        .param("--subscription", subscription)
        .param("-g", resource_group)
        .param("-c", cluster_name)
        .param("-t", "managedClusters")
        # TODO: Determine exact output format and add --query param.
    )


def create_extension(subscription: str, resource_group: str, cluster_name: str, name: str, version: str) -> None:
    execute(
        Cmd(["az", "k8s-extension", "create"])
        .param("--subscription", subscription)
        .param("-g", resource_group)
        .param("-c", cluster_name)
        .param("-n", name)
        .param("--version", version)
        .param("--config", f"site={environ['DD_SITE']}")
        .param("--config-protected", f"dd.apikey={environ['DD_API_KEY']}")
        .param("--plan-publisher", "datadog1591740804488")
        .param("--plan-product", "dd_aks_extension")
        .param("--plan-name", "datadog_aks_cluster_extension")
        .param("--extension-type", "Microsoft.AzureMonitor.Containers")
        .param("-t", "managedClusters")
        .param("--auto-upgrade-minor-version", "false")
    )
