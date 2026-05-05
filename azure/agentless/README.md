# Azure Agentless Scanner Setup

This script automates the deployment of Datadog Agentless Scanner on Azure using Terraform.

## Prerequisites

- Azure Cloud Shell or a machine with:
  - `az` CLI installed and authenticated (`az login`)
  - `terraform` CLI installed (>= 1.0)
- Azure subscriptions with appropriate permissions:
  - `Owner` (or a role granting role-assignment write + resource creation) on the scanner subscription
  - A role granting `Microsoft.Authorization/roleAssignments/write` on each scanned subscription (e.g., `User Access Administrator` or `Owner`), so the scanner's managed identity can be granted the roles it needs to snapshot and read disks
- The following resource providers registered in the scanner subscription (auto-registered by the script when possible): `Microsoft.Compute`, `Microsoft.Network`, `Microsoft.ManagedIdentity`, `Microsoft.Storage`, `Microsoft.KeyVault`, `Microsoft.Authorization`

## Usage

### Deploy

Run the script with environment variables:

```bash
DD_API_KEY="your-api-key" \
DD_APP_KEY="your-app-key" \
DD_SITE="datadoghq.com" \
WORKFLOW_ID="uuid-from-datadog-ui" \
SCANNER_SUBSCRIPTION="00000000-0000-0000-0000-000000000000" \
SCANNER_LOCATIONS="eastus" \
SUBSCRIPTIONS_TO_SCAN="sub-id-1,sub-id-2,sub-id-3" \
python azure_agentless_setup.pyz deploy
```

#### Deploy Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DD_API_KEY` | Yes | Datadog API key with Remote Configuration enabled |
| `DD_APP_KEY` | Yes | Datadog Application key |
| `DD_SITE` | Yes | Datadog site (e.g., `datadoghq.com`, `datadoghq.eu`) |
| `WORKFLOW_ID` | Yes | Workflow ID from Datadog UI (UUID) for tracking setup progress |
| `SCANNER_SUBSCRIPTION` | Yes | Azure subscription ID where the scanner will be deployed |
| `SCANNER_LOCATIONS` | Yes | Comma-separated list of Azure locations (max 4) for scanners (e.g., `eastus` or `eastus,westeurope`) |
| `SUBSCRIPTIONS_TO_SCAN` | Yes | Comma-separated list of Azure subscription IDs to scan |
| `SCANNER_RESOURCE_GROUP` | No | Resource group name for scanner resources (default: `datadog-agentless-scanner`). Cannot be changed after the first deploy — to switch resource groups, run `destroy` first. |
| `TF_STATE_STORAGE_ACCOUNT` | No | Custom Azure Storage Account for Terraform state (see below) |

Re-running `deploy` with new `SCANNER_LOCATIONS` or `SUBSCRIPTIONS_TO_SCAN` values merges them with the existing deployment (stored in the Terraform state storage account) instead of replacing it.

### Destroy

To remove the scanner infrastructure:

```bash
DD_API_KEY="your-api-key" \
DD_APP_KEY="your-app-key" \
DD_SITE="datadoghq.com" \
SCANNER_SUBSCRIPTION="00000000-0000-0000-0000-000000000000" \
python azure_agentless_setup.pyz destroy
```

If only one installation exists locally, `SCANNER_SUBSCRIPTION` can be omitted and will be inferred automatically.

#### Destroy Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DD_API_KEY` | Yes | Datadog API key (used to disable scan options in Datadog) |
| `DD_APP_KEY` | Yes | Datadog Application key |
| `DD_SITE` | Yes | Datadog site |
| `SCANNER_SUBSCRIPTION` | No* | Scanner subscription ID (*inferred if only one installation exists locally) |
| `SCANNER_RESOURCE_GROUP` | No* | Resource group name (*required only if metadata does not contain it, e.g., installations created before this field was added) |
| `TF_STATE_STORAGE_ACCOUNT` | No | Custom Storage Account (if used during deploy) |
| `SCANNER_LOCATIONS` | No* | Locations to destroy (*fallback only if deployment metadata cannot be read) |
| `SUBSCRIPTIONS_TO_SCAN` | No* | Subscriptions to clean up (*fallback only if deployment metadata cannot be read) |

The destroy command will:
1. Run `terraform destroy` (prompts for confirmation)
2. Disable the Agentless scan options in Datadog for each previously configured subscription
3. Ask if you want to delete the Key Vault holding the API key (kept by default to allow reuse)
4. Leave the resource group and Terraform state storage account intact (manual deletion instructions provided)

### Terraform State Storage

Terraform state is stored in an Azure Storage Account (blob container `tfstate`, key `datadog-agentless.tfstate`) to ensure persistence across runs and enable future updates or teardown.

**Default behavior:** A storage account with a deterministic name derived from the scanner subscription ID (e.g., `datadog<hash>`) is automatically created inside the scanner resource group. If it already exists (e.g., from a previous run), it is reused. The `azurerm` backend is configured with `use_azuread_auth = true`, and the script grants the current user the `Storage Blob Data Contributor` role on the account.

**Custom storage account:** Set `TF_STATE_STORAGE_ACCOUNT` to use your own account:
```bash
TF_STATE_STORAGE_ACCOUNT="my-existing-account" \
SCANNER_SUBSCRIPTION="00000000-0000-0000-0000-000000000000" \
# ... other variables ...
python azure_agentless_setup.pyz deploy
```
The custom storage account must already exist in `SCANNER_RESOURCE_GROUP`; the script will not create it.

## What it does

1. **Validates prerequisites** - Checks Datadog credentials, Azure authentication, subscription access, required RBAC actions, and registers required resource providers
2. **Creates state storage** - Ensures the resource group, Storage Account, and `tfstate` blob container exist, and grants the current user blob data access
3. **Stores API key in Key Vault** - Creates an RBAC-authorized Key Vault (or recovers a soft-deleted one) and stores the Datadog API key as a secret
4. **Generates Terraform configuration** - Creates `main.tf` referencing the `terraform-module-datadog-agentless-scanner` Azure sub-modules (managed identity, roles, custom data, virtual network, VMSS), one virtual network + VMSS per location
5. **Runs Terraform** - Executes `terraform init` and `terraform apply`

Deployment metadata (locations, subscriptions, resource group) is written to the state storage account after a successful apply so that later `deploy` runs can merge new inputs and `destroy` runs can recover the full configuration without local state.

## Resources Created

- **Scanner Subscription / Resource Group:**
  - Storage Account + `tfstate` blob container (Terraform state)
  - Key Vault with the Datadog API key secret
  - User-assigned managed identity (shared across locations)
  - Role definitions and assignments for the managed identity
  - Per location: virtual network, NAT gateway, subnet, and Virtual Machine Scale Set running the scanner

- **Scanned Subscriptions:**
  - Role assignments granting the scanner's managed identity the permissions needed to snapshot and read disks

## Building

From the `azure/` directory:

```bash
./agentless/build.sh
```

## Testing

```bash
cd agentless
pip install -r ../dev_requirements.txt
pytest
```
