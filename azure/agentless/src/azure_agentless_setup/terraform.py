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
import tempfile
from pathlib import Path
from typing import Optional

from .config import Config, get_config_dir
from .errors import TerraformError
from .reporter import Reporter, AgentlessStep


TERRAFORM_PARALLELISM = 10

MODULE_VERSION = "0.12.1"
MODULE_BASE = f"git::https://github.com/DataDog/terraform-module-datadog-agentless-scanner//azure/modules"


def _module_source(module_name: str) -> str:
    return f"{MODULE_BASE}/{module_name}?ref={MODULE_VERSION}"


def _sanitize_name(name: str) -> str:
    """Convert a name to a valid Terraform identifier (replace hyphens with underscores)."""
    return name.replace("-", "_")


def generate_ssh_key() -> tuple[str, Path]:
    """Generate a temporary SSH key pair for the scanner VMSS.

    Azure requires an SSH public key for VMSS instances. The key is only
    used during provisioning — scanner VMs are not accessed via SSH.

    Returns:
        Tuple of (public_key_content, temp_dir_path). The caller should
        clean up temp_dir after Terraform apply completes.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="dd-agentless-ssh-"))
    key_path = tmp_dir / "id_rsa"

    subprocess.run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(key_path), "-N", "", "-q"],
        check=True,
    )

    public_key = (key_path.with_suffix(".pub")).read_text().strip()
    return public_key, tmp_dir


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

    # Per-location resources: VNet (inlined because the upstream module
    # hardcodes resource names which collide in multi-location deployments)
    # and VM (module supports a name variable).
    location_modules_tf = ""
    for location in config.locations:
        loc_id = _sanitize_name(location)
        location_modules_tf += f'''
# --- {location} ---

resource "azurerm_virtual_network" "vnet_{loc_id}" {{
  name                = "vnet-{location}"
  location            = "{location}"
  resource_group_name = data.azurerm_resource_group.scanner.name
  address_space       = ["10.0.0.0/16"]
  tags                = {{ Datadog = "true", DatadogAgentlessScanner = "true" }}
}}

resource "azurerm_subnet" "subnet_{loc_id}" {{
  name                 = "default"
  resource_group_name  = data.azurerm_resource_group.scanner.name
  virtual_network_name = azurerm_virtual_network.vnet_{loc_id}.name
  address_prefixes     = ["10.0.0.0/18"]
}}

resource "azurerm_nat_gateway" "natgw_{loc_id}" {{
  name                = "natgw-{location}"
  location            = "{location}"
  resource_group_name = data.azurerm_resource_group.scanner.name
  sku_name            = "Standard"
  tags                = {{ Datadog = "true", DatadogAgentlessScanner = "true" }}
}}

resource "azurerm_public_ip" "natgw_ip_{loc_id}" {{
  name                = "natgw-ip-{location}"
  location            = "{location}"
  resource_group_name = data.azurerm_resource_group.scanner.name
  sku                 = "Standard"
  sku_tier            = "Regional"
  ip_version          = "IPv4"
  allocation_method   = "Static"
  tags                = {{ Datadog = "true", DatadogAgentlessScanner = "true" }}
}}

resource "azurerm_nat_gateway_public_ip_association" "natgw_ip_assoc_{loc_id}" {{
  nat_gateway_id       = azurerm_nat_gateway.natgw_{loc_id}.id
  public_ip_address_id = azurerm_public_ip.natgw_ip_{loc_id}.id
}}

resource "azurerm_subnet_nat_gateway_association" "subnet_natgw_assoc_{loc_id}" {{
  subnet_id      = azurerm_subnet.subnet_{loc_id}.id
  nat_gateway_id = azurerm_nat_gateway.natgw_{loc_id}.id
}}

module "virtual_machine_{loc_id}" {{
  source                 = "{_module_source("virtual-machine")}"
  depends_on             = [azurerm_subnet_nat_gateway_association.subnet_natgw_assoc_{loc_id}]
  name                   = "DatadogAgentlessScanner-{location}"
  location               = "{location}"
  resource_group_name    = data.azurerm_resource_group.scanner.name
  admin_ssh_key          = var.admin_ssh_key
  custom_data            = module.custom_data.install_sh
  subnet_id              = azurerm_subnet.subnet_{loc_id}.id
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
        self._ssh_tmp_dir: Optional[Path] = None

    def setup_working_directory(self) -> Path:
        """Create and populate the Terraform working directory."""
        ssh_public_key, self._ssh_tmp_dir = generate_ssh_key()

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

    def cleanup_ssh_key(self) -> None:
        """Remove the temporary SSH key pair."""
        if self._ssh_tmp_dir and self._ssh_tmp_dir.exists():
            import shutil
            shutil.rmtree(self._ssh_tmp_dir, ignore_errors=True)
            self._ssh_tmp_dir = None

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
            self.cleanup_ssh_key()
