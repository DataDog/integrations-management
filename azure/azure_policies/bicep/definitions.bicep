// Deploy at subscription scope. To target a management group instead:
//   1. Change targetScope to 'managementGroup'
//   2. Use: az deployment mg create --management-group-id <id> --template-file main.bicep ...
//
// This template deploys the policy definitions and initiative only.
// Parameters (storageAccountsByRegion, effect, tags, etc.) are supplied at assignment time, not here.
//
// Based on Azure built-in initiative:
//   Enable allLogs category group resource logging for supported resources to storage
// Extended with additional resource types from Datadog's azure-log-forwarding-orchestration,
// including microsoft.web/sites (web apps, function apps, logic apps) which is absent
// from the built-in initiative despite supporting diagnostic settings.
targetScope = 'subscription'

var sharedPolicyParams = loadJsonContent('policies/shared.params.json')

var policyRuleAadDomainservices = loadJsonContent('policies/aad-domainservices.rules.json')

resource policyDefAadDomainservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-aad-domainservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.aad/domainservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.aad/domainservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAadDomainservices
  }
}

var policyRuleAgfoodplatformFarmbeats = loadJsonContent('policies/agfoodplatform-farmbeats.rules.json')

resource policyDefAgfoodplatformFarmbeats 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-agfoodplatform-farmbeats'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.agfoodplatform/farmbeats to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.agfoodplatform/farmbeats to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAgfoodplatformFarmbeats
  }
}

var policyRuleAnalysisservicesServers = loadJsonContent('policies/analysisservices-servers.rules.json')

resource policyDefAnalysisservicesServers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-analysisservices-servers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.analysisservices/servers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.analysisservices/servers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAnalysisservicesServers
  }
}

var policyRuleApimanagementService = loadJsonContent('policies/apimanagement-service.rules.json')

resource policyDefApimanagementService 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-apimanagement-service'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.apimanagement/service to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.apimanagement/service to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleApimanagementService
  }
}

var policyRuleAppManagedenvironments = loadJsonContent('policies/app-managedenvironments.rules.json')

resource policyDefAppManagedenvironments 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-app-managedenvironments'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.app/managedenvironments to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.app/managedenvironments to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAppManagedenvironments
  }
}

var policyRuleAppconfigurationConfigurationstores = loadJsonContent('policies/appconfiguration-configurationstores.rules.json')

resource policyDefAppconfigurationConfigurationstores 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-appconfiguration-configurationstores'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.appconfiguration/configurationstores to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.appconfiguration/configurationstores to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAppconfigurationConfigurationstores
  }
}

var policyRuleAppplatformSpring = loadJsonContent('policies/appplatform-spring.rules.json')

resource policyDefAppplatformSpring 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-appplatform-spring'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.appplatform/spring to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.appplatform/spring to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAppplatformSpring
  }
}

var policyRuleAttestationAttestationproviders = loadJsonContent('policies/attestation-attestationproviders.rules.json')

resource policyDefAttestationAttestationproviders 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-attestation-attestationproviders'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.attestation/attestationproviders to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.attestation/attestationproviders to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAttestationAttestationproviders
  }
}

var policyRuleAutomationAutomationaccounts = loadJsonContent('policies/automation-automationaccounts.rules.json')

resource policyDefAutomationAutomationaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-automation-automationaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.automation/automationaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.automation/automationaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAutomationAutomationaccounts
  }
}

var policyRuleAutonomousdevelopmentplatformWorkspaces = loadJsonContent('policies/autonomousdevelopmentplatform-workspaces.rules.json')

resource policyDefAutonomousdevelopmentplatformWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-autonomousdevelopmentplatform-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.autonomousdevelopmentplatform/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.autonomousdevelopmentplatform/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAutonomousdevelopmentplatformWorkspaces
  }
}

var policyRuleAvsPrivateclouds = loadJsonContent('policies/avs-privateclouds.rules.json')

resource policyDefAvsPrivateclouds 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-avs-privateclouds'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.avs/privateclouds to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.avs/privateclouds to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAvsPrivateclouds
  }
}

var policyRuleAzureplaywrightserviceAccounts = loadJsonContent('policies/azureplaywrightservice-accounts.rules.json')

resource policyDefAzureplaywrightserviceAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-azureplaywrightservice-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.azureplaywrightservice/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.azureplaywrightservice/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAzureplaywrightserviceAccounts
  }
}

var policyRuleAzuresphereCatalogs = loadJsonContent('policies/azuresphere-catalogs.rules.json')

resource policyDefAzuresphereCatalogs 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-azuresphere-catalogs'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.azuresphere/catalogs to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.azuresphere/catalogs to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAzuresphereCatalogs
  }
}

var policyRuleBatchBatchaccounts = loadJsonContent('policies/batch-batchaccounts.rules.json')

resource policyDefBatchBatchaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-batch-batchaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.batch/batchaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.batch/batchaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleBatchBatchaccounts
  }
}

var policyRuleBotserviceBotservices = loadJsonContent('policies/botservice-botservices.rules.json')

resource policyDefBotserviceBotservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-botservice-botservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.botservice/botservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.botservice/botservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleBotserviceBotservices
  }
}

var policyRuleCacheRedis = loadJsonContent('policies/cache-redis.rules.json')

resource policyDefCacheRedis 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cache-redis'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cache/redis to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cache/redis to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCacheRedis
  }
}

var policyRuleCacheRedisenterpriseDatabases = loadJsonContent('policies/cache-redisenterprise-databases.rules.json')

resource policyDefCacheRedisenterpriseDatabases 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cache-redisenterprise-databases'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cache/redisenterprise/databases to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cache/redisenterprise/databases to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCacheRedisenterpriseDatabases
  }
}

var policyRuleCdnCdnwebapplicationfirewallpolicies = loadJsonContent('policies/cdn-cdnwebapplicationfirewallpolicies.rules.json')

resource policyDefCdnCdnwebapplicationfirewallpolicies 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cdn-cdnwebapplicationfirewallpolicies'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cdn/cdnwebapplicationfirewallpolicies to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cdn/cdnwebapplicationfirewallpolicies to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCdnCdnwebapplicationfirewallpolicies
  }
}

var policyRuleCdnProfiles = loadJsonContent('policies/cdn-profiles.rules.json')

resource policyDefCdnProfiles 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cdn-profiles'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cdn/profiles to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cdn/profiles to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCdnProfiles
  }
}

var policyRuleCdnProfilesEndpoints = loadJsonContent('policies/cdn-profiles-endpoints.rules.json')

resource policyDefCdnProfilesEndpoints 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cdn-profiles-endpoints'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cdn/profiles/endpoints to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cdn/profiles/endpoints to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCdnProfilesEndpoints
  }
}

var policyRuleChaosExperiments = loadJsonContent('policies/chaos-experiments.rules.json')

resource policyDefChaosExperiments 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-chaos-experiments'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.chaos/experiments to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.chaos/experiments to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleChaosExperiments
  }
}

var policyRuleClassicnetworkNetworksecuritygroups = loadJsonContent('policies/classicnetwork-networksecuritygroups.rules.json')

resource policyDefClassicnetworkNetworksecuritygroups 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-classicnetwork-networksecuritygroups'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.classicnetwork/networksecuritygroups to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.classicnetwork/networksecuritygroups to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleClassicnetworkNetworksecuritygroups
  }
}

var policyRuleCloudtestHostedpools = loadJsonContent('policies/cloudtest-hostedpools.rules.json')

resource policyDefCloudtestHostedpools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cloudtest-hostedpools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cloudtest/hostedpools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cloudtest/hostedpools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCloudtestHostedpools
  }
}

var policyRuleCodesigningCodesigningaccounts = loadJsonContent('policies/codesigning-codesigningaccounts.rules.json')

resource policyDefCodesigningCodesigningaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-codesigning-codesigningaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.codesigning/codesigningaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.codesigning/codesigningaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCodesigningCodesigningaccounts
  }
}

var policyRuleCognitiveservicesAccounts = loadJsonContent('policies/cognitiveservices-accounts.rules.json')

resource policyDefCognitiveservicesAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-cognitiveservices-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.cognitiveservices/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.cognitiveservices/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCognitiveservicesAccounts
  }
}

var policyRuleCommunicationCommunicationservices = loadJsonContent('policies/communication-communicationservices.rules.json')

resource policyDefCommunicationCommunicationservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-communication-communicationservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.communication/communicationservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.communication/communicationservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCommunicationCommunicationservices
  }
}

var policyRuleCommunityCommunitytrainings = loadJsonContent('policies/community-communitytrainings.rules.json')

resource policyDefCommunityCommunitytrainings 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-community-communitytrainings'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.community/communitytrainings to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.community/communitytrainings to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCommunityCommunitytrainings
  }
}

var policyRuleConfidentialledgerManagedccfs = loadJsonContent('policies/confidentialledger-managedccfs.rules.json')

resource policyDefConfidentialledgerManagedccfs 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-confidentialledger-managedccfs'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.confidentialledger/managedccfs to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.confidentialledger/managedccfs to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConfidentialledgerManagedccfs
  }
}

var policyRuleConnectedcacheEnterprisemcccustomers = loadJsonContent('policies/connectedcache-enterprisemcccustomers.rules.json')

resource policyDefConnectedcacheEnterprisemcccustomers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-connectedcache-enterprisemcccustomers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.connectedcache/enterprisemcccustomers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.connectedcache/enterprisemcccustomers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConnectedcacheEnterprisemcccustomers
  }
}

var policyRuleConnectedcacheIspcustomers = loadJsonContent('policies/connectedcache-ispcustomers.rules.json')

resource policyDefConnectedcacheIspcustomers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-connectedcache-ispcustomers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.connectedcache/ispcustomers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.connectedcache/ispcustomers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConnectedcacheIspcustomers
  }
}

var policyRuleContainerinstanceContainergroups = loadJsonContent('policies/containerinstance-containergroups.rules.json')

resource policyDefContainerinstanceContainergroups 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-containerinstance-containergroups'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.containerinstance/containergroups to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.containerinstance/containergroups to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleContainerinstanceContainergroups
  }
}

var policyRuleContainerregistryRegistries = loadJsonContent('policies/containerregistry-registries.rules.json')

resource policyDefContainerregistryRegistries 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-containerregistry-registries'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.containerregistry/registries to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.containerregistry/registries to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleContainerregistryRegistries
  }
}

var policyRuleCustomprovidersResourceproviders = loadJsonContent('policies/customproviders-resourceproviders.rules.json')

resource policyDefCustomprovidersResourceproviders 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-customproviders-resourceproviders'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.customproviders/resourceproviders to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.customproviders/resourceproviders to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleCustomprovidersResourceproviders
  }
}

var policyRuleD365customerinsightsInstances = loadJsonContent('policies/d365customerinsights-instances.rules.json')

resource policyDefD365customerinsightsInstances 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-d365customerinsights-instances'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.d365customerinsights/instances to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.d365customerinsights/instances to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleD365customerinsightsInstances
  }
}

var policyRuleDashboardGrafana = loadJsonContent('policies/dashboard-grafana.rules.json')

resource policyDefDashboardGrafana 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dashboard-grafana'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dashboard/grafana to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dashboard/grafana to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDashboardGrafana
  }
}

var policyRuleDatabricksWorkspaces = loadJsonContent('policies/databricks-workspaces.rules.json')

resource policyDefDatabricksWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-databricks-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.databricks/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.databricks/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDatabricksWorkspaces
  }
}

var policyRuleDatafactoryFactories = loadJsonContent('policies/datafactory-factories.rules.json')

resource policyDefDatafactoryFactories 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-datafactory-factories'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.datafactory/factories to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.datafactory/factories to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDatafactoryFactories
  }
}

var policyRuleDatalakeanalyticsAccounts = loadJsonContent('policies/datalakeanalytics-accounts.rules.json')

resource policyDefDatalakeanalyticsAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-datalakeanalytics-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.datalakeanalytics/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.datalakeanalytics/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDatalakeanalyticsAccounts
  }
}

var policyRuleDatalakestoreAccounts = loadJsonContent('policies/datalakestore-accounts.rules.json')

