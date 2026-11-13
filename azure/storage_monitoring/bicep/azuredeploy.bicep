// Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

// This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

// Datadog Storage Monitoring onboarding for one subscription: the template equivalent of install.sh.
// Deploy with `az deployment sub create`, or from the Datadog UI's Deploy to Azure link.
targetScope = 'subscription'

type storageAccountToOnboard = {
  @description('Storage account name.')
  name: string

  @description('Resource group of the storage account.')
  resourceGroup: string

  @description('Turn on last-access tracking. Defaults to false.')
  enableLastAccessTracking: bool?

  @description('Current inventory rules on the account other than the Datadog rule. They are kept. Defaults to none.')
  existingInventoryRules: array?
}

@description('Datadog UI workflow ID. Returned in the outputs so Datadog can match the deployment to the onboarding session.')
param workflowId string = ''

@description('Object ID (not client ID) of the Datadog integration service principal. Manually: az ad sp show --id <client_id> --query id -o tsv')
param datadogServicePrincipalObjectId string

@description('Storage accounts to onboard in this subscription.')
@minLength(1)
param storageAccounts storageAccountToOnboard[]

@description('Container that receives the inventory reports.')
param inventoryContainerName string = 'datadog-storage-monitoring'

@description('Inventory CSV columns. The Datadog inventory reader requires Name, AccessTier, Last-Modified, Content-Length and ServerEncrypted.')
param inventorySchemaFields string[] = [
  'Name'
  'Creation-Time'
  'AccessTier'
  'AccessTierInferred'
  'BlobType'
  'Last-Modified'
  'LastAccessTime'
  'Content-Length'
  'ServerEncrypted'
  'VersionId'
  'IsCurrentVersion'
]

module storageAccountSetup 'storage_account.bicep' = [
  for account in storageAccounts: {
    name: take('datadog-storage-monitoring-${account.name}', 64)
    scope: resourceGroup(account.resourceGroup)
    params: {
      storageAccountName: account.name
      inventoryContainerName: inventoryContainerName
      datadogServicePrincipalObjectId: datadogServicePrincipalObjectId
      enableLastAccessTracking: account.?enableLastAccessTracking ?? false
      existingInventoryRules: account.?existingInventoryRules ?? []
      inventorySchemaFields: inventorySchemaFields
    }
  }
]

output workflowId string = workflowId
output inventoryContainerResourceIds string[] = [
  for (account, index) in storageAccounts: storageAccountSetup[index].outputs.inventoryContainerResourceId
]
