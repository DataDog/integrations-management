# Azure Diagnostic Settings Policy Initiative

Deploys an Azure Policy initiative that configures diagnostic settings on supported resource types to route logs to a regional storage account.

## Deployment

Registers the initiative and assigns it to the current subscription in a single step.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2FYOUR_GITHUB_RAW_URL%2Ftemplates%2Farm%2Fdeploy.json)

```bash
az deployment sub create \
  --name diag-policies \
  --location eastus \
  --template-file templates/bicep/deploy.bicep \
  --parameters @templates/parameters.example.json
```

## Deploy to Azure button setup

Replace `YOUR_GITHUB_RAW_URL` in the button URL with the base raw URL of this repo, e.g.:

```
https://raw.githubusercontent.com/YOUR_ORG/YOUR_REPO/main
```

The full URL should point to `templates/arm/deploy.json`, URL-encoded.

## Parameters

See [`templates/parameters.example.json`](templates/parameters.example.json) for a full example. Key parameters:

| Parameter | Required | Description |
|---|---|---|
| `storageAccountsByRegion` | Yes | Map of region → storage account resource ID |
| `effect` | No (default: `DeployIfNotExists`) | `DeployIfNotExists`, `AuditIfNotExists`, or `Disabled` |
| `diagnosticSettingName` | No (default: `setByPolicy-Storage`) | Name of the diagnostic setting created on each resource |
| `resourceTypeList` | No (default: all supported types) | Subset of resource types to enforce |
| `tagIncludeFilter` | No (default: `{}`) | Only target resources matching all these tags |
| `tagExcludeFilter` | No (default: `{}`) | Skip resources matching all these tags |

## Remediation

After assignment, existing non-compliant resources are not automatically remediated. Because this is an initiative, the Azure API requires a separate remediation task per policy definition (174 in total). Use this script to create them all:

```bash
EFFECT=$(az policy assignment show \
  --name diag-regional-storage \
  --query 'parameters.effect.value' -o tsv)

if [ "$EFFECT" != "DeployIfNotExists" ]; then
  echo "Remediation only applies to DeployIfNotExists assignments (current effect: $EFFECT)"
  exit 0
fi

# Trigger one subscription-wide scan rather than one per remediation task.
# Wait for it to complete before creating remediation tasks.
echo "Triggering compliance scan..."
az policy state trigger-scan

ASSIGNMENT_ID=$(az policy assignment show \
  --name diag-regional-storage \
  --query id -o tsv)

az policy set-definition show \
  --name diag-regional-storage \
  --query 'policyDefinitions[].policyDefinitionReferenceId' \
  -o tsv | while read -r ref_id; do
    az policy remediation create \
      --name "remediate-${ref_id}" \
      --policy-assignment "$ASSIGNMENT_ID" \
      --definition-reference-id "$ref_id" \
      --resource-discovery-mode ExistingNonCompliant \
      --no-wait
  done
```

`az policy state trigger-scan` waits for the scan to complete before returning. `--no-wait` on each remediation task launches all 174 in parallel rather than sequentially.
