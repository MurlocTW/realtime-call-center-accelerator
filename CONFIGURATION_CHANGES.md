# Configuration System Changes - Migration Guide

## 🎯 Overview

The project has been migrated to a **unified configuration management system** using `config.yml`. This eliminates hardcoded values and provides a single source of truth for all configuration.

## ⚡ Quick Start

### For New Users

```bash
# 1. Copy example configuration
cp config.example.yml config.yml

# 2. Edit config.yml with your deployment names and service name
nano config.yml  # or your preferred editor
# Update:
#   - environment.service_name (e.g., "app")
#   - azure_openai.completion_deployment.name
#   - azure_openai.chat_deployment.name

# 3. Deploy (no need to pass arguments anymore!)
azd up
```

### For Existing Users (Migration)

```bash
# 1. Create your config.yml from example
cp config.example.yml config.yml

# 2. Update config.yml with your existing deployment names
# Check your Azure Portal for actual deployment names and update:
#   - azure_openai.completion_deployment.name
#   - azure_openai.chat_deployment.name
#   - azure_search.index.name

# 3. Test locally first
source scripts/get_service_env.sh
cd src/app && python app.py

# 4. Deploy when ready
azd up
```

## 📋 What Changed

### New Files

| File | Purpose |
|------|---------|
| `config.yml` | Main configuration file (you create this) |
| `config.example.yml` | Example configuration template |
| `scripts/load_config.sh` | Shell script configuration loader |
| `src/app/backend/config.py` | Python configuration loader |
| `CONFIG.md` | Complete configuration documentation |

### Modified Files

| File | Changes |
|------|---------|
| `azd-hooks/deploy.sh` | Now loads from config.yml, passes params to bicep |
| `scripts/get_service_env.sh` | Uses config.yml for default values |
| `infra/main.bicep` | Added chat deployment parameters |
| `infra/main.parameters.json` | Added chat deployment parameters |
| `infra/core/app/web.bicep` | Uses parameters instead of hardcoded values |
| `src/app/app.py` | Uses config loader instead of direct env vars |
| `.gitignore` | Added config.yml to prevent committing secrets |

## 🔧 Breaking Changes

### 1. Deployment Names Must Match Config

Previously, deployment names were hardcoded in multiple places:
- `deploy.sh` had `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4.1"`
- `web.bicep` had hardcoded `"gpt-4o-realtime-preview"`
- `get_service_env.sh` had both hardcoded

**Now:** All deployment names come from `config.yml`. You must:
1. Create `config.yml` from `config.example.yml`
2. Update deployment names to match your Azure OpenAI deployments
3. Deploy will fail if config.yml is missing

### 2. New Required File: config.yml

**Action Required:**
```bash
cp config.example.yml config.yml
# Edit config.yml with your values, including service_name
```

### 3. Service Name Now in Config

Previously, you had to pass service name as command line argument:
```bash
# Old way
./azd-hooks/deploy.sh app dev
```

**Now:** Set `environment.service_name` in config.yml:
```yaml
environment:
  service_name: "app"  # 3-12 chars, lowercase alphanumeric
```

Then just run:
```bash
azd up  # No arguments needed!
```

### 4. Environment Variables Still Work

Environment variables **override** config.yml values, so your existing `.env` files still work:
```bash
# This will override config.yml
export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="my-custom-deployment"
```

## ✅ Benefits

### Before (Old System)

```bash
# Hardcoded in deploy.sh
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4.1"

# Hardcoded in web.bicep
value: 'gpt-4.1'

# Hardcoded in get_service_env.sh
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4.1"

# Hardcoded in app.py
chat_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4.1")
```

**Problems:**
- ❌ Same value in 4+ places
- ❌ Easy to have mismatches
- ❌ Hard to update
- ❌ Deployment names mixed with code

### After (New System)

```yaml
# config.yml (single source of truth)
azure_openai:
  chat_deployment:
    name: "gpt-4.1"
```

**Benefits:**
- ✅ Single source of truth
- ✅ No mismatches possible
- ✅ Easy to update (one place)
- ✅ Configuration separate from code
- ✅ Type-safe in Python
- ✅ Environment variable overrides supported

