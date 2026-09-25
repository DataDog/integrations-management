// This will deploy just the forwarder container app + storage account needed for the forwarder to work.
// Automated log forwarding setup and scaling will not be set up.
targetScope = 'resourceGroup'

@description('Name of the Container App Managed Environment for the Forwarder')
@minLength(2)
@maxLength(60)
param environmentName string = 'datadog-log-forwarder-env'

@description('Name of the Forwarder Container App Job')
@minLength(1)
@maxLength(260)
param jobName string = 'datadog-log-forwarder'

@description('Name of the Log Storage Account')
@minLength(3)
@maxLength(24)
param storageAccountName string = 'ddlog${uniqueString(resourceGroup().id)}'

@description('The SKU of the storage account')
@allowed([
  'Premium_LRS'
  'Premium_ZRS'
  'Standard_GRS'
  'Standard_GZRS'
  'Standard_LRS'
  'Standard_RAGRS'
  'Standard_RAGZRS'
  'Standard_ZRS'
])
param storageAccountSku string = 'Standard_LRS'

@description('The number of days to retain logs (and internal metrics) in the storage account')
@minValue(1)
param storageAccountRetentionDays int = 1

@secure()
@description('Datadog API Key')
@minLength(32)
@maxLength(32)
param datadogApiKey string

@allowed([
  'datadoghq.com'
  'datadoghq.eu'
  'ap1.datadoghq.com'
  'ap2.datadoghq.com'
  'uk1.datadoghq.com'
  'us3.datadoghq.com'
  'us5.datadoghq.com'
  'ddog-gov.com'
])
param datadogSite string = 'datadoghq.com'

@description('Enable Virtual Network integration: deploys the Container App Environment into a virtual network and disables public access on the storage account (using a private endpoint instead).')
param enableVnetIntegration bool = false

@description('Create a new virtual network and subnets automatically. Set to false to use existing subnets. Only applies when enableVnetIntegration is true.')
param createNewVnet bool = true

@description('Name for the new virtual network. Only used when createNewVnet is true.')
@minLength(1)
param vnetName string = 'datadog-log-forwarder-vnet'

@description('Address space for the new virtual network. Only used when createNewVnet is true.')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Address prefix for the Container App Environment subnet (minimum /23). Only used when createNewVnet is true.')
param acaSubnetPrefix string = '10.0.0.0/23'

@description('Address prefix for the storage private endpoint subnet (minimum /28). Only used when createNewVnet is true.')
param peSubnetPrefix string = '10.0.2.0/28'

@description('Resource ID of an existing virtual network. Required when enableVnetIntegration is true and createNewVnet is false.')
param existingVnetId string = ''

@description('Resource ID of an existing subnet for the Container App Environment. Must be delegated to Microsoft.App/environments and at least /23. Required when enableVnetIntegration is true and createNewVnet is false.')
param existingInfrastructureSubnetId string = ''

@description('Resource ID of an existing subnet for the storage private endpoint. Leave empty to reuse existingInfrastructureSubnetId. Only used when createNewVnet is false.')
param existingStoragePrivateEndpointSubnetId string = ''

@description('Resource ID of an existing Private DNS Zone for blob storage (privatelink.blob.*). Leave empty to create one automatically. Only used when enableVnetIntegration is true and createNewVnet is false.')
param existingPrivateDnsZoneId string = ''

var enableVnet = enableVnetIntegration
var resolvedVnetId = enableVnetIntegration
  ? (createNewVnet ? resourceId('Microsoft.Network/virtualNetworks', vnetName) : existingVnetId)
  : ''
var resolvedAcaSubnetId = enableVnetIntegration
  ? (createNewVnet ? resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'aca-subnet') : existingInfrastructureSubnetId)
  : ''
var resolvedPeSubnetId = enableVnetIntegration
  ? (createNewVnet
      ? resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'pe-subnet')
      : (existingStoragePrivateEndpointSubnetId != '' ? existingStoragePrivateEndpointSubnetId : existingInfrastructureSubnetId))
  : ''
var resolvedPrivateDnsZoneId = enableVnetIntegration
  ? (empty(existingPrivateDnsZoneId)
      ? resourceId('Microsoft.Network/privateDnsZones', 'privatelink.blob.${environment().suffixes.storage}')
      : existingPrivateDnsZoneId)
  : ''

resource newVnet 'Microsoft.Network/virtualNetworks@2023-11-01' = if (enableVnetIntegration && createNewVnet) {
  name: vnetName
  location: resourceGroup().location
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'aca-subnet'
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'Microsoft.App-environments'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'pe-subnet'
        properties: { addressPrefix: peSubnetPrefix }
      }
    ]
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: resourceGroup().location
  sku: {
    name: storageAccountSku
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    publicNetworkAccess: enableVnet ? 'Disabled' : null
    networkAcls: enableVnet ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    } : null
  }
}

resource storageManagementPolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    policy: {
      rules: [
        {
          enabled: true
          name: 'Delete Old Blobs'
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: storageAccountRetentionDays
                }
              }
              snapshot: {
                delete: {
                  daysAfterCreationGreaterThan: storageAccountRetentionDays
                }
              }
            }
            filters: {
              blobTypes: [
                'blockBlob'
                'appendBlob'
              ]
            }
          }
        }
      ]
    }
  }
}

resource forwarderEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: resourceGroup().location
  properties: enableVnet ? {
    vnetConfiguration: {
      infrastructureSubnetId: resolvedAcaSubnetId
    }
  } : {}
}

resource forwarder 'Microsoft.App/jobs@2023-05-01' = {
  name: jobName
  location: resourceGroup().location
  properties: {
    environmentId: forwarderEnvironment.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '* * * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: [
        {
          name: 'storage-connection-string'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        { name: 'dd-api-key', value: datadogApiKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'datadog-forwarder'
          image: 'datadoghq.azurecr.io/forwarder:latest'
          resources: {
            cpu: 2
            memory: '4Gi'
          }
          env: [
            { name: 'AzureWebJobsStorage', secretRef: 'storage-connection-string' }
            { name: 'DD_API_KEY', secretRef: 'dd-api-key' }
            { name: 'DD_SITE', value: datadogSite }
            { name: 'CONTROL_PLANE_ID', value: 'none' }
            { name: 'CONFIG_ID', value: resourceId('Microsoft.App/jobs', jobName) }
          ]
        }
      ]
    }
  }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (enableVnet) {
  name: '${storageAccountName}-blob-pe'
  location: resourceGroup().location
  properties: {
    subnet: { id: resolvedPeSubnetId }
    privateLinkServiceConnections: [
      {
        name: '${storageAccountName}-blob-connection'
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: ['blob']
        }
      }
    ]
  }
}

resource storageBlobPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (enableVnet && empty(existingPrivateDnsZoneId)) {
  name: 'privatelink.blob.${environment().suffixes.storage}'
  location: 'global'
}

resource storageBlobPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (enableVnet && empty(existingPrivateDnsZoneId)) {
  name: 'blob-dns-zone-vnet-link'
  parent: storageBlobPrivateDnsZone
  location: 'global'
  properties: {
    virtualNetwork: { id: resolvedVnetId }
    registrationEnabled: false
  }
}

resource storageBlobDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (enableVnet) {
  name: 'blob-dns-zone-group'
  parent: storagePrivateEndpoint
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config'
        properties: {
          privateDnsZoneId: resolvedPrivateDnsZoneId
        }
      }
    ]
  }
  dependsOn: [storageBlobPrivateDnsZone]
}
