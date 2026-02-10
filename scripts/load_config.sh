#!/bin/bash

# ============================================
# Configuration Loader for Shell Scripts
# ============================================
# This script loads configuration from config.yml and exports as environment variables
# Usage: source scripts/load_config.sh

set -euo pipefail

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$PROJECT_ROOT/config.yml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found at $CONFIG_FILE"
    exit 1
fi

# Function to parse YAML and get value
# Usage: get_config_value "azure_openai.completion_deployment.name"
get_config_value() {
    local key="$1"
    local default="${2:-}"

    # Convert dot notation to yq format
    local yq_path=$(echo "$key" | sed 's/\./\./g')

    # Try to get value using yq (if available) or python
    if command -v yq &> /dev/null; then
        value=$(yq eval ".$yq_path" "$CONFIG_FILE" 2>/dev/null || echo "$default")
    elif command -v python3 &> /dev/null; then
        value=$(python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_FILE', 'r') as f:
        config = yaml.safe_load(f)
    keys = '$key'.split('.')
    value = config
    for k in keys:
        value = value.get(k, {})
    if value and value != {}:
        print(value)
    else:
        print('$default')
except Exception as e:
    print('$default')
" 2>/dev/null)
    else
        echo "Error: Neither yq nor python3 found. Please install one of them."
        exit 1
    fi

    # Handle environment variable substitution
    if [[ "$value" =~ \$\{([^:}]+):?([^}]*)\} ]]; then
        env_var="${BASH_REMATCH[1]}"
        env_default="${BASH_REMATCH[2]}"
        value="${!env_var:-$env_default}"
    fi

    # Return empty string as empty, not "null"
    if [ "$value" = "null" ] || [ "$value" = "None" ] || [ -z "$value" ]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Function to load all config values and export as environment variables
load_config() {
    echo "Loading configuration from $CONFIG_FILE..."

    # Azure OpenAI - Completion (Realtime API)
    export AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME=$(get_config_value "azure_openai.completion_deployment.name")
    export AZURE_OPENAI_COMPLETION_MODEL=$(get_config_value "azure_openai.completion_deployment.model")
    export AZURE_OPENAI_COMPLETION_MODEL_VERSION=$(get_config_value "azure_openai.completion_deployment.version")
    export AZURE_OPENAI_REALTIME_DEPLOYMENT_CAPACITY=$(get_config_value "azure_openai.completion_deployment.capacity")

    # Azure OpenAI - Chat (Text API)
    export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=$(get_config_value "azure_openai.chat_deployment.name")
    export AZURE_OPENAI_CHAT_MODEL=$(get_config_value "azure_openai.chat_deployment.model")
    export AZURE_OPENAI_CHAT_MODEL_VERSION=$(get_config_value "azure_openai.chat_deployment.version")
    export AZURE_OPENAI_CHAT_DEPLOYMENT_CAPACITY=$(get_config_value "azure_openai.chat_deployment.capacity")

    # Azure OpenAI - Embedding
    export AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$(get_config_value "azure_openai.embedding_deployment.name")
    export AZURE_OPENAI_EMBEDDING_MODEL=$(get_config_value "azure_openai.embedding_deployment.model")
    export AZURE_OPENAI_EMBEDDING_MODEL_VERSION=$(get_config_value "azure_openai.embedding_deployment.version" "1")
    export AZURE_OPENAI_EMB_DEPLOYMENT_CAPACITY=$(get_config_value "azure_openai.embedding_deployment.capacity")
    export AZURE_OPENAI_EMB_DIMENSIONS=$(get_config_value "azure_openai.embedding_deployment.dimensions")

    # Azure OpenAI - API
    export AZURE_OPENAI_VERSION=$(get_config_value "azure_openai.api_version")
    export OPENAI_API_TYPE=$(get_config_value "azure_openai.api_type")

    # Azure Search
    export AZURE_SEARCH_INDEX=$(get_config_value "azure_search.index.name")
    export AZURE_SEARCH_SEMANTIC_CONFIGURATION=$(get_config_value "azure_search.index.semantic_configuration")
    export AZURE_SEARCH_SERVICE_SKU=$(get_config_value "azure_search.service.sku")
    export AZURE_SEARCH_SEMANTIC_RANKER=$(get_config_value "azure_search.service.semantic_ranker")
    export AZURE_SEARCH_SERVICE_LOCATION=$(get_config_value "azure_search.service.location")

    # Azure Search - Fields
    export AZURE_SEARCH_IDENTIFIER_FIELD=$(get_config_value "azure_search.index.fields.identifier")
    export AZURE_SEARCH_CONTENT_FIELD=$(get_config_value "azure_search.index.fields.content")
    export AZURE_SEARCH_TITLE_FIELD=$(get_config_value "azure_search.index.fields.title")
    export AZURE_SEARCH_EMBEDDING_FIELD=$(get_config_value "azure_search.index.fields.embedding")
    export AZURE_SEARCH_USE_VECTOR_QUERY=$(get_config_value "azure_search.index.use_vector_query")

    # Azure Storage
    export AZURE_STORAGE_SKU=$(get_config_value "azure_storage.sku")
    export AZURE_STORAGE_CONTAINER=$(get_config_value "azure_storage.containers[0].name" "content")
    export AZURE_STORAGE_PROMPT_CONTAINER=$(get_config_value "azure_storage.containers[1].name" "prompt")

    # Environment
    export CONFIG_RES_NAME=$(get_config_value "environment.res_name")
    export CONFIG_LOCATION=$(get_config_value "environment.location" "swedencentral")
    export RESOURCE_GROUP_PREFIX=$(get_config_value "environment.resource_group_prefix")
    export SERVICE_NAME=$(get_config_value "environment.service_name" "rcca")

    # ACS
    export ACS_PHONE_NUMBER=$(get_config_value "azure_communication_services.phone_number" "Manualupdate")
    export ACS_CALLBACK_PATH_LOCAL=$(get_config_value "azure_communication_services.local.callback_path")
    export ACS_WEBSOCKET_PATH_LOCAL=$(get_config_value "azure_communication_services.local.websocket_path")

    # Container Apps
    export CONTAINER_APP_CPU=$(get_config_value "container_apps.resources.cpu")
    export CONTAINER_APP_MEMORY=$(get_config_value "container_apps.resources.memory")
    export CONTAINER_APP_MIN_REPLICAS=$(get_config_value "container_apps.scale.min_replicas")
    export CONTAINER_APP_MAX_REPLICAS=$(get_config_value "container_apps.scale.max_replicas")

    # Application
    export APP_HOST=$(get_config_value "application.host")
    export APP_PORT=$(get_config_value "application.port")
    export APP_LOG_LEVEL=$(get_config_value "application.log_level")

    echo "✓ Configuration loaded successfully"
}

# Auto-load if sourced
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    load_config
fi
