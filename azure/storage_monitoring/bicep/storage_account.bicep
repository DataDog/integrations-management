// Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

// This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

// Sets up Datadog Storage Monitoring on one storage account: inventory container, daily blob
// inventory rule, optional last-access tracking, and read access for the Datadog service principal.
// Mirrors install.sh, including its HNS (Data Lake Gen2) handling.
targetScope = 'resourceGroup'

@description('Name of an existing StorageV2, BlockBlobStorage or BlobStorage account. Other kinds do not support blob inventory.')
param storageAccountName string

@description('Container that receives the inventory reports.')
param inventoryContainerName string

@description('Object ID (not client ID) of the Datadog integration service principal.')
param datadogServicePrincipalObjectId string

@description('Turn on last-access tracking so inventory reports fill LastAccessTime. Existing blob service settings are kept.')
param enableLastAccessTracking bool

@description('Current inventory rules on the account other than the Datadog rule. An account has a single inventory policy, which this module replaces, so these rules are written back.')
param existingInventoryRules array

@description('Inventory CSV columns. VersionId and IsCurrentVersion are dropped on HNS accounts, which do not support blob versions.')
param inventorySchemaFields string[]

var storageBlobDataReaderRoleDefinitionId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var blobVersionSchemaFields = ['VersionId', 'IsCurrentVersion']

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource existingBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storageAccount
  name: 'default'
}

var isHierarchicalNamespaceEnabled = storageAccount.properties.?isHnsEnabled ?? false

// A PUT on blobServices/default resets the settings it omits (for example soft delete), so the
// current settings are copied and only last-access tracking is changed.
resource blobServiceWithLastAccessTracking 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (enableLastAccessTracking) {
  parent: storageAccount
  name: 'default'
  properties: union(existingBlobService.properties, {
    lastAccessTimeTrackingPolicy: {
      enable: true
      name: 'AccessTimeTracking'
      trackingGranularityInDays: 1
      blobType: ['blockBlob']
    }
  })
}

resource inventoryContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: existingBlobService
  name: inventoryContainerName
  properties: {
    publicAccess: 'None'
  }
  dependsOn: [
    blobServiceWithLastAccessTracking
  ]
}

resource inventoryPolicy 'Microsoft.Storage/storageAccounts/inventoryPolicies@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    policy: {
      enabled: true
      type: 'Inventory'
      rules: concat(existingInventoryRules, [
        {
          enabled: true
          name: inventoryContainerName
          destination: inventoryContainer.name
          definition: {
            format: 'Csv'
            schedule: 'Daily'
            objectType: 'Blob'
            schemaFields: isHierarchicalNamespaceEnabled
              ? filter(inventorySchemaFields, field => !contains(blobVersionSchemaFields, field))
              : inventorySchemaFields
            filters: {
              blobTypes: isHierarchicalNamespaceEnabled ? ['blockBlob'] : ['blockBlob', 'appendBlob', 'pageBlob']
              excludePrefix: [inventoryContainerName]
              includeBlobVersions: !isHierarchicalNamespaceEnabled
              includeSnapshots: false
            }
          }
        }
      ])
    }
  }
}

resource datadogInventoryReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: inventoryContainer
  name: guid(inventoryContainer.id, datadogServicePrincipalObjectId, storageBlobDataReaderRoleDefinitionId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleDefinitionId)
    principalId: datadogServicePrincipalObjectId
    principalType: 'ServicePrincipal'
    description: 'Datadog Storage Monitoring: read blob inventory reports'
  }
}

output inventoryContainerResourceId string = inventoryContainer.id
output isHierarchicalNamespaceEnabled bool = isHierarchicalNamespaceEnabled
