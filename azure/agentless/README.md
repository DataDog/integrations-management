# Azure Agentless Scanner Setup

This script automates the deployment of Datadog Agentless Scanner on Azure using Terraform.

## Prerequisites

- Azure Cloud Shell or a machine with:
  - `az` CLI installed and authenticated (`az login`)
  - `terraform` CLI installed (>= 1.0)
- Azure permissions (see [Permissions](#permissions) for the delegated, least-privilege variant if the SWE running the script is not subscription `Owner`):
  - `Owner` on the scanner subscription, **or** the custom role described below at the scanner subscription scope plus both `Contributor` and `User Access Administrator` on the scanner resource group (the latter is required so the script can grant itself `Storage Blob Data Contributor` on the state Storage Account and `Key Vault Secrets Officer` on the Key Vault)
  - A role granting `Microsoft.Authorization/roleAssignments/write` and `Microsoft.Authorization/roleDefinitions/write` on each scanned subscription (e.g., `User Access Administrator` or `Owner`), so the scanner's managed identity can be granted scan permissions and the custom scanning role can list the scan-target subscription in its `assignableScopes`
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
| `SCANNER_RESOURCE_GROUP` | No | Resource group name for scanner resources (default: `datadog-agentless-scanner`). When unset, the script auto-discovers the resource group from the `DatadogAgentlessScanner=true` tag the previous deploy applied — this is what makes re-runs from a fresh Cloud Shell session work without re-setting the env var. To relocate an existing deployment to a different resource group, run `destroy` first. |
| `TF_STATE_STORAGE_ACCOUNT` | No | Custom Azure Storage Account for Terraform state (see below) |

Re-running `deploy` with new `SCANNER_LOCATIONS` or `SUBSCRIPTIONS_TO_SCAN` values merges them with the existing deployment (stored in the Terraform state storage account) instead of replacing it.

Only one Agentless Scanner deployment is supported per scanner subscription. If the script detects more than one tagged deployment in the scanner subscription, `deploy` fails fast and lists the resource groups so you can `destroy` the ones you no longer need — it never picks one silently. (On `destroy`, set `SCANNER_RESOURCE_GROUP` to choose which one to remove.)

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
| `SCANNER_RESOURCE_GROUP` | No* | Resource group name (*auto-discovered from the `DatadogAgentlessScanner=true` tag when exactly one tagged deployment exists in the scanner subscription; required when the resource group was not tagged at deploy time — typically an admin-pre-created resource group — or when multiple tagged deployments exist) |
| `TF_STATE_STORAGE_ACCOUNT` | No | Custom Storage Account (if used during deploy) |
| `SCANNER_LOCATIONS` | No* | Locations to destroy (*fallback only if deployment metadata cannot be read) |
| `SUBSCRIPTIONS_TO_SCAN` | No* | Subscriptions to clean up (*fallback only if deployment metadata cannot be read) |

The destroy command will:
1. Run `terraform destroy` (prompts for confirmation)
2. Disable the Agentless scan options in Datadog for each previously configured subscription
3. Remove the deployment metadata blob from the state Storage Account on a successful run; if scan-options cleanup partially failed, the metadata is kept so a follow-up `destroy` can still find the subscription list
4. Ask if you want to delete the Key Vault holding the API key (kept by default to allow reuse)
5. Leave the resource group and Terraform state storage account intact (manual deletion instructions provided)

Unlike `deploy`, `destroy` does not run a permission preflight: missing role assignments surface as `terraform destroy` errors rather than a pre-run summary.

### Terraform State Storage

Terraform state is stored in an Azure Storage Account (blob container `tfstate`, key `datadog-agentless.tfstate`) to ensure persistence across runs and enable future updates or teardown.

**Default behavior:** A storage account named `datadog<install-id>` (where `install-id` is the first 12 hex chars of `sha256("<scanner-subscription>|<resource-group>")`) is created inside the scanner resource group. Two deploys against the same `(SCANNER_SUBSCRIPTION, SCANNER_RESOURCE_GROUP)` pair resolve to the same Storage Account name and are therefore the same install. Re-running with a different `SCANNER_RESOURCE_GROUP` resolves to a different Storage Account, which is why this combination uniquely identifies an installation. The `azurerm` backend is configured with `use_azuread_auth = true`, and the script grants the current user the `Storage Blob Data Contributor` role on the account.

**Custom storage account:** Set `TF_STATE_STORAGE_ACCOUNT` to use your own account:
```bash
TF_STATE_STORAGE_ACCOUNT="my-existing-account" \
SCANNER_SUBSCRIPTION="00000000-0000-0000-0000-000000000000" \
# ... other variables ...
python azure_agentless_setup.pyz deploy
```
The custom storage account must already exist in `SCANNER_RESOURCE_GROUP`; the script will not create it.

## What it does

1. **Discovers existing deployment** - Lists resource groups in the scanner subscription tagged `DatadogAgentlessScanner=true`. If exactly one is found and `SCANNER_RESOURCE_GROUP` is unset, the deployment is silently reused; if it disagrees with an explicitly set `SCANNER_RESOURCE_GROUP`, deploy fails with guidance to either reuse it or destroy first; if more than one is found, deploy fails (single-install policy)
2. **Validates prerequisites** - Checks Datadog credentials, Azure authentication, subscription access, required RBAC actions, and registers required resource providers
3. **Creates state storage** - Ensures the resource group, Storage Account, and `tfstate` blob container exist, and grants the current user blob data access. The resource group is tagged with `Datadog=true` and `DatadogAgentlessScanner=true` only when the script creates it; resource groups that already exist (e.g., admin-pre-created) are left untagged so the marker never appears on resources the script does not own
4. **Stores API key in Key Vault** - Creates an RBAC-authorized Key Vault (or recovers a soft-deleted one) and stores the Datadog API key as a secret
5. **Generates Terraform configuration** - Creates `main.tf` referencing the `terraform-module-datadog-agentless-scanner` Azure sub-modules (managed identity, roles, custom data, virtual network, VMSS), one virtual network + VMSS per location
6. **Runs Terraform** - Executes `terraform init` and `terraform apply`

Deployment metadata (locations, subscriptions, resource group, `install-id`) is written to the state storage account after a successful apply so that later `deploy` runs can merge new inputs and `destroy` runs can recover the full configuration without local state.

## Resources Created

- **Scanner Subscription / Resource Group:**
  - Storage Account + `tfstate` blob container (Terraform state)
  - Key Vault with the Datadog API key secret
  - User-assigned managed identity (shared across locations)
  - Role definitions and assignments for the managed identity
  - Per location: virtual network, NAT gateway, subnet, and Virtual Machine Scale Set running the scanner

- **Scanned Subscriptions:**
  - Role assignments granting the scanner's managed identity the permissions needed to snapshot and read disks

## Permissions

The simplest path is to run the setup as `Owner` on the scanner subscription and on every scanned subscription. Many enterprise tenants instead pre-create the resource group and grant the engineer running the setup a least-privilege custom role; this section documents that delegated path.

The setup needs three independent grants:

1. **Scanner resource group** — write access to the resources created inside the RG (Storage Account, Key Vault, managed identity, VNets, VMSS) and the ability to grant the running user data-plane access on the SA and KV.
2. **Scanner subscription** — read access for discovery + write access to create the custom scanning role definition at the subscription scope.
3. **Each scanned subscription** — write access to attach the scanning role to the managed identity at the scan target's scope, plus the matching `roleDefinitions/write` so the custom role can declare the scan target in its `assignableScopes`.

### 1. Scanner resource group

Pre-create the resource group with the desired name and grant the engineer:

- `Contributor` on the RG — covers Storage Account, Key Vault, managed identity, virtual network, NAT gateway, and VMSS creation.
- `User Access Administrator` on the RG — covers the `roleAssignments/write` needed by the script to grant itself `Storage Blob Data Contributor` on the state Storage Account and `Key Vault Secrets Officer` on the Key Vault.

The Terraform-state Storage Account is created **inside this RG** by default, so the engineer does not need any additional subscription-wide Storage permissions for state.

### 2. Scanner subscription — custom role for the engineer

Create the following custom role at the scanner subscription scope. It bundles every read action the setup performs at the subscription level plus the `roleDefinitions/write` introduced by the custom scanning role:

```json
{
  "Name": "Datadog Agentless Scanner Deployer (scanner subscription)",
  "Description": "Permissions required by the engineer running the Datadog Agentless Scanner Azure setup on the scanner subscription.",
  "Actions": [
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Resources/subscriptions/resourceProviders/read",
    "Microsoft.Resources/subscriptions/resourceProviders/register/action",
    "Microsoft.KeyVault/locations/deletedVaults/read",
    "Microsoft.Authorization/permissions/read",
    "Microsoft.Authorization/roleAssignments/read",
    "Microsoft.Authorization/roleAssignments/write",
    "Microsoft.Authorization/roleAssignments/delete",
    "Microsoft.Authorization/roleDefinitions/read",
    "Microsoft.Authorization/roleDefinitions/write",
    "Microsoft.Authorization/roleDefinitions/delete"
  ],
  "AssignableScopes": [
    "/subscriptions/<scanner-subscription-id>"
  ]
}
```

Notes:

- `resourceProviders/register/action` is only exercised when the required providers are not pre-registered. You can drop it from the role and register the providers manually instead (see the prerequisites list).
- `subscriptions/resourceGroups/read` is needed for tag-based discovery of existing deployments (the `az group list --tag DatadogAgentlessScanner=true` lookup).
- `roleDefinitions/write` is needed because the Terraform module creates a custom scanning role whose primary scope is the scanner subscription.

### 3. Each scanned subscription — custom role for the engineer

For every subscription listed in `SUBSCRIPTIONS_TO_SCAN` (other than the scanner subscription), create the same custom role at the scan-target scope with just the role-management actions:

```json
{
  "Name": "Datadog Agentless Scanner Deployer (scan target)",
  "Description": "Permissions required by the engineer running the Datadog Agentless Scanner setup, on each scanned subscription.",
  "Actions": [
    "Microsoft.Authorization/permissions/read",
    "Microsoft.Authorization/roleAssignments/read",
    "Microsoft.Authorization/roleAssignments/write",
    "Microsoft.Authorization/roleAssignments/delete",
    "Microsoft.Authorization/roleDefinitions/read",
    "Microsoft.Authorization/roleDefinitions/write",
    "Microsoft.Authorization/roleDefinitions/delete"
  ],
  "AssignableScopes": [
    "/subscriptions/<scan-target-subscription-id>"
  ]
}
```

The same role is sufficient for both `deploy` and `destroy`. On `deploy`, the preflight will fail fast with a clear error listing the missing actions if any of the above are not granted; on `destroy`, missing actions surface during `terraform destroy` (no preflight is run).

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
