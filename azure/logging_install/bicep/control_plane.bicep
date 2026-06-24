targetScope = 'resourceGroup'

param controlPlaneId string

param controlPlaneLocation string
param controlPlaneSubscriptionId string
param controlPlaneResourceGroupName string
param monitoredSubscriptions string

param imageRegistry string

@secure()
param datadogApiKey string
param datadogSite string
param piiScrubberRules string
param resourceTagFilters string
param datadogTelemetry bool
param logLevel string

var forwarderImage = '${imageRegistry}/forwarder:latest'
var resourcesTaskImage = '${imageRegistry}/resources-task:latest'
var diagnosticSettingsTaskImage = '${imageRegistry}/diagnostic-settings-task:latest'
var scalingTaskImage = '${imageRegistry}/scaling-task:latest'

// Settings
var STORAGE_CONNECTION_SETTING = 'AzureWebJobsStorage'
var DD_SITE_SETTING = 'DD_SITE'
var DD_API_KEY_SETTING = 'DD_API_KEY'
var DD_TELEMETRY_SETTING = 'DD_TELEMETRY'
var FORWARDER_IMAGE_SETTING = 'FORWARDER_IMAGE'
var SUBSCRIPTION_ID_SETTING = 'SUBSCRIPTION_ID'
var RESOURCE_GROUP_SETTING = 'RESOURCE_GROUP'
var CONTROL_PLANE_REGION_SETTING = 'CONTROL_PLANE_REGION'
var CONTROL_PLANE_ID_SETTING = 'CONTROL_PLANE_ID'
var MONITORED_SUBSCRIPTIONS_SETTING = 'MONITORED_SUBSCRIPTIONS'
var RESOURCE_TAG_FILTERS_SETTING = 'RESOURCE_TAG_FILTERS'
var PII_SCRUBBER_RULES_SETTING = 'PII_SCRUBBER_RULES'
var LOG_LEVEL_SETTING = 'LOG_LEVEL'
var AZURE_AUTHORITY_SETTING = 'AZURE_AUTHORITY'

// Secret Names
var DD_API_KEY_SECRET = 'dd-api-key'
var CONNECTION_STRING_SECRET = 'connection-string'

// CONTROL PLANE RESOURCES

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'lfostorage${controlPlaneId}'
  kind: 'StorageV2'
  location: controlPlaneLocation
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
  sku: { name: 'Standard_LRS' }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: storageAccount
  properties: {}
}

resource cacheContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: 'control-plane-cache'
  parent: blobServices
  properties: {}
}

var storageAccountKey = listKeys(storageAccount.id, '2019-06-01').keys[0].value
var connectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccountKey}'

var commonSecrets = [
  { name: CONNECTION_STRING_SECRET, value: connectionString }
  { name: DD_API_KEY_SECRET, value: datadogApiKey }
]

var commonEnv = [
  { name: STORAGE_CONNECTION_SETTING, secretRef: CONNECTION_STRING_SECRET }
  { name: DD_API_KEY_SETTING, secretRef: DD_API_KEY_SECRET }
  { name: DD_SITE_SETTING, value: datadogSite }
  { name: DD_TELEMETRY_SETTING, value: datadogTelemetry ? 'true' : 'false' }
  { name: CONTROL_PLANE_ID_SETTING, value: controlPlaneId }
  { name: CONTROL_PLANE_REGION_SETTING, value: controlPlaneLocation }
  { name: SUBSCRIPTION_ID_SETTING, value: controlPlaneSubscriptionId }
  { name: AZURE_AUTHORITY_SETTING, value: environment().authentication.loginEndpoint }
  { name: LOG_LEVEL_SETTING, value: logLevel }
]

resource controlPlaneEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'dd-log-forwarder-env-${controlPlaneId}-${controlPlaneLocation}'
  location: controlPlaneLocation
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

var resourceTaskName = 'resources-task-${controlPlaneId}'
resource resourceTask 'Microsoft.App/jobs@2024-03-01' = {
  name: resourceTaskName
  location: controlPlaneLocation
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: controlPlaneEnv.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '*/5 * * * *'
      }
      replicaRetryLimit: 1
      replicaTimeout: 1800
      secrets: commonSecrets
    }
    template: {
      containers: [
        {
          name: resourceTaskName
          image: resourcesTaskImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: union(commonEnv, [
            { name: MONITORED_SUBSCRIPTIONS_SETTING, value: monitoredSubscriptions }
            { name: RESOURCE_TAG_FILTERS_SETTING, value: resourceTagFilters }
          ])
        }
      ]
    }
  }
}

var diagnosticSettingsTaskName = 'diagnostic-settings-task-${controlPlaneId}'
resource diagnosticSettingsTask 'Microsoft.App/jobs@2024-03-01' = {
  name: diagnosticSettingsTaskName
  location: controlPlaneLocation
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: controlPlaneEnv.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '*/5 * * * *'
      }
      replicaRetryLimit: 1
      replicaTimeout: 1800
      secrets: commonSecrets
    }
    template: {
      containers: [
        {
          name: diagnosticSettingsTaskName
          image: diagnosticSettingsTaskImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: union(commonEnv, [
            { name: RESOURCE_GROUP_SETTING, value: controlPlaneResourceGroupName }
          ])
        }
      ]
    }
  }
}

var scalingTaskName = 'scaling-task-${controlPlaneId}'
resource scalingTask 'Microsoft.App/jobs@2024-03-01' = {
  name: scalingTaskName
  location: controlPlaneLocation
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: controlPlaneEnv.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '*/5 * * * *'
      }
      replicaRetryLimit: 1
      replicaTimeout: 1800
      secrets: commonSecrets
    }
    template: {
      containers: [
        {
          name: scalingTaskName
          image: scalingTaskImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: union(commonEnv, [
            { name: RESOURCE_GROUP_SETTING, value: controlPlaneResourceGroupName }
            { name: FORWARDER_IMAGE_SETTING, value: forwarderImage }
            { name: PII_SCRUBBER_RULES_SETTING, value: piiScrubberRules }
          ])
        }
      ]
    }
  }
}

// INITIAL RUN IDENTITY

resource initialRunIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'initialRunIdentity${controlPlaneId}'
  location: controlPlaneLocation
}

output resourceTaskPrincipalId string = resourceTask.identity.principalId
output diagnosticSettingsTaskPrincipalId string = diagnosticSettingsTask.identity.principalId
output scalingTaskPrincipalId string = scalingTask.identity.principalId
output initialRunIdentityPrincipalId string = initialRunIdentity.properties.principalId
output initialRunIdentityId string = initialRunIdentity.id
output storageAccountName string = storageAccount.name
