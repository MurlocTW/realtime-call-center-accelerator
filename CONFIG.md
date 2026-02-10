# Configuration Management Guide

This document explains the unified configuration management system for the Call Center Accelerator project.

## Overview

All configuration is now managed through a single `config.yml` file, eliminating hardcoded values scattered across multiple files. This provides:

- ✅ **Single source of truth** for all configuration
- ✅ **Environment variable overrides** supported
- ✅ **Type-safe configuration** in Python
- ✅ **Consistent values** across all scripts and deployments
- ✅ **Easy maintenance** and updates

## Quick Start

1. **Copy the example config file:**
   ```bash
   cp config.example.yml config.yml
   ```

2. **Update values in `config.yml`** with your deployment names and preferences

3. **Set required environment variables:**
   ```bash
   # For local development
   export AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com/"
   export AZURE_OPENAI_API_KEY="your-api-key"
   export AZURE_SEARCH_ENDPOINT="https://your-search.search.windows.net"
   export AZURE_SEARCH_API_KEY="your-search-key"
   export AZURE_STORAGE_CONNECTION_STRING="your-storage-connection-string"
   export ACS_CONNECTION_STRING="your-acs-connection-string"
   ```

4. **For local development, you can also use:**
   ```bash
   source scripts/get_service_env.sh
   ```

## Configuration Structure

### Main Configuration File: `config.yml`

Located in the project root, this YAML file contains all configuration settings organized into logical sections:

```yaml
environment:          # Environment settings
azure_openai:         # OpenAI deployment settings
azure_search:         # AI Search configuration
azure_storage:        # Storage settings
azure_communication_services:  # ACS settings
container_apps:       # Container configuration
application:          # App runtime settings
service_names:        # Optional service name overrides
```

### Key Configuration Sections

#### 1. Azure OpenAI Configuration

```yaml
azure_openai:
  completion_deployment:
    name: "gpt-4o-realtime-preview"  # For audio/voice
  chat_deployment:
    name: "gpt-4.1"                  # For text chat
  embedding_deployment:
    name: "text-embedding-3-large"   # For embeddings
```

**Important:** These deployment names must match what you created in Azure OpenAI Studio.

#### 2. Azure AI Search Configuration

```yaml
azure_search:
  service:
    sku: "standard"
    semantic_ranker: "free"
  index:
    name: "voicerag-intvect"
    semantic_configuration: "default"
```

#### 3. Azure Communication Services

```yaml
azure_communication_services:
  phone_number: "${ACS_PHONE_NUMBER:Manualupdate}"
  local:
    callback_path: "http://localhost:8765/acs"
    websocket_path: "ws://localhost:8765/realtime-acs"
```

## Environment Variable Overrides

Any value in `config.yml` can be overridden by environment variables. The system checks environment variables first, then falls back to config.yml values.

### Priority Order:
1. **Environment Variables** (highest priority)
2. **config.yml values**
3. **Default values** (lowest priority)

### Environment Variable Reference Format

In `config.yml`, you can reference environment variables using:

```yaml
# ${VAR_NAME} - required, fails if not set
# ${VAR_NAME:default} - optional, uses default if not set
phone_number: "${ACS_PHONE_NUMBER:Manualupdate}"
```

## Usage in Different Contexts

### 1. Shell Scripts (Bash)

Shell scripts automatically load configuration via `load_config.sh`:

```bash
#!/bin/bash
source scripts/load_config.sh

# Now you can use config variables
echo "Chat deployment: $AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
echo "Search index: $AZURE_SEARCH_INDEX"
```

**Available variables:**
- `AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME`
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_OPENAI_VERSION`
- `AZURE_SEARCH_INDEX`
- `AZURE_SEARCH_SEMANTIC_CONFIGURATION`
- And many more (see `scripts/load_config.sh`)

### 2. Bicep Templates

Bicep files receive configuration values as parameters from the deployment script:

```bicep
param completionDeploymentName string = 'gpt-4o-realtime-preview'
param chatDeploymentName string = 'gpt-4.1'
```

These are passed from `deploy.sh` which loads values from `config.yml`.

### 3. Python Application

Python code uses the `backend.config` module:

```python
from backend.config import get_config

# Get configuration instance
config = get_config()

# Access configuration values (type-safe)
llm_deployment = config.openai.completion_deployment_name
chat_deployment = config.openai.chat_deployment_name
search_index = config.search.index_name

# Validate configuration
if not config.validate():
    raise ValueError("Configuration error")