resource policyDefDatalakestoreAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-datalakestore-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.datalakestore/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.datalakestore/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDatalakestoreAccounts
  }
}

var policyRuleDataprotectionBackupvaults = loadJsonContent('policies/dataprotection-backupvaults.rules.json')

resource policyDefDataprotectionBackupvaults 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dataprotection-backupvaults'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dataprotection/backupvaults to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dataprotection/backupvaults to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDataprotectionBackupvaults
  }
}

var policyRuleDatashareAccounts = loadJsonContent('policies/datashare-accounts.rules.json')

resource policyDefDatashareAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-datashare-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.datashare/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.datashare/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDatashareAccounts
  }
}

var policyRuleDbformariadbServers = loadJsonContent('policies/dbformariadb-servers.rules.json')

resource policyDefDbformariadbServers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbformariadb-servers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbformariadb/servers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbformariadb/servers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbformariadbServers
  }
}

var policyRuleDbformysqlFlexibleservers = loadJsonContent('policies/dbformysql-flexibleservers.rules.json')

resource policyDefDbformysqlFlexibleservers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbformysql-flexibleservers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbformysql/flexibleservers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbformysql/flexibleservers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbformysqlFlexibleservers
  }
}

var policyRuleDbformysqlServers = loadJsonContent('policies/dbformysql-servers.rules.json')

resource policyDefDbformysqlServers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbformysql-servers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbformysql/servers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbformysql/servers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbformysqlServers
  }
}

var policyRuleDbforpostgresqlFlexibleservers = loadJsonContent('policies/dbforpostgresql-flexibleservers.rules.json')

resource policyDefDbforpostgresqlFlexibleservers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbforpostgresql-flexibleservers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbforpostgresql/flexibleservers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbforpostgresql/flexibleservers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbforpostgresqlFlexibleservers
  }
}

var policyRuleDbforpostgresqlServergroupsv2 = loadJsonContent('policies/dbforpostgresql-servergroupsv2.rules.json')

resource policyDefDbforpostgresqlServergroupsv2 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbforpostgresql-servergroupsv2'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbforpostgresql/servergroupsv2 to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbforpostgresql/servergroupsv2 to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbforpostgresqlServergroupsv2
  }
}

var policyRuleDbforpostgresqlServers = loadJsonContent('policies/dbforpostgresql-servers.rules.json')

resource policyDefDbforpostgresqlServers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbforpostgresql-servers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbforpostgresql/servers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbforpostgresql/servers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbforpostgresqlServers
  }
}

var policyRuleDesktopvirtualizationApplicationgroups = loadJsonContent('policies/desktopvirtualization-applicationgroups.rules.json')

resource policyDefDesktopvirtualizationApplicationgroups 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-desktopvirtualization-applicationgroups'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.desktopvirtualization/applicationgroups to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.desktopvirtualization/applicationgroups to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDesktopvirtualizationApplicationgroups
  }
}

var policyRuleDesktopvirtualizationHostpools = loadJsonContent('policies/desktopvirtualization-hostpools.rules.json')

resource policyDefDesktopvirtualizationHostpools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-desktopvirtualization-hostpools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.desktopvirtualization/hostpools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.desktopvirtualization/hostpools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDesktopvirtualizationHostpools
  }
}

var policyRuleDesktopvirtualizationScalingplans = loadJsonContent('policies/desktopvirtualization-scalingplans.rules.json')

resource policyDefDesktopvirtualizationScalingplans 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-desktopvirtualization-scalingplans'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.desktopvirtualization/scalingplans to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.desktopvirtualization/scalingplans to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDesktopvirtualizationScalingplans
  }
}

var policyRuleDesktopvirtualizationWorkspaces = loadJsonContent('policies/desktopvirtualization-workspaces.rules.json')

resource policyDefDesktopvirtualizationWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-desktopvirtualization-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.desktopvirtualization/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.desktopvirtualization/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDesktopvirtualizationWorkspaces
  }
}

var policyRuleDevcenterDevcenters = loadJsonContent('policies/devcenter-devcenters.rules.json')

resource policyDefDevcenterDevcenters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-devcenter-devcenters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.devcenter/devcenters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.devcenter/devcenters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDevcenterDevcenters
  }
}

var policyRuleDevicesIothubs = loadJsonContent('policies/devices-iothubs.rules.json')

resource policyDefDevicesIothubs 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-devices-iothubs'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.devices/iothubs to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.devices/iothubs to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDevicesIothubs
  }
}

var policyRuleDevicesProvisioningservices = loadJsonContent('policies/devices-provisioningservices.rules.json')

resource policyDefDevicesProvisioningservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-devices-provisioningservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.devices/provisioningservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.devices/provisioningservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDevicesProvisioningservices
  }
}

var policyRuleDigitaltwinsDigitaltwinsinstances = loadJsonContent('policies/digitaltwins-digitaltwinsinstances.rules.json')

resource policyDefDigitaltwinsDigitaltwinsinstances 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-digitaltwins-digitaltwinsinstances'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.digitaltwins/digitaltwinsinstances to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.digitaltwins/digitaltwinsinstances to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDigitaltwinsDigitaltwinsinstances
  }
}

var policyRuleDocumentdbCassandraclusters = loadJsonContent('policies/documentdb-cassandraclusters.rules.json')

resource policyDefDocumentdbCassandraclusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-documentdb-cassandraclusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.documentdb/cassandraclusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.documentdb/cassandraclusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDocumentdbCassandraclusters
  }
}

var policyRuleDocumentdbDatabaseaccounts = loadJsonContent('policies/documentdb-databaseaccounts.rules.json')

resource policyDefDocumentdbDatabaseaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-documentdb-databaseaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.documentdb/databaseaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.documentdb/databaseaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDocumentdbDatabaseaccounts
  }
}

var policyRuleDocumentdbMongoclusters = loadJsonContent('policies/documentdb-mongoclusters.rules.json')

resource policyDefDocumentdbMongoclusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-documentdb-mongoclusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.documentdb/mongoclusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.documentdb/mongoclusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDocumentdbMongoclusters
  }
}

var policyRuleEventgridDomains = loadJsonContent('policies/eventgrid-domains.rules.json')

resource policyDefEventgridDomains 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-domains'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/domains to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/domains to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridDomains
  }
}

var policyRuleEventgridPartnernamespaces = loadJsonContent('policies/eventgrid-partnernamespaces.rules.json')

resource policyDefEventgridPartnernamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-partnernamespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/partnernamespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/partnernamespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridPartnernamespaces
  }
}

var policyRuleEventgridPartnertopics = loadJsonContent('policies/eventgrid-partnertopics.rules.json')

resource policyDefEventgridPartnertopics 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-partnertopics'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/partnertopics to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/partnertopics to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridPartnertopics
  }
}

var policyRuleEventgridSystemtopics = loadJsonContent('policies/eventgrid-systemtopics.rules.json')

resource policyDefEventgridSystemtopics 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-systemtopics'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/systemtopics to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/systemtopics to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridSystemtopics
  }
}

var policyRuleEventgridTopics = loadJsonContent('policies/eventgrid-topics.rules.json')

resource policyDefEventgridTopics 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-topics'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/topics to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/topics to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridTopics
  }
}

var policyRuleEventhubNamespaces = loadJsonContent('policies/eventhub-namespaces.rules.json')

resource policyDefEventhubNamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventhub-namespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventhub/namespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventhub/namespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventhubNamespaces
  }
}

var policyRuleExperimentationExperimentworkspaces = loadJsonContent('policies/experimentation-experimentworkspaces.rules.json')

resource policyDefExperimentationExperimentworkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-experimentation-experimentworkspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.experimentation/experimentworkspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.experimentation/experimentworkspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleExperimentationExperimentworkspaces
  }
}

var policyRuleHealthcareapisServices = loadJsonContent('policies/healthcareapis-services.rules.json')

resource policyDefHealthcareapisServices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-healthcareapis-services'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.healthcareapis/services to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.healthcareapis/services to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHealthcareapisServices
  }
}

var policyRuleHealthcareapisWorkspacesDicomservices = loadJsonContent('policies/healthcareapis-workspaces-dicomservices.rules.json')

resource policyDefHealthcareapisWorkspacesDicomservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-healthcareapis-workspaces-dicomservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.healthcareapis/workspaces/dicomservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.healthcareapis/workspaces/dicomservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHealthcareapisWorkspacesDicomservices
  }
}

var policyRuleHealthcareapisWorkspacesFhirservices = loadJsonContent('policies/healthcareapis-workspaces-fhirservices.rules.json')

resource policyDefHealthcareapisWorkspacesFhirservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-healthcareapis-workspaces-fhirservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.healthcareapis/workspaces/fhirservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.healthcareapis/workspaces/fhirservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHealthcareapisWorkspacesFhirservices
  }
}

var policyRuleHealthcareapisWorkspacesIotconnectors = loadJsonContent('policies/healthcareapis-workspaces-iotconnectors.rules.json')

resource policyDefHealthcareapisWorkspacesIotconnectors 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-healthcareapis-workspaces-iotconnectors'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.healthcareapis/workspaces/iotconnectors to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.healthcareapis/workspaces/iotconnectors to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHealthcareapisWorkspacesIotconnectors
  }
}

var policyRuleInsightsAutoscalesettings = loadJsonContent('policies/insights-autoscalesettings.rules.json')

resource policyDefInsightsAutoscalesettings 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-insights-autoscalesettings'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.insights/autoscalesettings to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.insights/autoscalesettings to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleInsightsAutoscalesettings
  }
}

var policyRuleInsightsComponents = loadJsonContent('policies/insights-components.rules.json')

resource policyDefInsightsComponents 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-insights-components'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.insights/components to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.insights/components to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleInsightsComponents
  }
}

var policyRuleInsightsDatacollectionrules = loadJsonContent('policies/insights-datacollectionrules.rules.json')

resource policyDefInsightsDatacollectionrules 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-insights-datacollectionrules'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.insights/datacollectionrules to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.insights/datacollectionrules to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleInsightsDatacollectionrules
  }
}

var policyRuleKeyvaultManagedhsms = loadJsonContent('policies/keyvault-managedhsms.rules.json')

resource policyDefKeyvaultManagedhsms 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-keyvault-managedhsms'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.keyvault/managedhsms to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.keyvault/managedhsms to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleKeyvaultManagedhsms
  }
}

var policyRuleKeyvaultVaults = loadJsonContent('policies/keyvault-vaults.rules.json')

resource policyDefKeyvaultVaults 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-keyvault-vaults'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.keyvault/vaults to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.keyvault/vaults to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleKeyvaultVaults
  }
}

var policyRuleKustoClusters = loadJsonContent('policies/kusto-clusters.rules.json')

resource policyDefKustoClusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-kusto-clusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.kusto/clusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.kusto/clusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleKustoClusters
  }
}

var policyRuleLoadtestserviceLoadtests = loadJsonContent('policies/loadtestservice-loadtests.rules.json')

resource policyDefLoadtestserviceLoadtests 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-loadtestservice-loadtests'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.loadtestservice/loadtests to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.loadtestservice/loadtests to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleLoadtestserviceLoadtests
  }
}

var policyRuleLogicIntegrationaccounts = loadJsonContent('policies/logic-integrationaccounts.rules.json')

resource policyDefLogicIntegrationaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-logic-integrationaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.logic/integrationaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.logic/integrationaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleLogicIntegrationaccounts
  }
}

var policyRuleLogicWorkflows = loadJsonContent('policies/logic-workflows.rules.json')

resource policyDefLogicWorkflows 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-logic-workflows'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.logic/workflows to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.logic/workflows to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleLogicWorkflows
  }
}

var policyRuleMachinelearningservicesRegistries = loadJsonContent('policies/machinelearningservices-registries.rules.json')

resource policyDefMachinelearningservicesRegistries 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-machinelearningservices-registries'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.machinelearningservices/registries to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.machinelearningservices/registries to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMachinelearningservicesRegistries
  }
}

var policyRuleMachinelearningservicesWorkspaces = loadJsonContent('policies/machinelearningservices-workspaces.rules.json')

resource policyDefMachinelearningservicesWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-machinelearningservices-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.machinelearningservices/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.machinelearningservices/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMachinelearningservicesWorkspaces
  }
}

