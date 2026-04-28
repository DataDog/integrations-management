# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Terraform wrapper for generating config, init, and apply.

Generates a Terraform configuration that uses the individual sub-modules
from terraform-module-datadog-agentless-scanner/azure/modules/ rather
than the monolithic root module. This allows deploying scanner
infrastructure across multiple Azure locations within a single
resource group.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from .config import Config, get_config_dir
from .errors import TerraformError
from .reporter import Reporter, AgentlessStep


TERRAFORM_PARALLELISM = 10

# TODO: replace with a release tag once terraform-module-datadog-agentless-scanner cuts one
MODULE_VERSION = "fbc0d0bb425ae4084433834e68d3b23e566fba0d"
MODULE_BASE = f"git::https://github.com/DataDog/terraform-module-datadog-agentless-scanner//azure/modules"


def _module_source(module_name: str) -> str:
    return f"{MODULE_BASE}/{module_name}?ref={MODULE_VERSION}"


def _sanitize_name(name: str) -> str:
    """Convert a name to a valid Terraform identifier (replace hyphens with underscores)."""
    return name.replace("-", "_")


def generate_ssh_key() -> str:
    """Generate an SSH public key for the scanner VMSS.

    Azure requires an SSH public key for VMSS instances. The key is only
    used during provisioning — scanner VMs are not accessed via SSH.
    The private key is discarded and never written to disk.
    """
    pubpem = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA",
         "-out", "/dev/null", "-outpubkey", "-"],
        capture_output=True,
        check=True,
    )

    pubkey = subprocess.run(
        ["ssh-keygen", "-i", "-m", "PKCS8", "-f", "/dev/stdin"],
        input=pubpem.stdout,
        capture_output=True,
        check=True,
    )

    return pubkey.stdout.decode("ascii").strip()


def generate_terraform_config(
    config: Config,
    storage_account: str,
    api_key_secret_id: str,
    ssh_public_key: str,
) -> str:
    """Generate the Terraform configuration using individual sub-modules.

    Architecture:
      - Resource group: referenced as data source (already created by state_storage.py)
      - Managed identity: one shared across all locations
      - Roles: one set of role definitions/assignments
      - Custom data: one install script (same identity for all VMs)
      - Virtual network: one per location (VNet + NAT gateway)
      - Virtual machine: one VMSS per location
    """
    # Provider block
    provider_tf = f'''provider "azurerm" {{
  features {{}}
  subscription_id = "{config.scanner_subscription}"
}}
'''

    # Backend
    backend_tf = f'''terraform {{
  required_version = ">= 1.0"

  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = ">= 3.101.0"
    }}
  }}

  backend "azurerm" {{
    storage_account_name = "{storage_account}"
    container_name       = "tfstate"
    key                  = "datadog-agentless.tfstate"
    subscription_id      = "{config.scanner_subscription}"
    use_azuread_auth     = true
  }}
}}
'''

    # Resource group: data source (already created by state_storage.py)
    rg_tf = f'''data "azurerm_resource_group" "scanner" {{
  name = "{config.resource_group}"
}}
'''

    # Managed identity (one, shared across locations)
    identity_tf = f'''module "managed_identity" {{
  source              = "{_module_source("managed-identity")}"
  resource_group_name = data.azurerm_resource_group.scanner.name
  location            = data.azurerm_resource_group.scanner.location
}}
'''

    # Roles (one set, with suffix to avoid tenant-scoped name collisions).
    # Include subscription prefix so two subscriptions in the same tenant
    # don't produce identical role display names.
    role_suffix = f"{config.resource_group}-{config.scanner_subscription[:8]}"
    scan_scopes_tf = "[" + ", ".join(f'"/subscriptions/{s}"' for s in config.all_subscriptions) + "]"
    roles_tf = f'''module "roles" {{
  source            = "{_module_source("roles")}"
  role_name_suffix  = "{role_suffix}"
  resource_group_id = data.azurerm_resource_group.scanner.id
  principal_id      = module.managed_identity.identity.principal_id
  api_key_secret_id = "{api_key_secret_id}"
  scan_scopes       = {scan_scopes_tf}
}}
'''

    # Extract vault name from the ARM resource ID to build the data-plane URI.
    # api_key_secret_id format: /subscriptions/.../Microsoft.KeyVault/vaults/<name>/secrets/<secret>
    vault_name = api_key_secret_id.split("/providers/Microsoft.KeyVault/vaults/")[1].split("/")[0]
    secret_uri = f"https://{vault_name}.vault.azure.net/secrets/datadog-api-key"

    custom_data_tf = f'''module "custom_data" {{
  source    = "{_module_source("custom-data")}"
  api_key   = "@Microsoft.KeyVault(SecretUri={secret_uri})"
  site      = "{config.site}"
  client_id = module.managed_identity.identity.client_id
}}
'''

    # Per-location resources: VNet + VM
    location_modules_tf = ""
    for location in config.locations:
        loc_id = _sanitize_name(location)
        location_modules_tf += f'''
# --- {location} ---

module "virtual_network_{loc_id}" {{
  source              = "{_module_source("virtual-network")}"
  location            = "{location}"
  resource_group_name = data.azurerm_resource_group.scanner.name
  unique_suffix       = "{location}"
}}

module "virtual_machine_{loc_id}" {{
  source                 = "{_module_source("virtual-machine")}"
  depends_on             = [module.virtual_network_{loc_id}]
  name                   = "DatadogAgentlessScanner-{location}"
  location               = "{location}"
  resource_group_name    = data.azurerm_resource_group.scanner.name
  admin_ssh_key          = var.admin_ssh_key
  custom_data            = module.custom_data.install_sh
  subnet_id              = module.virtual_network_{loc_id}.subnet.id
  user_assigned_identity = module.managed_identity.identity.id
}}
'''

    # Variables
    variables_tf = '''
variable "admin_ssh_key" {
  description = "SSH public key for scanner VMSS instances"
  type        = string
  sensitive   = true
}
'''

    tf_config = f'''# Generated by Datadog Agentless Scanner Cloud Shell Setup
# Do not edit manually — rerun the setup script to update

{backend_tf}
{provider_tf}
{rg_tf}
{variables_tf}
{identity_tf}
{roles_tf}
{custom_data_tf}
{location_modules_tf}
'''

    return tf_config


