param name string
param location string = resourceGroup().location
param tags object = {}
param aiSearchName string
param storageAccountName string
param identityName string
param applicationInsightsName string
param containerAppsEnvironmentName string
param containerRegistryName string
param communicationServiceName string
param communicationServicePhoneNumber string
param serviceName string = 'web'
param imageName string
param openaiName string

// Azure OpenAI Configuration Parameters
param completionDeploymentName string = 'gpt-4o-realtime-preview'
param chatDeploymentName string = 'gpt-4.1'
param openaiApiVersion string = '2024-10-01-preview'

// Azure Search Configuration Parameters
param searchIndexName string = 'voicerag-intvect'
param searchSemanticConfiguration string = 'default'

// Container Resources
param containerCpu string = '1'
param containerMemory string = '2.0Gi'
param minReplicas int = 1
param maxReplicas int = 2

resource userIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

resource app 'Microsoft.App/containerApps@2023-04-01-preview' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${userIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'single'     
      ingress: {
        external: true
        targetPort: 8765
        transport: 'auto'
      }
      registries: [
        {
          server: '${containerRegistry.name}.azurecr.io'
          identity: userIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          image: imageName
          name: serviceName
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: userIdentity.properties.clientId
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: applicationInsights.properties.ConnectionString
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: account.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME'
              value: completionDeploymentName
            }
            {
              name: 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME'
              value: chatDeploymentName
            }
            {
              name: 'AZURE_OPENAI_VERSION'
              value: openaiApiVersion
            }
            {
              name: 'OPENAI_API_TYPE'
              value: 'azure'
            }
            { 
              name: 'ACS_SOURCE_NUMBER'
              value: communicationServicePhoneNumber 
            }
            { 
              name: 'ACS_CONNECTION_STRING'
              value: communicationService.listKeys().primaryConnectionString
            }
            {
              name: 'ACS_CALLBACK_PATH'
              value: 'Set by Deployment Script'
            }
            {
              name: 'ACS_MEDIA_STREAMING_WEBSOCKET_PATH'
              value: 'Set by Deployment Script'
            }
            {
              name: 'AZURE_SEARCH_API_KEY'
              value: 'Set by Deployment Script'
            }  
            {
              name: 'AZURE_SEARCH_ENDPOINT'
              value: 'https://${searchService.name}.search.windows.net'
            }  
            {
              name: 'AZURE_SEARCH_INDEX'
              value: 'Set by Deployment Script'
            }  
            {
              name: 'AZURE_SEARCH_SEMANTIC_CONFIGURATION'
              value: 'Set by Deployment Script'
            }   
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value}'
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
  scope: resourceGroup()
}

resource account 'Microsoft.CognitiveServices/accounts@2022-10-01' existing = {
  name: openaiName
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2022-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2022-02-01-preview' existing = {
  name: containerRegistryName
}

resource communicationService 'Microsoft.Communication/CommunicationServices@2023-04-01-preview' existing = {
  name: communicationServiceName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName 
}

output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