var policyRuleMachinelearningservicesWorkspacesOnlineendpoints = loadJsonContent('policies/machinelearningservices-workspaces-onlineendpoints.rules.json')

resource policyDefMachinelearningservicesWorkspacesOnlineendpoints 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-machinelearningservices-workspaces-onlineendpoints'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.machinelearningservices/workspaces/onlineendpoints to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.machinelearningservices/workspaces/onlineendpoints to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMachinelearningservicesWorkspacesOnlineendpoints
  }
}

var policyRuleManagednetworkfabricNetworkdevices = loadJsonContent('policies/managednetworkfabric-networkdevices.rules.json')

resource policyDefManagednetworkfabricNetworkdevices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-managednetworkfabric-networkdevices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.managednetworkfabric/networkdevices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.managednetworkfabric/networkdevices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleManagednetworkfabricNetworkdevices
  }
}

var policyRuleMediaMediaservices = loadJsonContent('policies/media-mediaservices.rules.json')

resource policyDefMediaMediaservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-media-mediaservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.media/mediaservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.media/mediaservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMediaMediaservices
  }
}

var policyRuleMediaVideoanalyzers = loadJsonContent('policies/media-videoanalyzers.rules.json')

resource policyDefMediaVideoanalyzers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-media-videoanalyzers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.media/videoanalyzers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.media/videoanalyzers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMediaVideoanalyzers
  }
}

var policyRuleMediaMediaservicesLiveevents = loadJsonContent('policies/media-mediaservices-liveevents.rules.json')

resource policyDefMediaMediaservicesLiveevents 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-media-mediaservices-liveevents'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.media/mediaservices/liveevents to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.media/mediaservices/liveevents to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMediaMediaservicesLiveevents
  }
}

var policyRuleMediaMediaservicesStreamingendpoints = loadJsonContent('policies/media-mediaservices-streamingendpoints.rules.json')

resource policyDefMediaMediaservicesStreamingendpoints 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-media-mediaservices-streamingendpoints'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.media/mediaservices/streamingendpoints to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.media/mediaservices/streamingendpoints to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMediaMediaservicesStreamingendpoints
  }
}

var policyRuleNetappNetappaccountsCapacitypoolsVolumes = loadJsonContent('policies/netapp-netappaccounts-capacitypools-volumes.rules.json')

resource policyDefNetappNetappaccountsCapacitypoolsVolumes 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-netapp-netappaccounts-capacitypools-volumes'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.netapp/netappaccounts/capacitypools/volumes to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.netapp/netappaccounts/capacitypools/volumes to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetappNetappaccountsCapacitypoolsVolumes
  }
}

var policyRuleNetworkApplicationgateways = loadJsonContent('policies/network-applicationgateways.rules.json')

resource policyDefNetworkApplicationgateways 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-applicationgateways'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/applicationgateways to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/applicationgateways to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkApplicationgateways
  }
}

var policyRuleNetworkAzurefirewalls = loadJsonContent('policies/network-azurefirewalls.rules.json')

resource policyDefNetworkAzurefirewalls 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-azurefirewalls'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/azurefirewalls to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/azurefirewalls to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkAzurefirewalls
  }
}

var policyRuleNetworkBastionhosts = loadJsonContent('policies/network-bastionhosts.rules.json')

resource policyDefNetworkBastionhosts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-bastionhosts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/bastionhosts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/bastionhosts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkBastionhosts
  }
}

var policyRuleNetworkDnsresolverpolicies = loadJsonContent('policies/network-dnsresolverpolicies.rules.json')

resource policyDefNetworkDnsresolverpolicies 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-dnsresolverpolicies'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/dnsresolverpolicies to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/dnsresolverpolicies to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkDnsresolverpolicies
  }
}

var policyRuleNetworkExpressroutecircuits = loadJsonContent('policies/network-expressroutecircuits.rules.json')

resource policyDefNetworkExpressroutecircuits 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-expressroutecircuits'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/expressroutecircuits to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/expressroutecircuits to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkExpressroutecircuits
  }
}

var policyRuleNetworkFrontdoors = loadJsonContent('policies/network-frontdoors.rules.json')

resource policyDefNetworkFrontdoors 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-frontdoors'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/frontdoors to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/frontdoors to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkFrontdoors
  }
}

var policyRuleNetworkLoadbalancers = loadJsonContent('policies/network-loadbalancers.rules.json')

resource policyDefNetworkLoadbalancers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-loadbalancers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/loadbalancers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/loadbalancers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkLoadbalancers
  }
}

var policyRuleNetworkNetworkmanagers = loadJsonContent('policies/network-networkmanagers.rules.json')

resource policyDefNetworkNetworkmanagers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-networkmanagers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/networkmanagers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/networkmanagers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkNetworkmanagers
  }
}

var policyRuleNetworkNetworkmanagersIpampools = loadJsonContent('policies/network-networkmanagers-ipampools.rules.json')

resource policyDefNetworkNetworkmanagersIpampools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-networkmanagers-ipampools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/networkmanagers/ipampools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/networkmanagers/ipampools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkNetworkmanagersIpampools
  }
}

var policyRuleNetworkNetworksecuritygroups = loadJsonContent('policies/network-networksecuritygroups.rules.json')

resource policyDefNetworkNetworksecuritygroups 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-networksecuritygroups'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/networksecuritygroups to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/networksecuritygroups to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkNetworksecuritygroups
  }
}

var policyRuleNetworkNetworksecurityperimeters = loadJsonContent('policies/network-networksecurityperimeters.rules.json')

resource policyDefNetworkNetworksecurityperimeters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-networksecurityperimeters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/networksecurityperimeters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/networksecurityperimeters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkNetworksecurityperimeters
  }
}

var policyRuleNetworkP2svpngateways = loadJsonContent('policies/network-p2svpngateways.rules.json')

resource policyDefNetworkP2svpngateways 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-p2svpngateways'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/p2svpngateways to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/p2svpngateways to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkP2svpngateways
  }
}

var policyRuleNetworkPublicipaddresses = loadJsonContent('policies/network-publicipaddresses.rules.json')

resource policyDefNetworkPublicipaddresses 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-publicipaddresses'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/publicipaddresses to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/publicipaddresses to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkPublicipaddresses
  }
}

var policyRuleNetworkPublicipprefixes = loadJsonContent('policies/network-publicipprefixes.rules.json')

resource policyDefNetworkPublicipprefixes 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-publicipprefixes'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/publicipprefixes to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/publicipprefixes to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkPublicipprefixes
  }
}

var policyRuleNetworkTrafficmanagerprofiles = loadJsonContent('policies/network-trafficmanagerprofiles.rules.json')

resource policyDefNetworkTrafficmanagerprofiles 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-trafficmanagerprofiles'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/trafficmanagerprofiles to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/trafficmanagerprofiles to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkTrafficmanagerprofiles
  }
}

var policyRuleNetworkVirtualnetworkgateways = loadJsonContent('policies/network-virtualnetworkgateways.rules.json')

resource policyDefNetworkVirtualnetworkgateways 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-virtualnetworkgateways'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/virtualnetworkgateways to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/virtualnetworkgateways to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkVirtualnetworkgateways
  }
}

var policyRuleNetworkVirtualnetworks = loadJsonContent('policies/network-virtualnetworks.rules.json')

resource policyDefNetworkVirtualnetworks 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-virtualnetworks'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/virtualnetworks to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/virtualnetworks to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkVirtualnetworks
  }
}

var policyRuleNetworkVpngateways = loadJsonContent('policies/network-vpngateways.rules.json')

resource policyDefNetworkVpngateways 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-network-vpngateways'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.network/vpngateways to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.network/vpngateways to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkVpngateways
  }
}

var policyRuleNetworkanalyticsDataproducts = loadJsonContent('policies/networkanalytics-dataproducts.rules.json')

resource policyDefNetworkanalyticsDataproducts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkanalytics-dataproducts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkanalytics/dataproducts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkanalytics/dataproducts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkanalyticsDataproducts
  }
}

var policyRuleNetworkcloudBaremetalmachines = loadJsonContent('policies/networkcloud-baremetalmachines.rules.json')

resource policyDefNetworkcloudBaremetalmachines 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkcloud-baremetalmachines'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkcloud/baremetalmachines to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkcloud/baremetalmachines to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkcloudBaremetalmachines
  }
}

var policyRuleNetworkcloudClusters = loadJsonContent('policies/networkcloud-clusters.rules.json')

resource policyDefNetworkcloudClusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkcloud-clusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkcloud/clusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkcloud/clusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkcloudClusters
  }
}

var policyRuleNetworkcloudStorageappliances = loadJsonContent('policies/networkcloud-storageappliances.rules.json')

resource policyDefNetworkcloudStorageappliances 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkcloud-storageappliances'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkcloud/storageappliances to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkcloud/storageappliances to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkcloudStorageappliances
  }
}

var policyRuleNetworkfunctionAzuretrafficcollectors = loadJsonContent('policies/networkfunction-azuretrafficcollectors.rules.json')

resource policyDefNetworkfunctionAzuretrafficcollectors 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkfunction-azuretrafficcollectors'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkfunction/azuretrafficcollectors to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkfunction/azuretrafficcollectors to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkfunctionAzuretrafficcollectors
  }
}

var policyRuleNotificationhubsNamespaces = loadJsonContent('policies/notificationhubs-namespaces.rules.json')

resource policyDefNotificationhubsNamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-notificationhubs-namespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.notificationhubs/namespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.notificationhubs/namespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNotificationhubsNamespaces
  }
}

var policyRuleNotificationhubsNamespacesNotificationhubs = loadJsonContent('policies/notificationhubs-namespaces-notificationhubs.rules.json')

resource policyDefNotificationhubsNamespacesNotificationhubs 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-notificationhubs-namespaces-notificationhubs'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.notificationhubs/namespaces/notificationhubs to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.notificationhubs/namespaces/notificationhubs to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNotificationhubsNamespacesNotificationhubs
  }
}

var policyRuleOpenenergyplatformEnergyservices = loadJsonContent('policies/openenergyplatform-energyservices.rules.json')

resource policyDefOpenenergyplatformEnergyservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-openenergyplatform-energyservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.openenergyplatform/energyservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.openenergyplatform/energyservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleOpenenergyplatformEnergyservices
  }
}

var policyRuleOperationalinsightsWorkspaces = loadJsonContent('policies/operationalinsights-workspaces.rules.json')

resource policyDefOperationalinsightsWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-operationalinsights-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.operationalinsights/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.operationalinsights/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleOperationalinsightsWorkspaces
  }
}

var policyRulePowerbiTenantsWorkspaces = loadJsonContent('policies/powerbi-tenants-workspaces.rules.json')

resource policyDefPowerbiTenantsWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-powerbi-tenants-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.powerbi/tenants/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.powerbi/tenants/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRulePowerbiTenantsWorkspaces
  }
}

var policyRulePowerbidedicatedCapacities = loadJsonContent('policies/powerbidedicated-capacities.rules.json')

resource policyDefPowerbidedicatedCapacities 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-powerbidedicated-capacities'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.powerbidedicated/capacities to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.powerbidedicated/capacities to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRulePowerbidedicatedCapacities
  }
}

var policyRulePurviewAccounts = loadJsonContent('policies/purview-accounts.rules.json')

resource policyDefPurviewAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-purview-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.purview/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.purview/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRulePurviewAccounts
  }
}

var policyRuleRecoveryservicesVaults = loadJsonContent('policies/recoveryservices-vaults.rules.json')

resource policyDefRecoveryservicesVaults 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-recoveryservices-vaults'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.recoveryservices/vaults to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.recoveryservices/vaults to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleRecoveryservicesVaults
  }
}

var policyRuleRelayNamespaces = loadJsonContent('policies/relay-namespaces.rules.json')

resource policyDefRelayNamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-relay-namespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.relay/namespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.relay/namespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleRelayNamespaces
  }
}

var policyRuleSearchSearchservices = loadJsonContent('policies/search-searchservices.rules.json')

resource policyDefSearchSearchservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-search-searchservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.search/searchservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.search/searchservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSearchSearchservices
  }
}

