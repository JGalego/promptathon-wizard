/*
Adapted from
https://learn.microsoft.com/en-us/azure/redis/web-app-bicep-with-redis-cache-provision
https://luke.geek.nz/azure/deploying-azure-managed-redis-with-bicep/
*/

@description('A unique name for the promptathon app. This name will be used to create the web app and hosting plan.')
@minLength(3)
@maxLength(63)
param webAppName string = 'promptathon${uniqueString(resourceGroup().id)}'

@description('Describes plan\'s pricing tier and instance size. Check details at https://azure.microsoft.com/en-us/pricing/details/app-service/')
@allowed([
  'F1'
  'D1'
  'B1'
  'B2'
  'B3'
  'S1'
  'S2'
  'S3'
  'P1'
  'P2'
  'P3'
  'P4'
])
param skuName string = 'F1'

@description('Describes plan\'s instance count')
@minValue(1)
@maxValue(7)
param skuCapacity int = 1

@description('Describes the runtime stack to use for the web app. Check details at https://learn.microsoft.com/en-us/azure/app-service/containers/app-service-linux-faq#what-are-the-supported-linux-stacks')
param linuxFxVersion string = 'python|3.11'

@description('Location for all resources.')
param location string = resourceGroup().location

// Redis Cache
var redisCacheName = 'cache${uniqueString(resourceGroup().id)}'
var redisAccessPolicyAssignment = 'redisWebAppAssignment'

// Azure OpenAI
@secure()
@description('Azure OpenAI API Key')
param azureOpenAIKey string

@description('Azure OpenAI API Endpoint')
@secure()
param azureOpenAIBase string

// App Service
var appServicePlanName = toLower('AppServicePlan-${webAppName}')
var webSiteName = toLower('WebApp-${webAppName}')

/*************
 * Resources *
 *************/

resource appServicePlan 'Microsoft.Web/serverfarms@2020-06-01' = {
  name: appServicePlanName
  location: location
  properties: {
    reserved: true
  }
  sku: {
    name: skuName
    capacity: skuCapacity
  }
  kind: 'linux'
}

resource appService 'Microsoft.Web/sites@2020-06-01' = {
  name: webSiteName
  location: location
  tags: {
    'hidden-related:${appServicePlan.id}': 'empty'
    displayName: 'Website'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: linuxFxVersion
    }
  }
  dependsOn: [
    redisEnterprise
  ]
}

resource appsettings 'Microsoft.Web/sites/config@2021-03-01' = {
  parent: appService
  name: 'appsettings'
  properties: {
    // App settings
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
    ENABLE_ORYX_BUILD: 'true'
    // Redis Cache
    REDIS_CLUSTER: '1'
    REDIS_HOST: redisEnterprise.properties.hostName
    REDIS_PORT: string(redisEnterpriseDatabase.properties.port)
    REDIS_PASSWORD: redisEnterpriseDatabase.listKeys().primaryKey
    REDIS_SSL: '1'
    // Azure OpenAI
    AZURE_API_KEY: azureOpenAIKey
    AZURE_API_BASE: azureOpenAIBase
  }
}

resource redisEnterprise 'Microsoft.Cache/redisEnterprise@2024-09-01-preview' = {
  name: redisCacheName
  location: location
  sku: {
    name: 'Balanced_B5'
  }
  identity: {
    type: 'None'
  }
  properties: {
    minimumTlsVersion: '1.2'    
  }
}

resource redisEnterpriseDatabase 'Microsoft.Cache/redisEnterprise/databases@2024-09-01-preview' = {
  name: 'default'
  parent: redisEnterprise
  properties:{
    clientProtocol: 'Encrypted'
    accessKeysAuthentication: 'Enabled'
    port: 10000
    clusteringPolicy: 'OSSCluster'
    evictionPolicy: 'NoEviction'
    persistence:{
      aofEnabled: false 
      rdbEnabled: true
      rdbFrequency: '1h'
    }
  }
}

resource redisAccessPolicyAssignmentName 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2024-09-01-preview' = {
  name: redisAccessPolicyAssignment
  parent: redisEnterpriseDatabase
  properties: {
    accessPolicyName: 'default'
    user: {
      objectId: appService.identity.principalId
    }
  }
}

/***********
 * Outputs *
 ***********/

// Redis Cache
output redisEnterpriseName string = redisEnterprise.name
output redisEnterpriseId string = redisEnterprise.id
output redisEnterpriseHostName string = redisEnterprise.properties.hostName
output redisEnterprisePort int = redisEnterpriseDatabase.properties.port

// App Service
output webAppName string = appService.name
output webAppUrl string = 'https://${appService.properties.defaultHostName}'