```

**Configuration classes:**
- `config.openai` - OpenAIConfig
- `config.search` - SearchConfig
- `config.storage` - StorageConfig
- `config.communication_services` - CommunicationServicesConfig
- `config.application` - ApplicationConfig

## Files Modified

The following files now use the unified configuration system:

### Configuration Files
- ✅ `config.yml` - Main configuration file (NEW)
- ✅ `config.example.yml` - Example configuration (NEW)
- ✅ `scripts/load_config.sh` - Shell config loader (NEW)
- ✅ `src/app/backend/config.py` - Python config loader (NEW)

### Updated Files
- ✅ `azd-hooks/deploy.sh` - Deployment script
- ✅ `scripts/get_service_env.sh` - Environment setup script
- ✅ `infra/main.bicep` - Main infrastructure template
- ✅ `infra/main.parameters.json` - Infrastructure parameters
- ✅ `infra/core/app/web.bicep` - Container app template
- ✅ `src/app/app.py` - Main application

### Removed Hardcoded Values

The following hardcoded values were removed and moved to `config.yml`:

| Value | Old Locations | Now In |
|-------|--------------|---------|
| `gpt-4.1` | deploy.sh, web.bicep, get_service_env.sh, app.py | config.yml: `azure_openai.chat_deployment.name` |
| `gpt-4o-realtime-preview` | web.bicep, get_service_env.sh | config.yml: `azure_openai.completion_deployment.name` |
| `voicerag-intvect` | deploy.sh, get_service_env.sh, main.bicep | config.yml: `azure_search.index.name` |
| `default` | deploy.sh, get_service_env.sh, main.bicep | config.yml: `azure_search.index.semantic_configuration` |
| `2024-12-17` | web.bicep | config.yml: `azure_openai.completion_deployment.version` |

## Deployment Workflow

### 1. Azure Deployment

```bash
# 1. Ensure config.yml is set up
cat config.yml

# 2. Deploy infrastructure and app
azd up

# The deploy.sh script automatically:
# - Loads config.yml via load_config.sh
# - Uses service_name from config.yml (no need to pass as argument)
# - Passes values to bicep templates
# - Updates container app with correct env vars

# Note: You can still use command line arguments for backward compatibility:
# ./azd-hooks/deploy.sh <service_name> <env_name>
# But config.yml values take precedence
```

### Service Name Configuration

The `environment.service_name` in config.yml determines your container app name:
- Must be 3-12 characters
- Only lowercase letters and numbers
- Example: `service_name: "app"` creates container app `callcenterapp`

**Before (manual input):**
```bash
./azd-hooks/deploy.sh app dev  # Had to type every time
```

**After (from config):**
```bash
azd up  # Reads service_name from config.yml automatically
```

### 2. Local Development

```bash
# 1. Set up environment variables
source scripts/get_service_env.sh

# 2. Run the application
cd src/app
python app.py
```

The application will:
- Load `config.yml` automatically
- Override with environment variables where set
- Validate all required configuration
- Start with correct settings

## Configuration Dependencies

```
config.yml
    ↓
├── Shell Scripts (via load_config.sh)
│   ├── deploy.sh
│   └── get_service_env.sh
│       ↓
├── Bicep Templates (via parameters)
│   ├── main.bicep
│   └── web.bicep
│       ↓
└── Python App (via backend.config)
    └── app.py
```

## Validation

### Shell Script Validation

```bash
# Test configuration loading
source scripts/load_config.sh

# Check loaded values
echo "Completion deployment: $AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME"
echo "Chat deployment: $AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
```

### Python Validation

```bash
# Run config validation
cd src/app
python -m backend.config

# Output will show:
# - Loaded configuration
# - Validation results
```

## Troubleshooting

### Issue: "Config file not found"

**Solution:** Ensure `config.yml` exists in the project root:
```bash
cp config.example.yml config.yml
```

### Issue: "Neither yq nor python3 found"

**Solution:** Install Python 3 or yq:
```bash
# Install Python 3
sudo apt-get install python3 python3-yaml

# OR install yq
sudo snap install yq
```

### Issue: "Configuration validation failed"

**Solution:** Check that required environment variables are set:
```bash
# Check if variables are set
env | grep AZURE_OPENAI
env | grep AZURE_SEARCH

# Set missing variables
export AZURE_OPENAI_ENDPOINT="..."
```

### Issue: Deployment names mismatch

**Solution:** Update `config.yml` to match your Azure OpenAI deployment names:
1. Go to Azure Portal → Azure OpenAI Studio
2. Check your deployment names under "Deployments"
3. Update `config.yml` accordingly:
   ```yaml
   azure_openai:
     completion_deployment:
       name: "your-actual-deployment-name"
     chat_deployment:
       name: "your-actual-chat-deployment-name"
   ```

## Best Practices

1. **Never commit `config.yml`** - It's already in `.gitignore`
2. **Keep `config.example.yml` updated** - When adding new config options
3. **Use environment variables for secrets** - Don't put API keys in config.yml
4. **Validate after changes** - Run validation scripts after modifying config
5. **Document new settings** - Add comments explaining purpose of new config values

## Migration from Old Setup

If you have an existing deployment:

1. **Back up current settings:**
   ```bash
   # Save current environment variables
   env | grep AZURE_ > backup.env
   ```

2. **Create config.yml:**
   ```bash
   cp config.example.yml config.yml
   ```

3. **Update config.yml with your values:**
   - Check Azure Portal for actual deployment names
   - Update all deployment names in config.yml
   - Review and update other settings

4. **Test locally first:**
   ```bash
   source scripts/get_service_env.sh
   cd src/app
   python app.py
   ```

5. **Deploy when ready:**
   ```bash
   azd up
   ```

## Support

For issues or questions:
- Check [GitHub Issues](https://github.com/your-repo/issues)
- Review logs: `azd logs` or application logs
- Validate configuration: `python -m backend.config`
