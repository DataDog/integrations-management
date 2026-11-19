// Assigns the diag-regional-storage initiative to the current subscription.
// Deploy AFTER definitions.bicep has registered the initiative.
//
// Usage:
//   az deployment sub create --location <region> --template-file assignment.bicep \
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

var initiativeId = '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.Authorization/policySetDefinitions/diag-regional-storage'

// Contributor role is required for the managed identity to deploy diagnostic settings via DeployIfNotExists.
var contributorRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')

resource assignment 'Microsoft.Authorization/policyAssignments@2022-06-01' = {
  name: assignmentName
  location: deployment().location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    policyDefinitionId: initiativeId
    displayName: assignmentDisplayName
    parameters: {
      storageAccountsByRegion: { value: storageAccountsByRegion }
      effect: { value: effect }
      diagnosticSettingName: { value: diagnosticSettingName }
      resourceTypeList: { value: empty(resourceTypeList) ? null : resourceTypeList }
      tagIncludeFilter: { value: tagIncludeFilter }
      tagExcludeFilter: { value: tagExcludeFilter }
    }
  }
}

// Grant the assignment's managed identity Contributor at subscription scope so it can
// deploy diagnostic settings resources via DeployIfNotExists remediation tasks.
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(assignmentName, subscription().subscriptionId, 'contributor')
  properties: {
    roleDefinitionId: contributorRoleDefinitionId
    principalId: assignment.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output assignmentId string = assignment.id
output assignmentPrincipalId string = assignment.identity.principalId
