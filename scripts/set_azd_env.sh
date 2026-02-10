#!/bin/bash

# ============================================
# Set AZD Environment Variables from config.yml
# ============================================
# This script loads config.yml, ensures the azd environment exists,
# and sets all azd environment variables.
#
# Usage:
#   source scripts/set_azd_env.sh   # Init env + set vars, then run azd up
#   (also called automatically by preprovision hook)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load configuration
source "$PROJECT_ROOT/scripts/load_config.sh"

# Ensure azd environment exists (based on config.yml res_name)
EXPECTED_ENV="$CONFIG_RES_NAME"
CURRENT_ENV=$(azd env list --output json 2>/dev/null | python3 -c "
import sys, json
try:
    envs = json.load(sys.stdin)
    for e in envs:
        if e.get('IsDefault', False):
            print(e.get('Name', ''))
            break
except:
    pass
" 2>/dev/null || echo "")

if [ -z "$CURRENT_ENV" ]; then
    echo "Creating azd environment '$EXPECTED_ENV' from config.yml..."
    azd env new "$EXPECTED_ENV" --no-prompt
elif [ "$CURRENT_ENV" != "$EXPECTED_ENV" ]; then
    # Check if expected env already exists
    ENV_EXISTS=$(azd env list --output json 2>/dev/null | python3 -c "
import sys, json
try:
    envs = json.load(sys.stdin)
    for e in envs:
        if e.get('Name') == '$EXPECTED_ENV':
            print('yes')
            break
except:
    pass
" 2>/dev/null || echo "")

    if [ "$ENV_EXISTS" = "yes" ]; then
        echo "Switching to azd environment '$EXPECTED_ENV'..."
        azd env select "$EXPECTED_ENV"
    else
        echo "Creating azd environment '$EXPECTED_ENV' from config.yml..."
        azd env new "$EXPECTED_ENV" --no-prompt
    fi
else
    echo "Using azd environment '$EXPECTED_ENV'"
fi

echo "Setting azd environment variables from config.yml..."

# Location
azd env set AZURE_LOCATION "$CONFIG_LOCATION"
azd env set AZURE_AI_RESOURCE_LOCATION "$CONFIG_LOCATION"

# Azure OpenAI - Completion (Realtime)
azd env set AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME "$AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME"
azd env set AZURE_OPENAI_COMPLETION_MODEL "$AZURE_OPENAI_COMPLETION_MODEL"
azd env set AZURE_OPENAI_COMPLETION_MODEL_VERSION "$AZURE_OPENAI_COMPLETION_MODEL_VERSION"
azd env set AZURE_OPENAI_REALTIME_DEPLOYMENT_CAPACITY "$AZURE_OPENAI_REALTIME_DEPLOYMENT_CAPACITY"

# Azure OpenAI - Chat (Text)
azd env set AZURE_OPENAI_CHAT_DEPLOYMENT_NAME "$AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
azd env set AZURE_OPENAI_CHAT_MODEL "$AZURE_OPENAI_CHAT_MODEL"
azd env set AZURE_OPENAI_CHAT_MODEL_VERSION "$AZURE_OPENAI_CHAT_MODEL_VERSION"
azd env set AZURE_OPENAI_CHAT_DEPLOYMENT_CAPACITY "$AZURE_OPENAI_CHAT_DEPLOYMENT_CAPACITY"

# Azure OpenAI - Embedding
azd env set AZURE_OPENAI_EMBEDDING_DEPLOYMENT "$AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
azd env set AZURE_OPENAI_EMBEDDING_MODEL_VERSION "$AZURE_OPENAI_EMBEDDING_MODEL_VERSION"
azd env set AZURE_OPENAI_EMB_DEPLOYMENT_CAPACITY "$AZURE_OPENAI_EMB_DEPLOYMENT_CAPACITY"

# Azure OpenAI - API
azd env set AZURE_OPENAI_VERSION "$AZURE_OPENAI_VERSION"

# Azure Search
azd env set AZURE_SEARCH_INDEX "$AZURE_SEARCH_INDEX"
azd env set AZURE_SEARCH_SEMANTIC_CONFIGURATION "$AZURE_SEARCH_SEMANTIC_CONFIGURATION"
azd env set AZURE_SEARCH_SERVICE_SKU "$AZURE_SEARCH_SERVICE_SKU"
azd env set AZURE_SEARCH_SEMANTIC_RANKER "$AZURE_SEARCH_SEMANTIC_RANKER"

# Azure Search - Fields
azd env set AZURE_SEARCH_IDENTIFIER_FIELD "$AZURE_SEARCH_IDENTIFIER_FIELD"
azd env set AZURE_SEARCH_CONTENT_FIELD "$AZURE_SEARCH_CONTENT_FIELD"
azd env set AZURE_SEARCH_TITLE_FIELD "$AZURE_SEARCH_TITLE_FIELD"
azd env set AZURE_SEARCH_EMBEDDING_FIELD "$AZURE_SEARCH_EMBEDDING_FIELD"
azd env set AZURE_SEARCH_USE_VECTOR_QUERY "$AZURE_SEARCH_USE_VECTOR_QUERY"

# Azure Storage
azd env set AZURE_STORAGE_SKU "$AZURE_STORAGE_SKU"
azd env set AZURE_STORAGE_CONTAINER "$AZURE_STORAGE_CONTAINER"
azd env set AZURE_STORAGE_PROMPT_CONTAINER "$AZURE_STORAGE_PROMPT_CONTAINER"

echo "✓ AZD environment variables set successfully"
echo ""
echo "You can now run: azd up"
