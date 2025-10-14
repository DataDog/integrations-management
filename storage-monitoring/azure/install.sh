#!/bin/bash
set -euo pipefail

# Datadog Storage Monitoring – Azure Blob Inventory bootstrap (HNS-aware)
# - Creates an inventory container (if needed)
# - Adds a Blob Inventory policy per account (HNS-safe)
# - Grants Storage Blob Data Reader to the provided App Registration on that container
#
# Usage:
#   ./install.sh <app_registration_client_id> <subscription_id> <comma_separated_storage_account_names> [<container_name>]

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <app_registration_client_id> <subscription_id> <comma_separated_storage_account_names> [<container_name>]"
    exit 1
fi

client_id="$1"
subscription_id="$2"
storage_accounts="$3"
container_name="${4:-datadog-storage-monitoring}"

echo "Starting Datadog Storage Monitoring Setup with the following parameters:
  - App Registration Client ID: $client_id
  - Subscription ID: $subscription_id
  - Storage Accounts: $storage_accounts
  - Inventory Container Name: $container_name
"

# Set subscription
if ! az account set --subscription "$subscription_id"; then
    echo "Error: Failed to set subscription $subscription_id. Please check if the subscription ID is valid."
    exit 1
fi

# Resolve principal object id of the app registration
principal_id=$(az ad sp show --id "$client_id" --query "id" --output tsv 2>/dev/null || true)
if [ -z "${principal_id:-}" ]; then
    echo "Error: App Registration with client ID $client_id not found."
    exit 1
fi

# Helper: Determine if this account kind supports Blob Inventory
supports_inventory() {
    case "$(tr '[:upper:]' '[:lower:]'<<<"$1")" in
    storagev2 | blockblobstorage | blobstorage) return 0 ;;
    *) return 1 ;;
    esac
}

# Helper: Construct an inventory policy JSON tailored to HNS/non-HNS
#   Arg1 = container name
#   Arg2 = is_hns (true|false)
build_policy_json() {
    local _container="$1"
    local _is_hns="$2"

    if [[ "$_is_hns" == "true" ]]; then
        # HNS: only blockBlob; no versions included and no version fields
        cat <<JSON
{
  "enabled": true,
  "destination": "$_container",
  "rules": [{
    "name": "$_container",
    "enabled": true,
    "destination": "$_container",
    "definition": {
      "filters": {
        "blobTypes": ["blockBlob"],
        "prefixMatch": [],
        "excludePrefix": ["$_container"],
        "includeSnapshots": false,
        "includeBlobVersions": false
      },
      "format": "csv",
      "objectType": "blob",
      "schedule": "daily",
      "schemaFields": [
        "Name","Creation-Time","AccessTier","Last-Modified","LastAccessTime","Content-Length","ServerEncrypted"
      ]
    }
  }]
}
JSON
    else
        # Non-HNS: include all blob types and blob versions; include required version fields
        cat <<JSON
{
  "enabled": true,
  "destination": "$_container",
  "rules": [{
    "name": "$_container",
    "enabled": true,
    "destination": "$_container",
    "definition": {
      "filters": {
        "blobTypes": ["blockBlob", "appendBlob", "pageBlob"],
        "prefixMatch": [],
        "excludePrefix": ["$_container"],
        "includeSnapshots": false,
        "includeBlobVersions": true
      },
      "format": "csv",
      "objectType": "blob",
      "schedule": "daily",
      "schemaFields": [
        "Name","Creation-Time","AccessTier","Last-Modified","LastAccessTime","Content-Length","ServerEncrypted",
        "VersionId","IsCurrentVersion"
      ]
    }
  }]
}
JSON
    fi
}

# Process each selected storage account
IFS=',' read -r -a accounts <<<"$storage_accounts"
for storage_account in "${accounts[@]}"; do
    storage_account="$(echo -n "$storage_account" | xargs)" # trim
    if [ -z "$storage_account" ]; then
        continue
    fi

    echo "----"
    echo "Setting up storage account: $storage_account"

    # Fetch account basics
    if ! account_json=$(az storage account show --name "$storage_account" --output json 2>/dev/null); then
        echo "  - Error: Storage account $storage_account not found. Skipping..."
        continue
    fi
    storage_account_id=$(echo "$account_json" | jq -r .id 2>/dev/null || az storage account show --name "$storage_account" --query "id" -o tsv)
    kind=$(echo "$account_json" | jq -r .kind 2>/dev/null || az storage account show --name "$storage_account" --query "kind" -o tsv)
    is_hns=$(echo "$account_json" | jq -r .isHnsEnabled 2>/dev/null || az storage account show --name "$storage_account" --query "isHnsEnabled" -o tsv)

    echo "  - Kind: $kind | HNS: $is_hns"

    # If this account kind doesn't support Blob Inventory, skip any calls that would error out.
    if ! supports_inventory "$kind"; then
        echo "  - Skipping: Blob Inventory not supported for account kind '$kind'."
        continue
    fi

    # Ensure the target container exists (only if we're going to set an inventory policy)
    if ! az storage container show --name "$container_name" --account-name "$storage_account" --auth-mode login --output none 2>/dev/null; then
        echo "  - Creating container '$container_name' for inventory reports"
        created=$(az storage container create --account-name "$storage_account" --name "$container_name" --auth-mode login --output tsv || true)
        if [[ "$created" != "True" ]]; then
            echo "  - Warning: Could not create container '$container_name' in $storage_account (Created=$created). Skipping policy setup for this account."
            continue
        fi
    else
        echo "  - Container '$container_name' already exists"
    fi

    # Build an HNS-aware policy payload and create/update the policy
    echo "  - Applying Blob Inventory policy (HNS-aware)"
    INVENTORY_POLICY_JSON="$(build_policy_json "$container_name" "$is_hns")"

    if ! az storage account blob-inventory-policy create \
        --account-name "$storage_account" \
        --policy "$INVENTORY_POLICY_JSON" \
        --only-show-errors --output none; then
        echo "  - Warning: Failed to add Blob Inventory policy to $storage_account. Skipping role assignment for this account."
        continue
    fi

    # Grant the app registration read access to the inventory container
    echo "  - Granting 'Storage Blob Data Reader' to $client_id on container scope"
    scope="$storage_account_id/blobServices/default/containers/$container_name"
    # Ignore error if assignment already exists
    az role assignment create \
        --assignee "$principal_id" \
        --role "Storage Blob Data Reader" \
        --scope "$scope" \
        --only-show-errors --output none || echo "  - Note: Role assignment may already exist."

done

echo
echo "======================================================================================================================"
echo "Datadog Storage Monitoring Setup completed. Return to the Datadog UI and click Confirm to finish the setup."
echo "======================================================================================================================"