var policyRuleServicebusNamespaces = loadJsonContent('policies/servicebus-namespaces.rules.json')

resource policyDefServicebusNamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-servicebus-namespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.servicebus/namespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.servicebus/namespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleServicebusNamespaces
  }
}

var policyRuleServicenetworkingTrafficcontrollers = loadJsonContent('policies/servicenetworking-trafficcontrollers.rules.json')

resource policyDefServicenetworkingTrafficcontrollers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-servicenetworking-trafficcontrollers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.servicenetworking/trafficcontrollers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.servicenetworking/trafficcontrollers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleServicenetworkingTrafficcontrollers
  }
}

var policyRuleSignalrserviceSignalr = loadJsonContent('policies/signalrservice-signalr.rules.json')

resource policyDefSignalrserviceSignalr 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-signalrservice-signalr'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.signalrservice/signalr to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.signalrservice/signalr to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSignalrserviceSignalr
  }
}

var policyRuleSignalrserviceWebpubsub = loadJsonContent('policies/signalrservice-webpubsub.rules.json')

resource policyDefSignalrserviceWebpubsub 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-signalrservice-webpubsub'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.signalrservice/webpubsub to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.signalrservice/webpubsub to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSignalrserviceWebpubsub
  }
}

var policyRuleSqlManagedinstances = loadJsonContent('policies/sql-managedinstances.rules.json')

resource policyDefSqlManagedinstances 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-sql-managedinstances'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.sql/managedinstances to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.sql/managedinstances to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSqlManagedinstances
  }
}

var policyRuleSqlManagedinstancesDatabases = loadJsonContent('policies/sql-managedinstances-databases.rules.json')

resource policyDefSqlManagedinstancesDatabases 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-sql-managedinstances-databases'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.sql/managedinstances/databases to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.sql/managedinstances/databases to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSqlManagedinstancesDatabases
  }
}

var policyRuleSqlServersDatabases = loadJsonContent('policies/sql-servers-databases.rules.json')

resource policyDefSqlServersDatabases 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-sql-servers-databases'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.sql/servers/databases to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.sql/servers/databases to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSqlServersDatabases
  }
}

var policyRuleStoragecacheCaches = loadJsonContent('policies/storagecache-caches.rules.json')

resource policyDefStoragecacheCaches 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storagecache-caches'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storagecache/caches to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storagecache/caches to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStoragecacheCaches
  }
}

var policyRuleStoragemoverStoragemovers = loadJsonContent('policies/storagemover-storagemovers.rules.json')

resource policyDefStoragemoverStoragemovers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storagemover-storagemovers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storagemover/storagemovers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storagemover/storagemovers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStoragemoverStoragemovers
  }
}

var policyRuleStreamanalyticsStreamingjobs = loadJsonContent('policies/streamanalytics-streamingjobs.rules.json')

resource policyDefStreamanalyticsStreamingjobs 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-streamanalytics-streamingjobs'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.streamanalytics/streamingjobs to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.streamanalytics/streamingjobs to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStreamanalyticsStreamingjobs
  }
}

var policyRuleSynapseWorkspaces = loadJsonContent('policies/synapse-workspaces.rules.json')

resource policyDefSynapseWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-synapse-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.synapse/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.synapse/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSynapseWorkspaces
  }
}

var policyRuleSynapseWorkspacesBigdatapools = loadJsonContent('policies/synapse-workspaces-bigdatapools.rules.json')

resource policyDefSynapseWorkspacesBigdatapools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-synapse-workspaces-bigdatapools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.synapse/workspaces/bigdatapools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.synapse/workspaces/bigdatapools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSynapseWorkspacesBigdatapools
  }
}

var policyRuleSynapseWorkspacesKustopools = loadJsonContent('policies/synapse-workspaces-kustopools.rules.json')

resource policyDefSynapseWorkspacesKustopools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-synapse-workspaces-kustopools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.synapse/workspaces/kustopools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.synapse/workspaces/kustopools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSynapseWorkspacesKustopools
  }
}

var policyRuleSynapseWorkspacesScopepools = loadJsonContent('policies/synapse-workspaces-scopepools.rules.json')

resource policyDefSynapseWorkspacesScopepools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-synapse-workspaces-scopepools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.synapse/workspaces/scopepools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.synapse/workspaces/scopepools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSynapseWorkspacesScopepools
  }
}

var policyRuleSynapseWorkspacesSqlpools = loadJsonContent('policies/synapse-workspaces-sqlpools.rules.json')

resource policyDefSynapseWorkspacesSqlpools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-synapse-workspaces-sqlpools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.synapse/workspaces/sqlpools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.synapse/workspaces/sqlpools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSynapseWorkspacesSqlpools
  }
}

var policyRuleTimeseriesinsightsEnvironments = loadJsonContent('policies/timeseriesinsights-environments.rules.json')

resource policyDefTimeseriesinsightsEnvironments 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-timeseriesinsights-environments'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.timeseriesinsights/environments to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.timeseriesinsights/environments to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleTimeseriesinsightsEnvironments
  }
}

var policyRuleTimeseriesinsightsEnvironmentsEventsources = loadJsonContent('policies/timeseriesinsights-environments-eventsources.rules.json')

resource policyDefTimeseriesinsightsEnvironmentsEventsources 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-timeseriesinsights-environments-eventsources'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.timeseriesinsights/environments/eventsources to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.timeseriesinsights/environments/eventsources to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleTimeseriesinsightsEnvironmentsEventsources
  }
}

var policyRuleVideoindexerAccounts = loadJsonContent('policies/videoindexer-accounts.rules.json')

resource policyDefVideoindexerAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-videoindexer-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.videoindexer/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.videoindexer/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleVideoindexerAccounts
  }
}

var policyRuleWebHostingenvironments = loadJsonContent('policies/web-hostingenvironments.rules.json')

resource policyDefWebHostingenvironments 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-web-hostingenvironments'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.web/hostingenvironments to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.web/hostingenvironments to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleWebHostingenvironments
  }
}

var policyRuleWorkloadsSapvirtualinstances = loadJsonContent('policies/workloads-sapvirtualinstances.rules.json')

resource policyDefWorkloadsSapvirtualinstances 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-workloads-sapvirtualinstances'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.workloads/sapvirtualinstances to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.workloads/sapvirtualinstances to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleWorkloadsSapvirtualinstances
  }
}

var policyRuleWebSites = loadJsonContent('policies/web-sites.rules.json')

resource policyDefWebSites 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-web-sites'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.web/sites to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.web/sites to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleWebSites
  }
}

var policyRuleAutonomousdevelopmentplatformAccounts = loadJsonContent('policies/autonomousdevelopmentplatform-accounts.rules.json')

resource policyDefAutonomousdevelopmentplatformAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-autonomousdevelopmentplatform-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.autonomousdevelopmentplatform/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.autonomousdevelopmentplatform/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleAutonomousdevelopmentplatformAccounts
  }
}

var policyRuleComputeVirtualmachines = loadJsonContent('policies/compute-virtualmachines.rules.json')

resource policyDefComputeVirtualmachines 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-compute-virtualmachines'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.compute/virtualmachines to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.compute/virtualmachines to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleComputeVirtualmachines
  }
}

var policyRuleConfidentialledgerManagedccf = loadJsonContent('policies/confidentialledger-managedccf.rules.json')

resource policyDefConfidentialledgerManagedccf 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-confidentialledger-managedccf'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.confidentialledger/managedccf to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.confidentialledger/managedccf to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConfidentialledgerManagedccf
  }
}

var policyRuleConnectedcacheCachenodes = loadJsonContent('policies/connectedcache-cachenodes.rules.json')

resource policyDefConnectedcacheCachenodes 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-connectedcache-cachenodes'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.connectedcache/cachenodes to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.connectedcache/cachenodes to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConnectedcacheCachenodes
  }
}

var policyRuleConnectedvehiclePlatformaccounts = loadJsonContent('policies/connectedvehicle-platformaccounts.rules.json')

resource policyDefConnectedvehiclePlatformaccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-connectedvehicle-platformaccounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.connectedvehicle/platformaccounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.connectedvehicle/platformaccounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleConnectedvehiclePlatformaccounts
  }
}

var policyRuleContainerserviceFleets = loadJsonContent('policies/containerservice-fleets.rules.json')

resource policyDefContainerserviceFleets 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-containerservice-fleets'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.containerservice/fleets to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.containerservice/fleets to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleContainerserviceFleets
  }
}

var policyRuleContainerserviceManagedclusters = loadJsonContent('policies/containerservice-managedclusters.rules.json')

resource policyDefContainerserviceManagedclusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-containerservice-managedclusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.containerservice/managedclusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.containerservice/managedclusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleContainerserviceManagedclusters
  }
}

var policyRuleDbforpostgresqlServersv2 = loadJsonContent('policies/dbforpostgresql-serversv2.rules.json')

resource policyDefDbforpostgresqlServersv2 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-dbforpostgresql-serversv2'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.dbforpostgresql/serversv2 to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.dbforpostgresql/serversv2 to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDbforpostgresqlServersv2
  }
}

var policyRuleDesktopvirtualizationAppattachpackages = loadJsonContent('policies/desktopvirtualization-appattachpackages.rules.json')

resource policyDefDesktopvirtualizationAppattachpackages 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-desktopvirtualization-appattachpackages'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.desktopvirtualization/appattachpackages to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.desktopvirtualization/appattachpackages to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDesktopvirtualizationAppattachpackages
  }
}

var policyRuleDevopsinfrastructurePools = loadJsonContent('policies/devopsinfrastructure-pools.rules.json')

resource policyDefDevopsinfrastructurePools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-devopsinfrastructure-pools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.devopsinfrastructure/pools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.devopsinfrastructure/pools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleDevopsinfrastructurePools
  }
}

var policyRuleEventgridNamespaces = loadJsonContent('policies/eventgrid-namespaces.rules.json')

resource policyDefEventgridNamespaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-eventgrid-namespaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.eventgrid/namespaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.eventgrid/namespaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleEventgridNamespaces
  }
}

var policyRuleHardwaresecuritymodulesCloudhsmclusters = loadJsonContent('policies/hardwaresecuritymodules-cloudhsmclusters.rules.json')

resource policyDefHardwaresecuritymodulesCloudhsmclusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-hardwaresecuritymodules-cloudhsmclusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.hardwaresecuritymodules/cloudhsmclusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.hardwaresecuritymodules/cloudhsmclusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHardwaresecuritymodulesCloudhsmclusters
  }
}

var policyRuleHealthdataaiservicesDeidservices = loadJsonContent('policies/healthdataaiservices-deidservices.rules.json')

resource policyDefHealthdataaiservicesDeidservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-healthdataaiservices-deidservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.healthdataaiservices/deidservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.healthdataaiservices/deidservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleHealthdataaiservicesDeidservices
  }
}

var policyRuleKubernetesConnectedclusters = loadJsonContent('policies/kubernetes-connectedclusters.rules.json')

resource policyDefKubernetesConnectedclusters 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-kubernetes-connectedclusters'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.kubernetes/connectedclusters to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.kubernetes/connectedclusters to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleKubernetesConnectedclusters
  }
}

var policyRuleMonitorAccounts = loadJsonContent('policies/monitor-accounts.rules.json')

resource policyDefMonitorAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-monitor-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.monitor/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.monitor/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleMonitorAccounts
  }
}

var policyRuleNetappNetappaccountsCapacitypools = loadJsonContent('policies/netapp-netappaccounts-capacitypools.rules.json')

resource policyDefNetappNetappaccountsCapacitypools 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-netapp-netappaccounts-capacitypools'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.netapp/netappaccounts/capacitypools to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.netapp/netappaccounts/capacitypools to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetappNetappaccountsCapacitypools
  }
}

var policyRuleNetworkcloudClustermanagers = loadJsonContent('policies/networkcloud-clustermanagers.rules.json')

resource policyDefNetworkcloudClustermanagers 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-networkcloud-clustermanagers'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.networkcloud/clustermanagers to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.networkcloud/clustermanagers to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNetworkcloudClustermanagers
  }
}