def generate_tfvars(ssh_public_key: str) -> str:
    """Generate the terraform.tfvars content."""
    return f'admin_ssh_key = "{ssh_public_key}"\n'


class TerraformRunner:
    """Runs Terraform commands in a working directory."""

    def __init__(
        self,
        config: Config,
        storage_account: str,
        api_key_secret_id: str,
        reporter: Reporter,
    ):
        self.config = config
        self.storage_account = storage_account
        self.api_key_secret_id = api_key_secret_id
        self.reporter = reporter
        self.work_dir: Optional[Path] = None

    def setup_working_directory(self) -> Path:
        """Create and populate the Terraform working directory."""
        ssh_public_key = generate_ssh_key()

        work_dir = get_config_dir(self.config.scanner_subscription)
        work_dir.mkdir(parents=True, exist_ok=True)

        main_tf = work_dir / "main.tf"
        main_tf.write_text(
            generate_terraform_config(
                self.config,
                self.storage_account,
                self.api_key_secret_id,
                ssh_public_key,
            )
        )

        tfvars = work_dir / "terraform.tfvars"
        tfvars.write_text(generate_tfvars(ssh_public_key))

        self.work_dir = work_dir
        return work_dir

    def init(self) -> None:
        """Run terraform init.

        Raises:
            TerraformError: If init fails.
        """
        if not self.work_dir:
            raise TerraformError("Working directory not set up")

        result = subprocess.run(
            ["terraform", "init", "-input=false", "-reconfigure"],
            capture_output=False,
        )

        if result.returncode != 0:
            raise TerraformError("Terraform init failed")

    def apply(self) -> None:
        """Run terraform apply.

        Raises:
            TerraformError: If apply fails.
        """
        if not self.work_dir:
            raise TerraformError("Working directory not set up")

        result = subprocess.run(
            [
                "terraform", "apply",
                "-auto-approve",
                f"-parallelism={TERRAFORM_PARALLELISM}",
                "-input=false",
            ],
            capture_output=False,
        )

        if result.returncode != 0:
            raise TerraformError("Terraform apply failed")

    def run(self) -> None:
        """Run the full Terraform workflow (generate → init → apply).

        Raises:
            TerraformError: If any Terraform operation fails.
        """
        self.reporter.start_step("Generating Terraform configuration", AgentlessStep.GENERATE_TERRAFORM_CONFIG)
        work_dir = self.setup_working_directory()
        self.reporter.success(f"Configuration written to {work_dir}")
        self.reporter.finish_step()

        original_dir = os.getcwd()
        os.chdir(work_dir)

        try:
            self.reporter.start_step("Initializing Terraform", AgentlessStep.TERRAFORM_INIT)
            self.reporter.info("Downloading providers (this may take a minute)...")
            self.init()
            self.reporter.success("Terraform initialized")
            self.reporter.finish_step()

            self.reporter.start_step("Deploying Agentless Scanner", AgentlessStep.DEPLOY_INFRASTRUCTURE)
            self.reporter.info("Creating resources (this may take several minutes)...")
            self.apply()
            self.reporter.success("Resources created successfully")
            self.reporter.finish_step(metadata={
                "scanner_subscription": self.config.scanner_subscription,
                "scanner_locations": self.config.locations,
                "subscriptions_to_scan": self.config.all_subscriptions,
            })

        finally:
            os.chdir(original_dir)
