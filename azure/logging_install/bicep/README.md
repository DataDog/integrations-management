# Arm Template

(this assumes your current directory is the root of the repo)

## Setup:

```bash
# ensure the az cli is installed
brew install azure-cli
# install the bicep cli
az bicep install
az login
```

## Deploy

`azuredeploy.bicep` is the entrypoint and is scoped to a management group (it fans out into
`control_plane_resource_group.bicep`, `control_plane.bicep`, `subscription_permissions.bicep`,
`initial_run.bicep`, etc.), so it must be deployed with `az deployment mg create`:

```bash
az deployment mg create \
  --management-group-id <YOUR_MANAGEMENT_GROUP_ID> \
  --location <deployment-metadata-region, e.g. eastus> \
  --template-file logging_install/bicep/azuredeploy.bicep \
  --parameters \
    monitoredSubscriptions='["<sub1>","<sub2>"]' \
    controlPlaneLocation=eastus \
    controlPlaneSubscriptionId=<CONTROL_PLANE_SUBSCRIPTION_ID> \
    controlPlaneResourceGroupName=datadog_control_plane \
    datadogApiKey=<DD_API_KEY> \
    datadogSite=datadoghq.com
```

Notes:
- `monitoredSubscriptions` must be a JSON array **encoded as a string** (e.g.
  `'["sub1","sub2"]'`), not a comma-separated list — the template parses it with `json(...)`
  (see `azuredeploy.bicep`) and passing a plain comma-separated string fails with
  `InvalidTemplate: Unable to evaluate the template language function 'json'`.
- `--location` is only where the management-group deployment's metadata is stored; the actual
  resources are created in `controlPlaneLocation`/`controlPlaneSubscriptionId`. However, MG-scoped
  deployments are tracked by deployment **name** (defaults to the template filename, i.e.
  `azuredeploy`), and a given name is pinned to whichever `--location` it was first created with.
  Re-running with a different `--location` fails with `InvalidDeploymentLocation`. Either reuse
  the original `--location`, or pass a unique `--name` (e.g. `--name azuredeploy-$(whoami)`) to
  deploy to a different location.
- Add `--what-if` to preview the changes without applying them, or
  `--confirm-with-what-if` to review before confirming.
- Optional parameters (`resourceTagFilters`, `piiScrubberRules`, `datadogTelemetry`, `logLevel`,
  `imageRegistry`, `storageAccountUrl`, `storageAccountSas`) can be added the same way; see
  `azuredeploy.bicep` for the full parameter list and defaults.
- You can also build the compiled ARM JSON with `logging_install/build.sh` and deploy
  `dist/azuredeploy.json` via `--template-file logging_install/dist/azuredeploy.json` instead of
  the `.bicep` source.

## Manual Forwarder Deployment (Azure Portal)

`forwarder.bicep` deploys only the Container App job and storage account — no management group scope required. It can be deployed via the Azure Portal using the included UI definition for a guided, form-based experience.

**Portal deploy link** (uses the files from the `main` branch of this repo):

```
https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FDataDog%2Fintegrations-management%2Fmain%2Fazure%2Flogging_install%2Fdist%2Fforwarder.json/uiFormDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2FDataDog%2Fintegrations-management%2Fmain%2Fazure%2Flogging_install%2Fdist%2FmanualForwarderUiDefinition.json
```

**Or via CLI:**

```bash
az deployment group create \
  --resource-group <RESOURCE_GROUP> \
  --template-file logging_install/bicep/forwarder.bicep \
  --parameters datadogApiKey=<DD_API_KEY>
```

**Virtual Network integration** can be enabled by passing `enableVnetIntegration=true`. When enabled, a virtual network, private endpoint for storage, and private DNS zone are created automatically. To use existing networking resources, pass `createNewVnet=false` along with the existing resource IDs:

```bash
az deployment group create \
  --resource-group <RESOURCE_GROUP> \
  --template-file logging_install/bicep/forwarder.bicep \
  --parameters \
    datadogApiKey=<DD_API_KEY> \
    enableVnetIntegration=true \
    createNewVnet=false \
    existingVnetId=<VNET_RESOURCE_ID> \
    existingInfrastructureSubnetId=<ACA_SUBNET_RESOURCE_ID>
```

Note: Azure does not support adding a virtual network to an existing Container App Environment after deployment. Virtual network integration must be configured at creation time.