var policyRuleOpenlogisticsplatformWorkspaces = loadJsonContent('policies/openlogisticsplatform-workspaces.rules.json')

resource policyDefOpenlogisticsplatformWorkspaces 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-openlogisticsplatform-workspaces'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.openlogisticsplatform/workspaces to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.openlogisticsplatform/workspaces to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleOpenlogisticsplatformWorkspaces
  }
}

var policyRulePlayfabTitles = loadJsonContent('policies/playfab-titles.rules.json')

resource policyDefPlayfabTitles 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-playfab-titles'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.playfab/titles to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.playfab/titles to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRulePlayfabTitles
  }
}

var policyRulePowerbiTenants = loadJsonContent('policies/powerbi-tenants.rules.json')

resource policyDefPowerbiTenants 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-powerbi-tenants'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.powerbi/tenants to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.powerbi/tenants to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRulePowerbiTenants
  }
}

var policyRuleProviderhubProvidermonitorsettings = loadJsonContent('policies/providerhub-providermonitorsettings.rules.json')

resource policyDefProviderhubProvidermonitorsettings 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-providerhub-providermonitorsettings'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.providerhub/providermonitorsettings to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.providerhub/providermonitorsettings to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleProviderhubProvidermonitorsettings
  }
}

var policyRuleProviderhubProviderregistrations = loadJsonContent('policies/providerhub-providerregistrations.rules.json')

resource policyDefProviderhubProviderregistrations 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-providerhub-providerregistrations'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.providerhub/providerregistrations to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.providerhub/providerregistrations to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleProviderhubProviderregistrations
  }
}

var policyRuleSecurityAntimalwaresettings = loadJsonContent('policies/security-antimalwaresettings.rules.json')

resource policyDefSecurityAntimalwaresettings 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-security-antimalwaresettings'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.security/antimalwaresettings to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.security/antimalwaresettings to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSecurityAntimalwaresettings
  }
}

var policyRuleSecurityDefenderforstoragesettings = loadJsonContent('policies/security-defenderforstoragesettings.rules.json')

resource policyDefSecurityDefenderforstoragesettings 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-security-defenderforstoragesettings'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.security/defenderforstoragesettings to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.security/defenderforstoragesettings to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSecurityDefenderforstoragesettings
  }
}

var policyRuleSingularityAccounts = loadJsonContent('policies/singularity-accounts.rules.json')

resource policyDefSingularityAccounts 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-singularity-accounts'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.singularity/accounts to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.singularity/accounts to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleSingularityAccounts
  }
}

var policyRuleStorageStorageaccountsBlobservices = loadJsonContent('policies/storage-storageaccounts-blobservices.rules.json')

resource policyDefStorageStorageaccountsBlobservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storage-storageaccounts-blobservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storage/storageaccounts/blobservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storage/storageaccounts/blobservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStorageStorageaccountsBlobservices
  }
}

var policyRuleStorageStorageaccountsFileservices = loadJsonContent('policies/storage-storageaccounts-fileservices.rules.json')

resource policyDefStorageStorageaccountsFileservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storage-storageaccounts-fileservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storage/storageaccounts/fileservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storage/storageaccounts/fileservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStorageStorageaccountsFileservices
  }
}

var policyRuleStorageStorageaccountsQueueservices = loadJsonContent('policies/storage-storageaccounts-queueservices.rules.json')

resource policyDefStorageStorageaccountsQueueservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storage-storageaccounts-queueservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storage/storageaccounts/queueservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storage/storageaccounts/queueservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStorageStorageaccountsQueueservices
  }
}

var policyRuleStorageStorageaccountsTableservices = loadJsonContent('policies/storage-storageaccounts-tableservices.rules.json')

resource policyDefStorageStorageaccountsTableservices 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storage-storageaccounts-tableservices'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storage/storageaccounts/tableservices to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storage/storageaccounts/tableservices to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStorageStorageaccountsTableservices
  }
}

var policyRuleStoragecacheAmlfilesystems = loadJsonContent('policies/storagecache-amlfilesystems.rules.json')

resource policyDefStoragecacheAmlfilesystems 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-storagecache-amlfilesystems'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.storagecache/amlfilesystems to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.storagecache/amlfilesystems to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleStoragecacheAmlfilesystems
  }
}

var policyRuleWebSitesSlots = loadJsonContent('policies/web-sites-slots.rules.json')

resource policyDefWebSitesSlots 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-web-sites-slots'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.web/sites/slots to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.web/sites/slots to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleWebSitesSlots
  }
}

var policyRuleWebStaticsites = loadJsonContent('policies/web-staticsites.rules.json')

resource policyDefWebStaticsites 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-web-staticsites'
  properties: {
    displayName: 'Apply Diagnostic Settings for microsoft.web/staticsites to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for microsoft.web/staticsites to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleWebStaticsites
  }
}

var policyRuleNginxNginxplusNginxdeployment = loadJsonContent('policies/nginx-nginxplus-nginxdeployment.rules.json')

resource policyDefNginxNginxplusNginxdeployment 'Microsoft.Authorization/policyDefinitions@2021-06-01' = {
  name: 'apply-diag-nginx-nginxplus-nginxdeployment'
  properties: {
    displayName: 'Apply Diagnostic Settings for nginx.nginxplus/nginxdeployment to a Regional Storage Account'
    mode: 'Indexed'
    description: 'Deploys diagnostic settings for nginx.nginxplus/nginxdeployment to the storage account mapped to each resource\'s Azure region. Resources in regions not present in storageAccountsByRegion are skipped.'
    metadata: { category: 'Monitoring' }
    parameters: sharedPolicyParams
    policyRule: policyRuleNginxNginxplusNginxdeployment
  }
}


