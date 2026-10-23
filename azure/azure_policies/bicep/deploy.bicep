// Single-step deployment: registers the initiative and assigns it to the current subscription.
//
// Usage:
//   az deployment sub create --location <region> --template-file deploy.bicep \
//     --parameters storageAccountsByRegion='{"eastus":"/subscriptions/.../storageAccounts/stdiag"}'
targetScope = 'subscription'

@description('Resource name for the policy assignment (no spaces).')
param assignmentName string = 'diag-regional-storage'

@description('Display name shown in the Azure portal.')
param assignmentDisplayName string = 'Enable allLogs diagnostic settings to regional storage accounts'

@description('Map of Azure region name to storage account resource ID. Storage accounts must be in the same region as the resources they collect logs from. Example: {"eastus": "/subscriptions/.../storageAccounts/stdiageastus"}')
param storageAccountsByRegion object

@description('Enable or disable the execution of the policy.')
@allowed(['DeployIfNotExists', 'AuditIfNotExists', 'Disabled'])
param effect string = 'DeployIfNotExists'

@description('Name of the diagnostic setting resource created on each compliant resource.')
param diagnosticSettingName string = 'setByPolicy-Storage'

@description('Resource types to enforce. Leave empty to use the initiative default (all supported types).')
param resourceTypeList array = []

@description('Only apply to resources matching ALL of these tags. Leave empty to apply to all resources.')
param tagIncludeFilter object = {}

@description('Skip resources matching ALL of these tags. Leave empty to exclude no resources.')
param tagExcludeFilter object = {}

module initiative 'definitions.bicep' = {
  name: 'diag-initiative'
}

module assignment 'assignment.bicep' = {
  name: 'diag-assignment'
  dependsOn: [initiative]
  params: {
    assignmentName: assignmentName
    assignmentDisplayName: assignmentDisplayName
    storageAccountsByRegion: storageAccountsByRegion
    effect: effect
    diagnosticSettingName: diagnosticSettingName
    resourceTypeList: resourceTypeList
    tagIncludeFilter: tagIncludeFilter
    tagExcludeFilter: tagExcludeFilter
  }
}

output assignmentId string = assignment.outputs.assignmentId
output assignmentPrincipalId string = assignment.outputs.assignmentPrincipalId