## 📦 What Was Removed/Replaced

### Hardcoded Values Replaced

| Old Location | Old Value | New Location |
|--------------|-----------|--------------|
| `deploy.sh:56` | `"gpt-4.1"` | `config.yml: azure_openai.chat_deployment.name` |
| `web.bicep:64` | `"gpt-4o-realtime-preview"` | `config.yml: azure_openai.completion_deployment.name` |
| `web.bicep:68` | `"gpt-4.1"` | `config.yml: azure_openai.chat_deployment.name` |
| `web.bicep:72` | `"2024-12-17"` | `config.yml: azure_openai.api_version` |
| `get_service_env.sh:5` | `"gpt-4o-realtime-preview"` | `config.yml: azure_openai.completion_deployment.name` |
| `get_service_env.sh:6` | `"gpt-4.1"` | `config.yml: azure_openai.chat_deployment.name` |
| `get_service_env.sh:9` | `"voicerag-intvect"` | `config.yml: azure_search.index.name` |
| `get_service_env.sh:10` | `"default"` | `config.yml: azure_search.index.semantic_configuration` |
| `app.py:51` | `"gpt-4.1"` (fallback) | `config.yml: azure_openai.chat_deployment.name` |

## 🚨 Common Issues & Solutions

### Issue 1: Deployment Fails - Config Not Found

**Error:**
```
Error: Config file not found at /path/to/config.yml
```

**Solution:**
```bash
cp config.example.yml config.yml
# Edit config.yml with your values
```

### Issue 2: Deployment Names Don't Match

**Error:**
```
DeploymentNotFound: The API deployment for this resource does not exist
```

**Solution:**
1. Check your Azure OpenAI Studio for actual deployment names
2. Update `config.yml`:
   ```yaml
   azure_openai:
     completion_deployment:
       name: "your-actual-realtime-deployment"
     chat_deployment:
       name: "your-actual-chat-deployment"
   ```

### Issue 3: Local Development Not Working

**Solution:**
```bash
# Ensure .env is set up
source scripts/get_service_env.sh

# Or manually set required vars
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_API_KEY="..."
export AZURE_SEARCH_ENDPOINT="https://..."
export AZURE_SEARCH_API_KEY="..."
```

## 🔍 Testing Your Configuration

### 1. Test Shell Configuration

```bash
source scripts/load_config.sh
echo "Chat deployment: $AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
echo "Completion deployment: $AZURE_OPENAI_COMPLETION_DEPLOYMENT_NAME"
echo "Search index: $AZURE_SEARCH_INDEX"
```

### 2. Test Python Configuration

```bash
cd src/app
python -m backend.config

# Should show:
# Config(
#   OpenAI: deployment=gpt-4o-realtime-preview, chat=gpt-4.1
#   Search: index=voicerag-intvect
#   ...
# )
# Validation: ✓ Passed
```

### 3. Test Deployment (Dry Run)

```bash
# Check what would be deployed
azd provision --what-if
```

## 📚 Documentation

For complete documentation, see:
- **[CONFIG.md](CONFIG.md)** - Complete configuration guide
- **[config.example.yml](config.example.yml)** - Example with all options
- **[README.md](README.md)** - General project documentation

## 🤝 Need Help?

1. Check [CONFIG.md](CONFIG.md) for detailed documentation
2. Run validation: `python -m backend.config`
3. Check Azure Portal for correct deployment names
4. Review logs: `azd logs` or application logs
5. Open an issue on GitHub

## 📝 Checklist for Migration

- [ ] Copy `config.example.yml` to `config.yml`
- [ ] Update OpenAI deployment names in `config.yml`
- [ ] Update search index name if different
- [ ] Test locally: `source scripts/get_service_env.sh`
- [ ] Test Python config: `python -m backend.config`
- [ ] Deploy: `azd up`
- [ ] Verify deployment works
- [ ] Update your documentation if you have custom setup

## 🎉 Done!

Your configuration is now centralized and easier to manage. All hardcoded values have been eliminated, and you have a single source of truth for all settings.
