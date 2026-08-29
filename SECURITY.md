# Security

## GitHub Sync Endpoint Authentication

The `/api/github/sync` endpoint performs privileged operations (Git push and pull request creation) using server-held credentials. To prevent unauthorized access, this endpoint requires authentication.

### Configuration

Set the `GITHUB_SYNC_SECRET` environment variable to a strong, randomly-generated secret:

```bash
# Generate a secure random secret (example using openssl)
openssl rand -base64 32

# Set the environment variable
export GITHUB_SYNC_SECRET="your-generated-secret-here"
```

### Usage

All requests to `/api/github/sync` must include an `Authorization` header with the secret:

```bash
curl -X POST https://your-domain.com/api/github/sync \
  -H "Authorization: Bearer your-generated-secret-here" \
  -H "Content-Type: application/json" \
  -d '{"action": "check"}'
```

### Actions

The endpoint accepts the following actions via the `action` parameter:

- `check` - Verify configuration without performing any write operations
- `push` - Push the branch to GitHub (no PR creation)
- `all` - Push the branch and create a pull request

Any other value will be rejected with a 400 Bad Request error.

### Error Responses

- `500` - `GITHUB_SYNC_SECRET` is not configured on the server
- `401` - Missing or invalid authorization header
- `400` - Invalid or missing action parameter
- `401` - `GITHUB_TOKEN` is not configured (after authentication succeeds)

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GITHUB_SYNC_SECRET` | Yes | Authentication secret for the sync endpoint |
| `GITHUB_TOKEN` | Yes | GitHub personal access token for repository operations |

## Security Best Practices

1. **Never commit secrets** - Keep `GITHUB_SYNC_SECRET` and `GITHUB_TOKEN` in environment variables only
2. **Use strong secrets** - Generate cryptographically random secrets (minimum 32 bytes)
3. **Rotate regularly** - Change secrets periodically and after any suspected compromise
4. **Limit network exposure** - If possible, restrict network access to the sync endpoint
5. **Monitor usage** - Review logs for unexpected sync operations
