# Security Patch: Custom Provider Management

## Overview

This patch addresses a critical security vulnerability where unauthenticated users could:
1. Create custom provider configurations with arbitrary code execution capabilities
2. Access server environment variables containing API keys and credentials
3. Execute custom Deno scripts with network access
4. Forward credentials to attacker-controlled URLs

## Changes Made

### 1. Configuration Flag (config.py)
- Added `ALLOW_CUSTOM_PROVIDERS` environment variable (default: `false`)
- Custom provider functionality is now disabled by default
- Must be explicitly enabled with `ALLOW_CUSTOM_PROVIDERS=true`

### 2. Provider Management Endpoints (main.py)
- `POST /providers`: Now requires `ALLOW_CUSTOM_PROVIDERS=true`, returns 403 otherwise
- `POST /providers/detect`: Now requires `ALLOW_CUSTOM_PROVIDERS=true`, returns 403 otherwise
- `DELETE /providers/{provider_id}`: Now requires `ALLOW_CUSTOM_PROVIDERS=true`, returns 403 otherwise
- `GET /providers/{provider_id}/models`: Blocks custom providers when disabled

### 3. Orchestration Validation (main.py)
- `provider_problems()` function now validates that providers are builtin when custom providers are disabled
- Prevents execution of custom providers through the `/orchestrate` endpoint

### 4. Runtime Security (provider_runtime.py)
- `list_models()`: Validates provider is builtin or custom providers are enabled
- `chat_stream()`: Validates provider is builtin or custom providers are enabled
- `_headers()`: Only attaches credentials for builtin providers or when explicitly enabled
- `_script_call()`: Blocks execution entirely when custom providers are disabled

## Security Model

### Default Behavior (ALLOW_CUSTOM_PROVIDERS=false)
- Only builtin providers (ollama, openai, groq, fireworks, litellm) can be used
- Custom provider creation/modification/deletion is blocked
- Custom provider execution is blocked
- Credentials are only sent to builtin provider URLs
- Custom Deno scripts cannot be executed

### Enabled Mode (ALLOW_CUSTOM_PROVIDERS=true)
- All provider management endpoints are accessible
- Custom providers can be created and executed
- Credentials can be accessed by custom code
- **WARNING**: This mode allows arbitrary code execution and credential access
- Should only be enabled in trusted, isolated environments

## Migration Guide

### For Users
1. If you only use builtin providers (ollama, openai, groq, fireworks, litellm):
   - No action required, everything continues to work

2. If you have custom providers:
   - Set environment variable: `ALLOW_CUSTOM_PROVIDERS=true`
   - Review your custom provider configurations for security
   - Consider migrating to builtin providers if possible

### For Administrators
1. Review all existing custom providers in your deployment
2. Assess whether custom providers are necessary
3. If custom providers are needed:
   - Ensure the backend runs in an isolated environment
   - Limit network access from the backend
   - Use dedicated, limited-scope credentials
   - Set `ALLOW_CUSTOM_PROVIDERS=true` explicitly

## Threat Model

### Threats Mitigated (Default Configuration)
- ✅ Arbitrary code execution via custom Deno scripts
- ✅ Environment variable exfiltration
- ✅ Credential forwarding to attacker-controlled URLs
- ✅ Unauthorized provider configuration changes
- ✅ Server-side request forgery (SSRF) via custom providers

### Remaining Considerations
- ⚠️ No authentication on API endpoints (relies on network isolation)
- ⚠️ CORS only restricts browser access, not direct API calls
- ⚠️ When custom providers are enabled, all threats return

## Recommendations

1. **Network Isolation**: Deploy the backend on localhost or behind authentication
2. **Principle of Least Privilege**: Use dedicated API keys with minimal scopes
3. **Environment Separation**: Never run with production credentials
4. **Monitoring**: Log all provider management operations
5. **Future Enhancement**: Implement proper authentication/authorization

## Testing

To verify the patch is working:

```bash
# Test 1: Custom provider creation should fail by default
curl -X POST http://localhost:8000/providers \
  -H "Content-Type: application/json" \
  -d '{"name":"test","kind":"custom_script","script":"console.log(1)"}'
# Expected: 403 Forbidden

# Test 2: Builtin providers should still work
curl http://localhost:8000/providers
# Expected: 200 OK with builtin providers listed

# Test 3: Enable custom providers
export ALLOW_CUSTOM_PROVIDERS=true
# Restart backend, then retry Test 1
# Expected: 201 Created
```

## Version Information

- Patch Date: 2024
- Affected Versions: All versions prior to this patch
- Severity: Critical (CVSS 9.8 - Unauthenticated RCE with credential access)