resource initiative 'Microsoft.Authorization/policySetDefinitions@2021-06-01' = {
  name: 'diag-regional-storage'
  properties: {
    displayName: 'Enable allLogs category group resource logging for supported resources to regional storage accounts'
    description: 'Resource logs should be enabled to track activities and events that take place on your resources and give you visibility and insights into any changes that occur. This initiative deploys diagnostic settings using the allLogs category group to route logs to the storage account mapped to each resource\'s Azure region.'
    policyType: 'Custom'
    metadata: {
      category: 'Monitoring'
      version: '1.0.0'
    }
    parameters: {
      effect: {
        type: 'String'
        metadata: { displayName: 'Effect', description: 'Enable or disable the execution of the policy' }
        allowedValues: [ 'DeployIfNotExists', 'AuditIfNotExists', 'Disabled' ]
        defaultValue: 'DeployIfNotExists'
      }
      diagnosticSettingName: {
        type: 'String'
        metadata: { displayName: 'Diagnostic Setting Name', description: 'Name of the diagnostic setting created and managed by this initiative.' }
        defaultValue: 'setByPolicy-Storage'
      }
      storageAccountsByRegion: {
        type: 'Object'
        metadata: { displayName: 'Storage accounts by region', description: 'Map of Azure region name to storage account resource ID. Storage accounts must be in the same region as the resources they collect logs from.' }
      }
      resourceTypeList: {
        type: 'Array'
        metadata: { displayName: 'Resource Types', description: 'List of resource types to enforce. Remove a type to disable enforcement for that resource type.' }
        allowedValues: [
      'microsoft.aad/domainservices'
      'microsoft.agfoodplatform/farmbeats'
      'microsoft.analysisservices/servers'
      'microsoft.apimanagement/service'
      'microsoft.app/managedenvironments'
      'microsoft.appconfiguration/configurationstores'
      'microsoft.appplatform/spring'
      'microsoft.attestation/attestationproviders'
      'microsoft.automation/automationaccounts'
      'microsoft.autonomousdevelopmentplatform/workspaces'
      'microsoft.avs/privateclouds'
      'microsoft.azureplaywrightservice/accounts'
      'microsoft.azuresphere/catalogs'
      'microsoft.batch/batchaccounts'
      'microsoft.botservice/botservices'
      'microsoft.cache/redis'
      'microsoft.cache/redisenterprise/databases'
      'microsoft.cdn/cdnwebapplicationfirewallpolicies'
      'microsoft.cdn/profiles'
      'microsoft.cdn/profiles/endpoints'
      'microsoft.chaos/experiments'
      'microsoft.classicnetwork/networksecuritygroups'
      'microsoft.cloudtest/hostedpools'
      'microsoft.codesigning/codesigningaccounts'
      'microsoft.cognitiveservices/accounts'
      'microsoft.communication/communicationservices'
      'microsoft.community/communitytrainings'
      'microsoft.confidentialledger/managedccfs'
      'microsoft.connectedcache/enterprisemcccustomers'
      'microsoft.connectedcache/ispcustomers'
      'microsoft.containerinstance/containergroups'
      'microsoft.containerregistry/registries'
      'microsoft.customproviders/resourceproviders'
      'microsoft.d365customerinsights/instances'
      'microsoft.dashboard/grafana'
      'microsoft.databricks/workspaces'
      'microsoft.datafactory/factories'
      'microsoft.datalakeanalytics/accounts'
      'microsoft.datalakestore/accounts'
      'microsoft.dataprotection/backupvaults'
      'microsoft.datashare/accounts'
      'microsoft.dbformariadb/servers'
      'microsoft.dbformysql/flexibleservers'
      'microsoft.dbformysql/servers'
      'microsoft.dbforpostgresql/flexibleservers'
      'microsoft.dbforpostgresql/servergroupsv2'
      'microsoft.dbforpostgresql/servers'
      'microsoft.desktopvirtualization/applicationgroups'
      'microsoft.desktopvirtualization/hostpools'
      'microsoft.desktopvirtualization/scalingplans'
      'microsoft.desktopvirtualization/workspaces'
      'microsoft.devcenter/devcenters'
      'microsoft.devices/iothubs'
      'microsoft.devices/provisioningservices'
      'microsoft.digitaltwins/digitaltwinsinstances'
      'microsoft.documentdb/cassandraclusters'
      'microsoft.documentdb/databaseaccounts'
      'microsoft.documentdb/mongoclusters'
      'microsoft.eventgrid/domains'
      'microsoft.eventgrid/partnernamespaces'
      'microsoft.eventgrid/partnertopics'
      'microsoft.eventgrid/systemtopics'
      'microsoft.eventgrid/topics'
      'microsoft.eventhub/namespaces'
      'microsoft.experimentation/experimentworkspaces'
      'microsoft.healthcareapis/services'
      'microsoft.healthcareapis/workspaces/dicomservices'
      'microsoft.healthcareapis/workspaces/fhirservices'
      'microsoft.healthcareapis/workspaces/iotconnectors'
      'microsoft.insights/autoscalesettings'
      'microsoft.insights/components'
      'microsoft.insights/datacollectionrules'
      'microsoft.keyvault/managedhsms'
      'microsoft.keyvault/vaults'
      'microsoft.kusto/clusters'
      'microsoft.loadtestservice/loadtests'
      'microsoft.logic/integrationaccounts'
      'microsoft.logic/workflows'
      'microsoft.machinelearningservices/registries'
      'microsoft.machinelearningservices/workspaces'
      'microsoft.machinelearningservices/workspaces/onlineendpoints'
      'microsoft.managednetworkfabric/networkdevices'
      'microsoft.media/mediaservices'
      'microsoft.media/videoanalyzers'
      'microsoft.media/mediaservices/liveevents'
      'microsoft.media/mediaservices/streamingendpoints'
      'microsoft.netapp/netappaccounts/capacitypools/volumes'
      'microsoft.network/applicationgateways'
      'microsoft.network/azurefirewalls'
      'microsoft.network/bastionhosts'
      'microsoft.network/dnsresolverpolicies'
      'microsoft.network/expressroutecircuits'
      'microsoft.network/frontdoors'
      'microsoft.network/loadbalancers'
      'microsoft.network/networkmanagers'
      'microsoft.network/networkmanagers/ipampools'
      'microsoft.network/networksecuritygroups'
      'microsoft.network/networksecurityperimeters'
      'microsoft.network/p2svpngateways'
      'microsoft.network/publicipaddresses'
      'microsoft.network/publicipprefixes'
      'microsoft.network/trafficmanagerprofiles'
      'microsoft.network/virtualnetworkgateways'
      'microsoft.network/virtualnetworks'
      'microsoft.network/vpngateways'
      'microsoft.networkanalytics/dataproducts'
      'microsoft.networkcloud/baremetalmachines'
      'microsoft.networkcloud/clusters'
      'microsoft.networkcloud/storageappliances'
      'microsoft.networkfunction/azuretrafficcollectors'
      'microsoft.notificationhubs/namespaces'
      'microsoft.notificationhubs/namespaces/notificationhubs'
      'microsoft.openenergyplatform/energyservices'
      'microsoft.operationalinsights/workspaces'
      'microsoft.powerbi/tenants/workspaces'
      'microsoft.powerbidedicated/capacities'
      'microsoft.purview/accounts'
      'microsoft.recoveryservices/vaults'
      'microsoft.relay/namespaces'
      'microsoft.search/searchservices'
      'microsoft.servicebus/namespaces'
      'microsoft.servicenetworking/trafficcontrollers'
      'microsoft.signalrservice/signalr'
      'microsoft.signalrservice/webpubsub'
      'microsoft.sql/managedinstances'
      'microsoft.sql/managedinstances/databases'
      'microsoft.sql/servers/databases'
      'microsoft.storagecache/caches'
      'microsoft.storagemover/storagemovers'
      'microsoft.streamanalytics/streamingjobs'
      'microsoft.synapse/workspaces'
      'microsoft.synapse/workspaces/bigdatapools'
      'microsoft.synapse/workspaces/kustopools'
      'microsoft.synapse/workspaces/scopepools'
      'microsoft.synapse/workspaces/sqlpools'
      'microsoft.timeseriesinsights/environments'
      'microsoft.timeseriesinsights/environments/eventsources'
      'microsoft.videoindexer/accounts'
      'microsoft.web/hostingenvironments'
      'microsoft.workloads/sapvirtualinstances'
      'microsoft.web/sites'
      'microsoft.autonomousdevelopmentplatform/accounts'
      'microsoft.compute/virtualmachines'
      'microsoft.confidentialledger/managedccf'
      'microsoft.connectedcache/cachenodes'
      'microsoft.connectedvehicle/platformaccounts'
      'microsoft.containerservice/fleets'
      'microsoft.containerservice/managedclusters'
      'microsoft.dbforpostgresql/serversv2'
      'microsoft.desktopvirtualization/appattachpackages'
      'microsoft.devopsinfrastructure/pools'
      'microsoft.eventgrid/namespaces'
      'microsoft.hardwaresecuritymodules/cloudhsmclusters'
      'microsoft.healthdataaiservices/deidservices'
      'microsoft.kubernetes/connectedclusters'
      'microsoft.monitor/accounts'
      'microsoft.netapp/netappaccounts/capacitypools'
      'microsoft.networkcloud/clustermanagers'
      'microsoft.openlogisticsplatform/workspaces'
      'microsoft.playfab/titles'
      'microsoft.powerbi/tenants'
      'microsoft.providerhub/providermonitorsettings'
      'microsoft.providerhub/providerregistrations'
      'microsoft.security/antimalwaresettings'
      'microsoft.security/defenderforstoragesettings'
      'microsoft.singularity/accounts'
      'microsoft.storage/storageaccounts/blobservices'
      'microsoft.storage/storageaccounts/fileservices'
      'microsoft.storage/storageaccounts/queueservices'
      'microsoft.storage/storageaccounts/tableservices'
      'microsoft.storagecache/amlfilesystems'
      'microsoft.web/sites/slots'
      'microsoft.web/staticsites'
      'nginx.nginxplus/nginxdeployment'
        ]
        defaultValue: [
      'microsoft.aad/domainservices'
      'microsoft.agfoodplatform/farmbeats'
      'microsoft.analysisservices/servers'
      'microsoft.apimanagement/service'
      'microsoft.app/managedenvironments'
      'microsoft.appconfiguration/configurationstores'
      'microsoft.appplatform/spring'
      'microsoft.attestation/attestationproviders'
      'microsoft.automation/automationaccounts'
      'microsoft.autonomousdevelopmentplatform/workspaces'
      'microsoft.avs/privateclouds'
      'microsoft.azureplaywrightservice/accounts'
      'microsoft.azuresphere/catalogs'
      'microsoft.batch/batchaccounts'
      'microsoft.botservice/botservices'
      'microsoft.cache/redis'
      'microsoft.cache/redisenterprise/databases'
      'microsoft.cdn/cdnwebapplicationfirewallpolicies'
      'microsoft.cdn/profiles'
      'microsoft.cdn/profiles/endpoints'
      'microsoft.chaos/experiments'
      'microsoft.classicnetwork/networksecuritygroups'
      'microsoft.cloudtest/hostedpools'
      'microsoft.codesigning/codesigningaccounts'
      'microsoft.cognitiveservices/accounts'
      'microsoft.communication/communicationservices'
      'microsoft.community/communitytrainings'
      'microsoft.confidentialledger/managedccfs'
      'microsoft.connectedcache/enterprisemcccustomers'
      'microsoft.connectedcache/ispcustomers'
      'microsoft.containerinstance/containergroups'
      'microsoft.containerregistry/registries'
      'microsoft.customproviders/resourceproviders'
      'microsoft.d365customerinsights/instances'
      'microsoft.dashboard/grafana'
      'microsoft.databricks/workspaces'
      'microsoft.datafactory/factories'
      'microsoft.datalakeanalytics/accounts'
      'microsoft.datalakestore/accounts'
      'microsoft.dataprotection/backupvaults'
      'microsoft.datashare/accounts'
      'microsoft.dbformariadb/servers'
      'microsoft.dbformysql/flexibleservers'
      'microsoft.dbformysql/servers'
      'microsoft.dbforpostgresql/flexibleservers'
      'microsoft.dbforpostgresql/servergroupsv2'
      'microsoft.dbforpostgresql/servers'
      'microsoft.desktopvirtualization/applicationgroups'
      'microsoft.desktopvirtualization/hostpools'
      'microsoft.desktopvirtualization/scalingplans'
      'microsoft.desktopvirtualization/workspaces'
      'microsoft.devcenter/devcenters'
      'microsoft.devices/iothubs'
      'microsoft.devices/provisioningservices'
      'microsoft.digitaltwins/digitaltwinsinstances'
      'microsoft.documentdb/cassandraclusters'
      'microsoft.documentdb/databaseaccounts'
      'microsoft.documentdb/mongoclusters'
      'microsoft.eventgrid/domains'
      'microsoft.eventgrid/partnernamespaces'
      'microsoft.eventgrid/partnertopics'
      'microsoft.eventgrid/systemtopics'
      'microsoft.eventgrid/topics'
      'microsoft.eventhub/namespaces'
      'microsoft.experimentation/experimentworkspaces'
      'microsoft.healthcareapis/services'
      'microsoft.healthcareapis/workspaces/dicomservices'
      'microsoft.healthcareapis/workspaces/fhirservices'
      'microsoft.healthcareapis/workspaces/iotconnectors'
      'microsoft.insights/autoscalesettings'
      'microsoft.insights/components'
      'microsoft.insights/datacollectionrules'
      'microsoft.keyvault/managedhsms'
      'microsoft.keyvault/vaults'
      'microsoft.kusto/clusters'
      'microsoft.loadtestservice/loadtests'
      'microsoft.logic/integrationaccounts'
      'microsoft.logic/workflows'
      'microsoft.machinelearningservices/registries'
      'microsoft.machinelearningservices/workspaces'
      'microsoft.machinelearningservices/workspaces/onlineendpoints'
      'microsoft.managednetworkfabric/networkdevices'
      'microsoft.media/mediaservices'
      'microsoft.media/videoanalyzers'
      'microsoft.media/mediaservices/liveevents'
      'microsoft.media/mediaservices/streamingendpoints'
      'microsoft.netapp/netappaccounts/capacitypools/volumes'
      'microsoft.network/applicationgateways'
      'microsoft.network/azurefirewalls'
      'microsoft.network/bastionhosts'
      'microsoft.network/dnsresolverpolicies'
      'microsoft.network/expressroutecircuits'
      'microsoft.network/frontdoors'
      'microsoft.network/loadbalancers'
      'microsoft.network/networkmanagers'
      'microsoft.network/networkmanagers/ipampools'
      'microsoft.network/networksecuritygroups'
      'microsoft.network/networksecurityperimeters'
      'microsoft.network/p2svpngateways'
      'microsoft.network/publicipaddresses'
      'microsoft.network/publicipprefixes'
      'microsoft.network/trafficmanagerprofiles'
      'microsoft.network/virtualnetworkgateways'
      'microsoft.network/virtualnetworks'
      'microsoft.network/vpngateways'
      'microsoft.networkanalytics/dataproducts'
      'microsoft.networkcloud/baremetalmachines'
      'microsoft.networkcloud/clusters'
      'microsoft.networkcloud/storageappliances'
      'microsoft.networkfunction/azuretrafficcollectors'
      'microsoft.notificationhubs/namespaces'
      'microsoft.notificationhubs/namespaces/notificationhubs'
      'microsoft.openenergyplatform/energyservices'
      'microsoft.operationalinsights/workspaces'
      'microsoft.powerbi/tenants/workspaces'
      'microsoft.powerbidedicated/capacities'
      'microsoft.purview/accounts'
      'microsoft.recoveryservices/vaults'
      'microsoft.relay/namespaces'
      'microsoft.search/searchservices'
      'microsoft.servicebus/namespaces'
      'microsoft.servicenetworking/trafficcontrollers'
      'microsoft.signalrservice/signalr'
      'microsoft.signalrservice/webpubsub'
      'microsoft.sql/managedinstances'
      'microsoft.sql/managedinstances/databases'
      'microsoft.sql/servers/databases'
      'microsoft.storagecache/caches'
      'microsoft.storagemover/storagemovers'
      'microsoft.streamanalytics/streamingjobs'
      'microsoft.synapse/workspaces'
      'microsoft.synapse/workspaces/bigdatapools'
      'microsoft.synapse/workspaces/kustopools'
      'microsoft.synapse/workspaces/scopepools'
      'microsoft.synapse/workspaces/sqlpools'
      'microsoft.timeseriesinsights/environments'
      'microsoft.timeseriesinsights/environments/eventsources'
      'microsoft.videoindexer/accounts'
      'microsoft.web/hostingenvironments'
      'microsoft.workloads/sapvirtualinstances'
      'microsoft.web/sites'
      'microsoft.autonomousdevelopmentplatform/accounts'
      'microsoft.compute/virtualmachines'
      'microsoft.confidentialledger/managedccf'
      'microsoft.connectedcache/cachenodes'
      'microsoft.connectedvehicle/platformaccounts'
      'microsoft.containerservice/fleets'
      'microsoft.containerservice/managedclusters'
      'microsoft.dbforpostgresql/serversv2'
      'microsoft.desktopvirtualization/appattachpackages'
      'microsoft.devopsinfrastructure/pools'
      'microsoft.eventgrid/namespaces'
      'microsoft.hardwaresecuritymodules/cloudhsmclusters'
      'microsoft.healthdataaiservices/deidservices'
      'microsoft.kubernetes/connectedclusters'
      'microsoft.monitor/accounts'
      'microsoft.netapp/netappaccounts/capacitypools'
      'microsoft.networkcloud/clustermanagers'
      'microsoft.openlogisticsplatform/workspaces'
      'microsoft.playfab/titles'
      'microsoft.powerbi/tenants'
      'microsoft.providerhub/providermonitorsettings'
      'microsoft.providerhub/providerregistrations'
      'microsoft.security/antimalwaresettings'
      'microsoft.security/defenderforstoragesettings'
      'microsoft.singularity/accounts'
      'microsoft.storage/storageaccounts/blobservices'
      'microsoft.storage/storageaccounts/fileservices'
      'microsoft.storage/storageaccounts/queueservices'
      'microsoft.storage/storageaccounts/tableservices'
      'microsoft.storagecache/amlfilesystems'
      'microsoft.web/sites/slots'
      'microsoft.web/staticsites'
      'nginx.nginxplus/nginxdeployment'
        ]
      }
      tagIncludeFilter: {
        type: 'Object'
        metadata: { displayName: 'Tag include filter', description: 'Map of tag name to tag value. Only resources matching ALL specified tags will have diagnostic settings deployed. Leave empty to apply to all resources.' }
        defaultValue: {}
      }
      tagExcludeFilter: {
        type: 'Object'
        metadata: { displayName: 'Tag exclude filter', description: 'Map of tag name to tag value. Resources matching ALL specified tags will be excluded from diagnostic settings deployment. Leave empty to exclude no resources.' }
        defaultValue: {}
      }
      categoryGroups: {
        type: 'Array'
        metadata: { displayName: 'Log category groups', description: '\'allLogs\' captures every available category; \'audit\' captures audit events only. Specify one or both.' }
        allowedValues: [ 'allLogs', 'audit' ]
        defaultValue: [ 'allLogs' ]
      }
    }
    policyDefinitions: [
      {
        policyDefinitionReferenceId: 'aad-domainservices'
        policyDefinitionId: policyDefAadDomainservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.aad/domainservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'agfoodplatform-farmbeats'
        policyDefinitionId: policyDefAgfoodplatformFarmbeats.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.agfoodplatform/farmbeats\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'analysisservices-servers'
        policyDefinitionId: policyDefAnalysisservicesServers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.analysisservices/servers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'apimanagement-service'
        policyDefinitionId: policyDefApimanagementService.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.apimanagement/service\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'app-managedenvironments'
        policyDefinitionId: policyDefAppManagedenvironments.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.app/managedenvironments\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'appconfiguration-configurationstores'
        policyDefinitionId: policyDefAppconfigurationConfigurationstores.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.appconfiguration/configurationstores\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'appplatform-spring'
        policyDefinitionId: policyDefAppplatformSpring.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.appplatform/spring\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'attestation-attestationproviders'
        policyDefinitionId: policyDefAttestationAttestationproviders.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.attestation/attestationproviders\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'automation-automationaccounts'
        policyDefinitionId: policyDefAutomationAutomationaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.automation/automationaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'autonomousdevelopmentplatform-workspaces'
        policyDefinitionId: policyDefAutonomousdevelopmentplatformWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.autonomousdevelopmentplatform/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'avs-privateclouds'
        policyDefinitionId: policyDefAvsPrivateclouds.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.avs/privateclouds\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'azureplaywrightservice-accounts'
        policyDefinitionId: policyDefAzureplaywrightserviceAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.azureplaywrightservice/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'azuresphere-catalogs'
        policyDefinitionId: policyDefAzuresphereCatalogs.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.azuresphere/catalogs\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'batch-batchaccounts'
        policyDefinitionId: policyDefBatchBatchaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.batch/batchaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'botservice-botservices'
        policyDefinitionId: policyDefBotserviceBotservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.botservice/botservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cache-redis'
        policyDefinitionId: policyDefCacheRedis.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cache/redis\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cache-redisenterprise-databases'
        policyDefinitionId: policyDefCacheRedisenterpriseDatabases.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cache/redisenterprise/databases\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cdn-cdnwebapplicationfirewallpolicies'
        policyDefinitionId: policyDefCdnCdnwebapplicationfirewallpolicies.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cdn/cdnwebapplicationfirewallpolicies\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cdn-profiles'
        policyDefinitionId: policyDefCdnProfiles.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cdn/profiles\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cdn-profiles-endpoints'
        policyDefinitionId: policyDefCdnProfilesEndpoints.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cdn/profiles/endpoints\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'chaos-experiments'
        policyDefinitionId: policyDefChaosExperiments.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.chaos/experiments\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'classicnetwork-networksecuritygroups'
        policyDefinitionId: policyDefClassicnetworkNetworksecuritygroups.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.classicnetwork/networksecuritygroups\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cloudtest-hostedpools'
        policyDefinitionId: policyDefCloudtestHostedpools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cloudtest/hostedpools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'codesigning-codesigningaccounts'
        policyDefinitionId: policyDefCodesigningCodesigningaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.codesigning/codesigningaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'cognitiveservices-accounts'
        policyDefinitionId: policyDefCognitiveservicesAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.cognitiveservices/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'communication-communicationservices'
        policyDefinitionId: policyDefCommunicationCommunicationservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.communication/communicationservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'community-communitytrainings'
        policyDefinitionId: policyDefCommunityCommunitytrainings.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.community/communitytrainings\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'confidentialledger-managedccfs'
        policyDefinitionId: policyDefConfidentialledgerManagedccfs.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.confidentialledger/managedccfs\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'connectedcache-enterprisemcccustomers'
        policyDefinitionId: policyDefConnectedcacheEnterprisemcccustomers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.connectedcache/enterprisemcccustomers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'connectedcache-ispcustomers'
        policyDefinitionId: policyDefConnectedcacheIspcustomers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.connectedcache/ispcustomers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'containerinstance-containergroups'
        policyDefinitionId: policyDefContainerinstanceContainergroups.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.containerinstance/containergroups\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'containerregistry-registries'
        policyDefinitionId: policyDefContainerregistryRegistries.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.containerregistry/registries\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'customproviders-resourceproviders'
        policyDefinitionId: policyDefCustomprovidersResourceproviders.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.customproviders/resourceproviders\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'd365customerinsights-instances'
        policyDefinitionId: policyDefD365customerinsightsInstances.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.d365customerinsights/instances\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dashboard-grafana'
        policyDefinitionId: policyDefDashboardGrafana.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dashboard/grafana\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'databricks-workspaces'
        policyDefinitionId: policyDefDatabricksWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.databricks/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'datafactory-factories'
        policyDefinitionId: policyDefDatafactoryFactories.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.datafactory/factories\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'datalakeanalytics-accounts'
        policyDefinitionId: policyDefDatalakeanalyticsAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.datalakeanalytics/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'datalakestore-accounts'
        policyDefinitionId: policyDefDatalakestoreAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.datalakestore/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dataprotection-backupvaults'
        policyDefinitionId: policyDefDataprotectionBackupvaults.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dataprotection/backupvaults\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'datashare-accounts'
        policyDefinitionId: policyDefDatashareAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.datashare/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbformariadb-servers'
        policyDefinitionId: policyDefDbformariadbServers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbformariadb/servers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbformysql-flexibleservers'
        policyDefinitionId: policyDefDbformysqlFlexibleservers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbformysql/flexibleservers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbformysql-servers'
        policyDefinitionId: policyDefDbformysqlServers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbformysql/servers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbforpostgresql-flexibleservers'
        policyDefinitionId: policyDefDbforpostgresqlFlexibleservers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbforpostgresql/flexibleservers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbforpostgresql-servergroupsv2'
        policyDefinitionId: policyDefDbforpostgresqlServergroupsv2.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbforpostgresql/servergroupsv2\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbforpostgresql-servers'
        policyDefinitionId: policyDefDbforpostgresqlServers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbforpostgresql/servers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'desktopvirtualization-applicationgroups'
        policyDefinitionId: policyDefDesktopvirtualizationApplicationgroups.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.desktopvirtualization/applicationgroups\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'desktopvirtualization-hostpools'
        policyDefinitionId: policyDefDesktopvirtualizationHostpools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.desktopvirtualization/hostpools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'desktopvirtualization-scalingplans'
        policyDefinitionId: policyDefDesktopvirtualizationScalingplans.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.desktopvirtualization/scalingplans\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'desktopvirtualization-workspaces'
        policyDefinitionId: policyDefDesktopvirtualizationWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.desktopvirtualization/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'devcenter-devcenters'
        policyDefinitionId: policyDefDevcenterDevcenters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.devcenter/devcenters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'devices-iothubs'
        policyDefinitionId: policyDefDevicesIothubs.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.devices/iothubs\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'devices-provisioningservices'
        policyDefinitionId: policyDefDevicesProvisioningservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.devices/provisioningservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'digitaltwins-digitaltwinsinstances'
        policyDefinitionId: policyDefDigitaltwinsDigitaltwinsinstances.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.digitaltwins/digitaltwinsinstances\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'documentdb-cassandraclusters'
        policyDefinitionId: policyDefDocumentdbCassandraclusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.documentdb/cassandraclusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'documentdb-databaseaccounts'
        policyDefinitionId: policyDefDocumentdbDatabaseaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.documentdb/databaseaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'documentdb-mongoclusters'
        policyDefinitionId: policyDefDocumentdbMongoclusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.documentdb/mongoclusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-domains'
        policyDefinitionId: policyDefEventgridDomains.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/domains\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-partnernamespaces'
        policyDefinitionId: policyDefEventgridPartnernamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/partnernamespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-partnertopics'
        policyDefinitionId: policyDefEventgridPartnertopics.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/partnertopics\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-systemtopics'
        policyDefinitionId: policyDefEventgridSystemtopics.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/systemtopics\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-topics'
        policyDefinitionId: policyDefEventgridTopics.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/topics\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventhub-namespaces'
        policyDefinitionId: policyDefEventhubNamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventhub/namespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'experimentation-experimentworkspaces'
        policyDefinitionId: policyDefExperimentationExperimentworkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.experimentation/experimentworkspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'healthcareapis-services'
        policyDefinitionId: policyDefHealthcareapisServices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.healthcareapis/services\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'healthcareapis-workspaces-dicomservices'
        policyDefinitionId: policyDefHealthcareapisWorkspacesDicomservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.healthcareapis/workspaces/dicomservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'healthcareapis-workspaces-fhirservices'
        policyDefinitionId: policyDefHealthcareapisWorkspacesFhirservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.healthcareapis/workspaces/fhirservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'healthcareapis-workspaces-iotconnectors'
        policyDefinitionId: policyDefHealthcareapisWorkspacesIotconnectors.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.healthcareapis/workspaces/iotconnectors\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'insights-autoscalesettings'
        policyDefinitionId: policyDefInsightsAutoscalesettings.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.insights/autoscalesettings\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'insights-components'
        policyDefinitionId: policyDefInsightsComponents.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.insights/components\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'insights-datacollectionrules'
        policyDefinitionId: policyDefInsightsDatacollectionrules.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.insights/datacollectionrules\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'keyvault-managedhsms'
        policyDefinitionId: policyDefKeyvaultManagedhsms.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.keyvault/managedhsms\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'keyvault-vaults'
        policyDefinitionId: policyDefKeyvaultVaults.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.keyvault/vaults\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'kusto-clusters'
        policyDefinitionId: policyDefKustoClusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.kusto/clusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'loadtestservice-loadtests'
        policyDefinitionId: policyDefLoadtestserviceLoadtests.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.loadtestservice/loadtests\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'logic-integrationaccounts'
        policyDefinitionId: policyDefLogicIntegrationaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.logic/integrationaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'logic-workflows'
        policyDefinitionId: policyDefLogicWorkflows.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.logic/workflows\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'machinelearningservices-registries'
        policyDefinitionId: policyDefMachinelearningservicesRegistries.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.machinelearningservices/registries\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'machinelearningservices-workspaces'
        policyDefinitionId: policyDefMachinelearningservicesWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.machinelearningservices/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'machinelearningservices-workspaces-onlineendpoints'
        policyDefinitionId: policyDefMachinelearningservicesWorkspacesOnlineendpoints.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.machinelearningservices/workspaces/onlineendpoints\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'managednetworkfabric-networkdevices'
        policyDefinitionId: policyDefManagednetworkfabricNetworkdevices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.managednetworkfabric/networkdevices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'media-mediaservices'
        policyDefinitionId: policyDefMediaMediaservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.media/mediaservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'media-videoanalyzers'
        policyDefinitionId: policyDefMediaVideoanalyzers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.media/videoanalyzers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'media-mediaservices-liveevents'
        policyDefinitionId: policyDefMediaMediaservicesLiveevents.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.media/mediaservices/liveevents\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'media-mediaservices-streamingendpoints'
        policyDefinitionId: policyDefMediaMediaservicesStreamingendpoints.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.media/mediaservices/streamingendpoints\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'netapp-netappaccounts-capacitypools-volumes'
        policyDefinitionId: policyDefNetappNetappaccountsCapacitypoolsVolumes.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.netapp/netappaccounts/capacitypools/volumes\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-applicationgateways'
        policyDefinitionId: policyDefNetworkApplicationgateways.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/applicationgateways\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-azurefirewalls'
        policyDefinitionId: policyDefNetworkAzurefirewalls.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/azurefirewalls\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-bastionhosts'
        policyDefinitionId: policyDefNetworkBastionhosts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/bastionhosts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-dnsresolverpolicies'
        policyDefinitionId: policyDefNetworkDnsresolverpolicies.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/dnsresolverpolicies\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-expressroutecircuits'
        policyDefinitionId: policyDefNetworkExpressroutecircuits.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/expressroutecircuits\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-frontdoors'
        policyDefinitionId: policyDefNetworkFrontdoors.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/frontdoors\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-loadbalancers'
        policyDefinitionId: policyDefNetworkLoadbalancers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/loadbalancers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-networkmanagers'
        policyDefinitionId: policyDefNetworkNetworkmanagers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/networkmanagers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-networkmanagers-ipampools'
        policyDefinitionId: policyDefNetworkNetworkmanagersIpampools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/networkmanagers/ipampools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-networksecuritygroups'
        policyDefinitionId: policyDefNetworkNetworksecuritygroups.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/networksecuritygroups\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-networksecurityperimeters'
        policyDefinitionId: policyDefNetworkNetworksecurityperimeters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/networksecurityperimeters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-p2svpngateways'
        policyDefinitionId: policyDefNetworkP2svpngateways.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/p2svpngateways\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-publicipaddresses'
        policyDefinitionId: policyDefNetworkPublicipaddresses.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/publicipaddresses\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-publicipprefixes'
        policyDefinitionId: policyDefNetworkPublicipprefixes.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/publicipprefixes\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-trafficmanagerprofiles'
        policyDefinitionId: policyDefNetworkTrafficmanagerprofiles.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/trafficmanagerprofiles\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-virtualnetworkgateways'
        policyDefinitionId: policyDefNetworkVirtualnetworkgateways.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/virtualnetworkgateways\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-virtualnetworks'
        policyDefinitionId: policyDefNetworkVirtualnetworks.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/virtualnetworks\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'network-vpngateways'
        policyDefinitionId: policyDefNetworkVpngateways.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.network/vpngateways\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkanalytics-dataproducts'
        policyDefinitionId: policyDefNetworkanalyticsDataproducts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkanalytics/dataproducts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkcloud-baremetalmachines'
        policyDefinitionId: policyDefNetworkcloudBaremetalmachines.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkcloud/baremetalmachines\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkcloud-clusters'
        policyDefinitionId: policyDefNetworkcloudClusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkcloud/clusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkcloud-storageappliances'
        policyDefinitionId: policyDefNetworkcloudStorageappliances.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkcloud/storageappliances\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkfunction-azuretrafficcollectors'
        policyDefinitionId: policyDefNetworkfunctionAzuretrafficcollectors.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkfunction/azuretrafficcollectors\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'notificationhubs-namespaces'
        policyDefinitionId: policyDefNotificationhubsNamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.notificationhubs/namespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'notificationhubs-namespaces-notificationhubs'
        policyDefinitionId: policyDefNotificationhubsNamespacesNotificationhubs.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.notificationhubs/namespaces/notificationhubs\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'openenergyplatform-energyservices'
        policyDefinitionId: policyDefOpenenergyplatformEnergyservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.openenergyplatform/energyservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'operationalinsights-workspaces'
        policyDefinitionId: policyDefOperationalinsightsWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.operationalinsights/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'powerbi-tenants-workspaces'
        policyDefinitionId: policyDefPowerbiTenantsWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.powerbi/tenants/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'powerbidedicated-capacities'
        policyDefinitionId: policyDefPowerbidedicatedCapacities.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.powerbidedicated/capacities\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'purview-accounts'
        policyDefinitionId: policyDefPurviewAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.purview/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'recoveryservices-vaults'
        policyDefinitionId: policyDefRecoveryservicesVaults.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.recoveryservices/vaults\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'relay-namespaces'
        policyDefinitionId: policyDefRelayNamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.relay/namespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'search-searchservices'
        policyDefinitionId: policyDefSearchSearchservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.search/searchservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'servicebus-namespaces'
        policyDefinitionId: policyDefServicebusNamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.servicebus/namespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'servicenetworking-trafficcontrollers'
        policyDefinitionId: policyDefServicenetworkingTrafficcontrollers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.servicenetworking/trafficcontrollers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'signalrservice-signalr'
        policyDefinitionId: policyDefSignalrserviceSignalr.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.signalrservice/signalr\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'signalrservice-webpubsub'
        policyDefinitionId: policyDefSignalrserviceWebpubsub.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.signalrservice/webpubsub\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'sql-managedinstances'
        policyDefinitionId: policyDefSqlManagedinstances.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.sql/managedinstances\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'sql-managedinstances-databases'
        policyDefinitionId: policyDefSqlManagedinstancesDatabases.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.sql/managedinstances/databases\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'sql-servers-databases'
        policyDefinitionId: policyDefSqlServersDatabases.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.sql/servers/databases\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storagecache-caches'
        policyDefinitionId: policyDefStoragecacheCaches.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storagecache/caches\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storagemover-storagemovers'
        policyDefinitionId: policyDefStoragemoverStoragemovers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storagemover/storagemovers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'streamanalytics-streamingjobs'
        policyDefinitionId: policyDefStreamanalyticsStreamingjobs.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.streamanalytics/streamingjobs\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'synapse-workspaces'
        policyDefinitionId: policyDefSynapseWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.synapse/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'synapse-workspaces-bigdatapools'
        policyDefinitionId: policyDefSynapseWorkspacesBigdatapools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.synapse/workspaces/bigdatapools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'synapse-workspaces-kustopools'
        policyDefinitionId: policyDefSynapseWorkspacesKustopools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.synapse/workspaces/kustopools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'synapse-workspaces-scopepools'
        policyDefinitionId: policyDefSynapseWorkspacesScopepools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.synapse/workspaces/scopepools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'synapse-workspaces-sqlpools'
        policyDefinitionId: policyDefSynapseWorkspacesSqlpools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.synapse/workspaces/sqlpools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'timeseriesinsights-environments'
        policyDefinitionId: policyDefTimeseriesinsightsEnvironments.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.timeseriesinsights/environments\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'timeseriesinsights-environments-eventsources'
        policyDefinitionId: policyDefTimeseriesinsightsEnvironmentsEventsources.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.timeseriesinsights/environments/eventsources\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'videoindexer-accounts'
        policyDefinitionId: policyDefVideoindexerAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.videoindexer/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'web-hostingenvironments'
        policyDefinitionId: policyDefWebHostingenvironments.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.web/hostingenvironments\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'workloads-sapvirtualinstances'
        policyDefinitionId: policyDefWorkloadsSapvirtualinstances.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.workloads/sapvirtualinstances\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'web-sites'
        policyDefinitionId: policyDefWebSites.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.web/sites\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'autonomousdevelopmentplatform-accounts'
        policyDefinitionId: policyDefAutonomousdevelopmentplatformAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.autonomousdevelopmentplatform/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'compute-virtualmachines'
        policyDefinitionId: policyDefComputeVirtualmachines.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.compute/virtualmachines\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'confidentialledger-managedccf'
        policyDefinitionId: policyDefConfidentialledgerManagedccf.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.confidentialledger/managedccf\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'connectedcache-cachenodes'
        policyDefinitionId: policyDefConnectedcacheCachenodes.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.connectedcache/cachenodes\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'connectedvehicle-platformaccounts'
        policyDefinitionId: policyDefConnectedvehiclePlatformaccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.connectedvehicle/platformaccounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'containerservice-fleets'
        policyDefinitionId: policyDefContainerserviceFleets.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.containerservice/fleets\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'containerservice-managedclusters'
        policyDefinitionId: policyDefContainerserviceManagedclusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.containerservice/managedclusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'dbforpostgresql-serversv2'
        policyDefinitionId: policyDefDbforpostgresqlServersv2.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.dbforpostgresql/serversv2\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'desktopvirtualization-appattachpackages'
        policyDefinitionId: policyDefDesktopvirtualizationAppattachpackages.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.desktopvirtualization/appattachpackages\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'devopsinfrastructure-pools'
        policyDefinitionId: policyDefDevopsinfrastructurePools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.devopsinfrastructure/pools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'eventgrid-namespaces'
        policyDefinitionId: policyDefEventgridNamespaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.eventgrid/namespaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'hardwaresecuritymodules-cloudhsmclusters'
        policyDefinitionId: policyDefHardwaresecuritymodulesCloudhsmclusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.hardwaresecuritymodules/cloudhsmclusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'healthdataaiservices-deidservices'
        policyDefinitionId: policyDefHealthdataaiservicesDeidservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.healthdataaiservices/deidservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'kubernetes-connectedclusters'
        policyDefinitionId: policyDefKubernetesConnectedclusters.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.kubernetes/connectedclusters\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'monitor-accounts'
        policyDefinitionId: policyDefMonitorAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.monitor/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'netapp-netappaccounts-capacitypools'
        policyDefinitionId: policyDefNetappNetappaccountsCapacitypools.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.netapp/netappaccounts/capacitypools\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'networkcloud-clustermanagers'
        policyDefinitionId: policyDefNetworkcloudClustermanagers.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.networkcloud/clustermanagers\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'openlogisticsplatform-workspaces'
        policyDefinitionId: policyDefOpenlogisticsplatformWorkspaces.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.openlogisticsplatform/workspaces\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'playfab-titles'
        policyDefinitionId: policyDefPlayfabTitles.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.playfab/titles\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'powerbi-tenants'
        policyDefinitionId: policyDefPowerbiTenants.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.powerbi/tenants\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'providerhub-providermonitorsettings'
        policyDefinitionId: policyDefProviderhubProvidermonitorsettings.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.providerhub/providermonitorsettings\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'providerhub-providerregistrations'
        policyDefinitionId: policyDefProviderhubProviderregistrations.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.providerhub/providerregistrations\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'security-antimalwaresettings'
        policyDefinitionId: policyDefSecurityAntimalwaresettings.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.security/antimalwaresettings\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'security-defenderforstoragesettings'
        policyDefinitionId: policyDefSecurityDefenderforstoragesettings.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.security/defenderforstoragesettings\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'singularity-accounts'
        policyDefinitionId: policyDefSingularityAccounts.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.singularity/accounts\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storage-storageaccounts-blobservices'
        policyDefinitionId: policyDefStorageStorageaccountsBlobservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storage/storageaccounts/blobservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storage-storageaccounts-fileservices'
        policyDefinitionId: policyDefStorageStorageaccountsFileservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storage/storageaccounts/fileservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storage-storageaccounts-queueservices'
        policyDefinitionId: policyDefStorageStorageaccountsQueueservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storage/storageaccounts/queueservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storage-storageaccounts-tableservices'
        policyDefinitionId: policyDefStorageStorageaccountsTableservices.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storage/storageaccounts/tableservices\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'storagecache-amlfilesystems'
        policyDefinitionId: policyDefStoragecacheAmlfilesystems.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.storagecache/amlfilesystems\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'web-sites-slots'
        policyDefinitionId: policyDefWebSitesSlots.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.web/sites/slots\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'web-staticsites'
        policyDefinitionId: policyDefWebStaticsites.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'microsoft.web/staticsites\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
      {
        policyDefinitionReferenceId: 'nginx-nginxplus-nginxdeployment'
        policyDefinitionId: policyDefNginxNginxplusNginxdeployment.id
        parameters: {
          effect: { value: '[if(contains(parameters(\'resourceTypeList\'),\'nginx.nginxplus/nginxdeployment\'),parameters(\'effect\'),\'Disabled\')]' }
          diagnosticSettingName: { value: '[parameters(\'diagnosticSettingName\')]' }
          storageAccountsByRegion: { value: '[parameters(\'storageAccountsByRegion\')]' }
          tagIncludeFilter: { value: '[parameters(\'tagIncludeFilter\')]' }
          tagExcludeFilter: { value: '[parameters(\'tagExcludeFilter\')]' }
          categoryGroups: { value: '[parameters(\'categoryGroups\')]' }
        }
      }
    ]
  }
}

output initiativeId string = initiative.id
