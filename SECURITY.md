# Security Model

## Overview

Local Agent Studio is designed as a **local development tool** that binds to `0.0.0.0` for convenience in containerized and cloud development environments. When deployed in network-accessible environments, administrative operations require authentication.

## Authentication

### API Key Protection

Administrative operations that modify global configuration require an API key when the `API_KEY` environment variable is set:

- `POST /providers` - Create or update provider profiles
- `DELETE /providers/{provider_id}` - Delete custom provider profiles

**Configuration:**

```bash
# Set a strong API key (recommended for network-exposed deployments)
export API_KEY="your-secure-random-key-here"
```

**Usage:**

When `API_KEY` is configured, clients must include the `X-API-Key` header:

```bash
curl -X POST http://localhost:8001/providers \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secure-random-key-here" \
  -d '{"name": "My Provider", ...}'
```

### Local Development Mode

When `API_KEY` is **not set** (empty string or unset), the API operates in local development mode:
- No authentication is required for provider management
- Suitable for localhost-only development
- **Not recommended** for network-exposed deployments

### Read-Only Operations

The following operations are always available without authentication:
- `GET /providers` - List provider profiles
- `GET /providers/{provider_id}/models` - Discover provider models
- `POST /providers/detect` - Probe provider capabilities (read-only)

These operations do not modify state and are safe for unauthenticated access.

## Next.js Proxy

The Next.js frontend (`app/api/providers/*`) automatically forwards the `API_KEY` from its environment to the FastAPI backend. Configure the same `API_KEY` value in both environments:

```bash
# In your .env or deployment configuration
API_KEY=your-secure-random-key-here
BACKEND_URL=http://127.0.0.1:8001
```

## Threat Model

### Protected Against

1. **Unauthenticated provider tampering**: When `API_KEY` is set, network clients cannot create, modify, or delete provider profiles without the correct key.

2. **Provider poisoning**: Attackers cannot inject malicious provider configurations that redirect model traffic or expose credentials.

3. **Timing attacks**: API key comparison uses constant-time comparison (`secrets.compare_digest`) to prevent timing-based key extraction.

### Out of Scope

1. **CSRF protection**: Not implemented. The API is designed for server-to-server communication and programmatic access, not browser-based forms. The CORS policy restricts browser origins to localhost.

2. **Rate limiting**: Not implemented. Deploy behind a reverse proxy (nginx, Caddy) with rate limiting if needed.

3. **User-level authorization**: The API does not support multiple users or per-user provider profiles. All authenticated operations have full administrative access.

4. **TLS/HTTPS**: The FastAPI backend does not provide TLS. Deploy behind a reverse proxy with TLS termination for production use.

## Deployment Recommendations

### Local Development
```bash
# No API key needed
bun run dev
```

### Network-Exposed Deployment
```bash
# Generate a strong API key
export API_KEY=$(openssl rand -base64 32)

# Start with authentication enabled
bun run dev
```

### Production Deployment
1. Set a strong `API_KEY` (32+ random bytes)
2. Deploy behind a reverse proxy with:
   - TLS termination
   - Rate limiting
   - IP allowlisting (if applicable)
3. Restrict FastAPI bind address if possible:
   ```bash
   # Bind only to localhost if reverse proxy is on same host
   uvicorn python_backend.main:app --host 127.0.0.1 --port 8001
   ```

## Security Considerations

### Provider Configuration Risks

Provider profiles control:
- **Outbound URLs**: Where model requests are sent
- **Authorization headers**: Environment variable references for API keys
- **Custom scripts**: Deno adapters with network access

A compromised provider profile could:
- Redirect model traffic to attacker-controlled servers
- Expose API keys through malicious URLs
- Execute malicious code via custom script adapters

**Mitigation**: Enable `API_KEY` authentication for any deployment where untrusted network clients can reach the FastAPI port.

### Environment Variable Security

The `API_KEY` is read from the environment at startup. Ensure:
- The key is not logged or exposed in error messages
- The key is not committed to version control
- The key is rotated periodically
- The key is stored securely (e.g., secrets manager, encrypted environment)

## Reporting Security Issues

If you discover a security vulnerability, please report it privately to the maintainers. Do not open a public issue.
