# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
from unittest.mock import MagicMock, patch

import pytest

from azure_agentless_setup.config import Config
from azure_agentless_setup.terraform import (
    MODULE_VERSION,
    _sanitize_name,
    generate_terraform_config,
    generate_tfvars,
)


def _make_config(**overrides) -> Config:
    defaults = dict(
        api_key="test-api-key",
        app_key="test-app-key",
        site="datadoghq.com",
        workflow_id="wf-123",
        scanner_subscription="sub-scanner",
        locations=["eastus"],
        subscriptions_to_scan=["sub-scanner", "sub-other"],
        resource_group="datadog-agentless-scanner",
    )
    defaults.update(overrides)
    return Config(**defaults)


API_KEY_SECRET_ID = "/subscriptions/sub-scanner/resourceGroups/datadog-agentless-scanner/providers/Microsoft.KeyVault/vaults/datadog-abc123/secrets/datadog-api-key"


class TestSanitizeName:
    def test_replaces_hyphens(self):
        assert _sanitize_name("east-us") == "east_us"

    def test_no_hyphens(self):
        assert _sanitize_name("eastus") == "eastus"


class TestGenerateTerraformConfig:
    def test_single_location(self):
        config = _make_config(locations=["eastus"])
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert 'subscription_id = "sub-scanner"' in tf
        assert 'storage_account_name = "storageacct"' in tf
        assert 'container_name       = "tfstate"' in tf
        assert f'key                  = "datadog-agentless.tfstate"' in tf
        assert 'data "azurerm_resource_group" "scanner"' in tf
        assert 'module "managed_identity"' in tf
        assert 'module "roles"' in tf
        assert 'module "custom_data"' in tf
        # VNet is inlined (not a module) with location-prefixed names
        assert 'resource "azurerm_virtual_network" "vnet_eastus"' in tf
        assert '"vnet-eastus"' in tf
        assert 'resource "azurerm_subnet" "subnet_eastus"' in tf
        assert 'resource "azurerm_nat_gateway" "natgw_eastus"' in tf
        assert 'module "virtual_machine_eastus"' in tf
        assert '"DatadogAgentlessScanner-eastus"' in tf

    def test_multi_location(self):
        config = _make_config(locations=["eastus", "westeurope"])
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        for loc in ["eastus", "westeurope"]:
            loc_id = loc.replace("-", "_")
            assert f'resource "azurerm_virtual_network" "vnet_{loc_id}"' in tf
            assert f'"vnet-{loc}"' in tf
            assert f'resource "azurerm_nat_gateway" "natgw_{loc_id}"' in tf
            assert f'"natgw-{loc}"' in tf
            assert f'module "virtual_machine_{loc_id}"' in tf
            assert f'"DatadogAgentlessScanner-{loc}"' in tf
        # Shared modules should appear only once
        assert tf.count('module "managed_identity"') == 1
        assert tf.count('module "roles"') == 1
        assert tf.count('module "custom_data"') == 1

    def test_scan_scopes_include_all_subscriptions(self):
        config = _make_config(subscriptions_to_scan=["sub-scanner", "sub-a", "sub-b"])
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert '"/subscriptions/sub-a"' in tf
        assert '"/subscriptions/sub-b"' in tf
        assert '"/subscriptions/sub-scanner"' in tf

    def test_module_version_pinned(self):
        config = _make_config()
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert f"ref={MODULE_VERSION}" in tf

    def test_key_vault_secret_uri(self):
        config = _make_config()
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert "https://datadog-abc123.vault.azure.net/secrets/datadog-api-key" in tf

    def test_no_resource_group_module(self):
        config = _make_config()
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert 'module "resource_group"' not in tf
        assert 'data "azurerm_resource_group"' in tf

    def test_role_name_suffix_includes_subscription_prefix(self):
        config = _make_config(resource_group="my-custom-rg", scanner_subscription="46aba334-2540-4cfe-b36e-54266afb2bf6")
        tf = generate_terraform_config(config, "storageacct", API_KEY_SECRET_ID, "ssh-rsa AAAA")

        assert 'role_name_suffix  = "my-custom-rg-46aba334"' in tf


class TestGenerateTfvars:
    def test_contains_ssh_key(self):
        tfvars = generate_tfvars("ssh-rsa AAAA test@host")
        assert 'admin_ssh_key = "ssh-rsa AAAA test@host"' in tfvars
