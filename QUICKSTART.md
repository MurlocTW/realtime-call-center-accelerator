# Quick Start Guide - Unified Configuration

## 🚀 3 Steps to Deploy

### Step 1: Create Your Config File

```bash
cp config.example.yml config.yml
```

### Step 2: Edit config.yml

Open `config.yml` and update these key values:

```yaml
environment:
  service_name: "app"  # Your service name (3-12 chars, lowercase)

azure_openai:
  completion_deployment:
    name: "gpt-4o-realtime-preview"  # Match your Azure OpenAI deployment
  chat_deployment:
    name: "gpt-4.1"  # Match your Azure OpenAI deployment
```

### Step 3: Deploy

```bash
azd up
```

That's it! ✅

## 📝 What Changed

### Before (Old Way)
```bash
# Had to remember and type arguments every time
./azd-hooks/deploy.sh app dev

# Deployment names hardcoded in multiple files:
# - deploy.sh: "gpt-4.1"
# - web.bicep: "gpt-4.1", "gpt-4o-realtime-preview"
# - get_service_env.sh: "gpt-4.1", "gpt-4o-realtime-preview"
# - app.py: fallback "gpt-4.1"
```

### After (New Way)
```bash
# Everything in config.yml
azd up  # That's it!

# All values come from single source: config.yml
```

## 🔧 Configuration Overview

### Minimal config.yml:
```yaml
environment:
  service_name: "app"  # REQUIRED: Your service name

azure_openai:
  completion_deployment:
    name: "gpt-4o-realtime-preview"  # REQUIRED: For audio
  chat_deployment:
    name: "gpt-4.1"  # REQUIRED: For text chat
```

### Environment variables (set during deployment or dev):
```bash
export AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com/"
export AZURE_OPENAI_API_KEY="your-key"  # Optional if using managed identity
export AZURE_SEARCH_ENDPOINT="https://your-search.search.windows.net"
export AZURE_SEARCH_API_KEY="your-key"
export AZURE_STORAGE_CONNECTION_STRING="your-connection-string"
export ACS_CONNECTION_STRING="your-acs-connection"
```

## 💡 Common Tasks

### Local Development
```bash
# Set up environment
source scripts/get_service_env.sh

# Run app
cd src/app
python app.py
```

### Validate Configuration
```bash
# Test shell config loading
source scripts/load_config.sh
echo "Service: $SERVICE_NAME"
echo "Chat: $AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
echo "Completion: $AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME"

# Test Python config
cd src/app
python -m backend.config
```

### Update Deployment Names
```bash
# Just edit config.yml
nano config.yml

# Update the deployment names
azure_openai:
  completion_deployment:
    name: "your-new-realtime-deployment"
  chat_deployment:
    name: "your-new-chat-deployment"

# Redeploy
azd up
```

## ⚙️ Key Features

| Feature | Benefit |
|---------|---------|
| ✅ Single config file | No more hunting for hardcoded values |
| ✅ Service name in config | No need to type arguments every time |
| ✅ Environment overrides | Can override any config with env vars |
| ✅ Type-safe Python | Config loader provides type safety |
| ✅ Validation | Auto-validates required settings |
| ✅ Backward compatible | Old command-line args still work |

## 🎯 Service Name Rules

Your `environment.service_name` must be:
- **3-12 characters** long
- **Lowercase** letters only (a-z)
- **Numbers** allowed (0-9)
- **No special characters**

Valid examples:
- ✅ `app`
- ✅ `callcenter`
- ✅ `voice2024`

Invalid examples:
- ❌ `App` (uppercase)
- ❌ `my-app` (hyphen)
- ❌ `ab` (too short)
- ❌ `verylongservicename` (too long)

## 📚 More Information

- **[CONFIG.md](CONFIG.md)** - Complete configuration guide
- **[CONFIGURATION_CHANGES.md](CONFIGURATION_CHANGES.md)** - Migration guide
- **[config.example.yml](config.example.yml)** - Full config reference

## ❓ Troubleshooting

### "No service name provided"
**Solution:** Set `environment.service_name` in config.yml
```yaml
environment:
  service_name: "app"
```

### "Deployment not found"
**Solution:** Check your Azure OpenAI Studio for actual deployment names and update config.yml

### "Config file not found"
**Solution:** Create config.yml from example
```bash
cp config.example.yml config.yml
```

### Want to use old command-line arguments?
Still works! Config takes precedence, but you can override:
```bash
./azd-hooks/deploy.sh myservice myenv
```

## 🎉 Benefits Summary

**Before:**
- ❌ Had to type service name every time
- ❌ Deployment names hardcoded in 5+ places
- ❌ Easy to have mismatches
- ❌ Hard to maintain

**After:**
- ✅ Set once in config.yml
- ✅ Single source of truth
- ✅ No more manual arguments
- ✅ Easy to maintain and update

---

**Need help?** Check [CONFIG.md](CONFIG.md) for detailed documentation!
