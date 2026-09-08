#!/bin/bash
# Test script: deploy the forwarder with VNet + private storage.
#
# Prerequisites:
#   - az CLI logged in (`az login`)
#   - Subscription and resource group already exist
#   - Set the variables in the CONFIG section below

set -euo pipefail

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="dd-forwarder-vnet-test"
LOCATION="eastus"
DD_API_KEY="<your-32-char-datadog-api-key>"
DD_SITE="datadoghq.com"

# Names (adjust if needed)
VNET_NAME="dd-forwarder-vnet"
VNET_ADDRESS="10.100.0.0/16"
ACA_SUBNET_NAME="aca-subnet"
ACA_SUBNET_PREFIX="10.100.0.0/23"   # /23 minimum for Container App Environments
PE_SUBNET_NAME="pe-subnet"
PE_SUBNET_PREFIX="10.100.2.0/28"

TEMPLATE="$(dirname "$0")/dist/forwarder.json"
# ──────────────────────────────────────────────────────────────────────────────

az account set --subscription "$SUBSCRIPTION_ID"

echo "==> Waiting for resource group $RESOURCE_GROUP to be ready..."
until az group show --name "$RESOURCE_GROUP" --query "properties.provisioningState" --output tsv 2>/dev/null | grep -qv "Deleting" || ! az group show --name "$RESOURCE_GROUP" --output none 2>/dev/null; do
  echo "   Resource group still deleting, waiting 10s..."
  sleep 10
done

echo "==> Creating resource group $RESOURCE_GROUP in $LOCATION (if not exists)..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "==> Cleaning up existing resources (in dependency order)..."
# Container App Job -> Environment -> Private Endpoint -> Subnets -> VNet
az containerapp job delete \
  --resource-group "$RESOURCE_GROUP" --name "datadog-log-forwarder" --yes --output none 2>/dev/null || true
az containerapp env delete \
  --resource-group "$RESOURCE_GROUP" --name "datadog-log-forwarder-env" --yes --output none 2>/dev/null || true
az network private-endpoint delete \
  --resource-group "$RESOURCE_GROUP" --name "$(az storage account list \
    --resource-group "$RESOURCE_GROUP" \
    --query "[?starts_with(name,'ddlog')].name" --output tsv 2>/dev/null | head -1)-blob-pe" \
  --output none 2>/dev/null || true
az network private-dns link vnet delete \
  --resource-group "$RESOURCE_GROUP" \
  --zone-name "privatelink.blob.core.windows.net" \
  --name "blob-dns-zone-vnet-link" --yes --output none 2>/dev/null || true
az network private-dns zone delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "privatelink.blob.core.windows.net" --yes --output none 2>/dev/null || true
az network vnet subnet delete \
  --resource-group "$RESOURCE_GROUP" --vnet-name "$VNET_NAME" --name "$PE_SUBNET_NAME" \
  --output none 2>/dev/null || true
az network vnet subnet delete \
  --resource-group "$RESOURCE_GROUP" --vnet-name "$VNET_NAME" --name "$ACA_SUBNET_NAME" \
  --output none 2>/dev/null || true
az network vnet delete \
  --resource-group "$RESOURCE_GROUP" --name "$VNET_NAME" --output none 2>/dev/null || true

echo "==> Creating VNet $VNET_NAME ($VNET_ADDRESS)..."
az network vnet create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VNET_NAME" \
  --address-prefix "$VNET_ADDRESS" \
  --location "$LOCATION" \
  --output none

echo "==> Creating Container App Environment subnet $ACA_SUBNET_NAME ($ACA_SUBNET_PREFIX)..."
az network vnet subnet create \
  --resource-group "$RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --address-prefix "$ACA_SUBNET_PREFIX" \
  --delegations "Microsoft.App/environments" \
  --output none

echo "==> Creating private endpoint subnet $PE_SUBNET_NAME ($PE_SUBNET_PREFIX)..."
az network vnet subnet create \
  --resource-group "$RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name "$PE_SUBNET_NAME" \
  --address-prefix "$PE_SUBNET_PREFIX" \
  --output none

# Resolve subnet/vnet resource IDs
VNET_ID=$(az network vnet show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VNET_NAME" \
  --query id --output tsv)

ACA_SUBNET_ID=$(az network vnet subnet show \
  --resource-group "$RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name "$ACA_SUBNET_NAME" \
  --query id --output tsv)

PE_SUBNET_ID=$(az network vnet subnet show \
  --resource-group "$RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name "$PE_SUBNET_NAME" \
  --query id --output tsv)

echo "==> Deploying forwarder ARM template..."
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$TEMPLATE" \
  --parameters \
      datadogApiKey="$DD_API_KEY" \
      datadogSite="$DD_SITE" \
      infrastructureSubnetId="$ACA_SUBNET_ID" \
      vnetId="$VNET_ID" \
      storagePrivateEndpointSubnetId="$PE_SUBNET_ID" \
  --output table

echo ""
echo "==> Verifying deployment..."

STORAGE_ACCOUNT=$(az storage account list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?starts_with(name,'ddlog')].name" --output tsv | head -1)

echo "Storage account: $STORAGE_ACCOUNT"

PUBLIC_ACCESS=$(az storage account show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --query "publicNetworkAccess" --output tsv)
echo "  publicNetworkAccess: $PUBLIC_ACCESS (expected: Disabled)"

PE_STATE=$(az network private-endpoint show \
  --resource-group "$RESOURCE_GROUP" \
  --name "${STORAGE_ACCOUNT}-blob-pe" \
  --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status" \
  --output tsv 2>/dev/null || echo "not found")
echo "  Private endpoint connection state: $PE_STATE (expected: Approved)"

DNS_ZONE=$(az network private-dns zone show \
  --resource-group "$RESOURCE_GROUP" \
  --name "privatelink.blob.core.windows.net" \
  --query name --output tsv 2>/dev/null || echo "not found")
echo "  Private DNS zone: $DNS_ZONE"

ACA_ENV=$(az containerapp env show \
  --resource-group "$RESOURCE_GROUP" \
  --name "datadog-log-forwarder-env" \
  --query "properties.vnetConfiguration.infrastructureSubnetId" \
  --output tsv 2>/dev/null || echo "not found")
echo "  Container App Env subnet: $ACA_ENV"

echo ""
echo "==> Triggering a manual job run..."
JOB_NAME=$(az containerapp job list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].name" --output tsv)
az containerapp job start \
  --resource-group "$RESOURCE_GROUP" \
  --name "$JOB_NAME" \
  --output none
echo "  Job '$JOB_NAME' started. Monitor at:"
echo "  https://portal.azure.com/#resource/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/jobs/$JOB_NAME/executions"

echo ""
echo "Done. To clean up: az group delete --name $RESOURCE_GROUP --yes --no-wait"
