# Security

## GitHub Integration Authorization

### Overview

The GitHub integration in this application uses a **repository allowlist** to prevent unauthorized access to GitHub repositories via the server's credentials. This mitigates a confused deputy vulnerability where unauthenticated callers could potentially abuse the server's `GITHUB_TOKEN` to perform operations on arbitrary repositories.

### Configuration

Two environment variables are required for GitHub integration:

1. **`GITHUB_TOKEN`** — Your GitHub personal access token or fine-grained token
2. **`GITHUB_ALLOWED_REPOSITORIES`** — Comma-separated list of authorized repositories

**Example:**
```bash
export GITHUB_TOKEN="ghp_your_token_here"
export GITHUB_ALLOWED_REPOSITORIES="myorg/repo1,myorg/repo2,anotherorg/repo3"
```

### Security Model

#### Authorization Enforcement

- **All GitHub operations** (repository lookup, branch creation, pull request creation) validate the requested repository against the allowlist before making any API calls.
- If `GITHUB_ALLOWED_REPOSITORIES` is empty or unset, **all GitHub operations are rejected** with a clear error message.
- Repository names are compared **case-insensitively** (matching GitHub's behavior).

#### Attack Surface Reduction

The allowlist prevents the following attack scenarios:

1. **Unauthenticated confused deputy attacks**: An attacker cannot use the server's GitHub token to access repositories they control but the server owner doesn't intend to authorize.
2. **Credential abuse**: Even if an attacker can reach the FastAPI or Next.js endpoints (e.g., via direct HTTP requests bypassing CORS), they cannot perform operations on unauthorized repositories.
3. **Lateral movement**: If one repository is compromised, the attacker cannot use the server to access other repositories not in the allowlist.

#### Defense in Depth

This implementation provides multiple layers of protection:

1. **Syntax validation**: Repository names must match the `owner/repository` format
2. **Allowlist authorization**: Only explicitly authorized repositories are accepted
3. **Token validation**: The `GITHUB_TOKEN` must be configured
4. **GitHub API validation**: GitHub's own authorization checks still apply

### Error Messages

The service provides clear, actionable error messages:

- **Empty allowlist**: `"GitHub integration is disabled. Configure GITHUB_ALLOWED_REPOSITORIES to authorize specific repositories."`
- **Unauthorized repository**: `"Repository 'attacker/evil-repo' is not authorized. Contact the administrator to add it to the allowlist."`
- **Missing token**: `"GitHub is not configured. Add GITHUB_TOKEN in the Keys tab."`

### Testing

The test suite (`python_backend/tests/test_github_service.py`) includes comprehensive coverage:

- Allowlist enforcement for authorized and unauthorized repositories
- Case-insensitive repository name matching
- Empty allowlist rejection
- Integration with existing validation (syntax, token, refs, SHAs)

Run tests with:
```bash
bun run test:python
```

### Deployment Considerations

#### Network Binding

The application binds to `0.0.0.0` by default, making it network-reachable. In production deployments:

1. **Always configure** `GITHUB_ALLOWED_REPOSITORIES` before enabling GitHub integration
2. Consider using a **reverse proxy** with authentication (e.g., nginx with basic auth, OAuth2 proxy)
3. Use **firewall rules** to restrict access to trusted networks
4. Consider **fine-grained GitHub tokens** with minimal permissions (read-only for repository info, write for branches/PRs only on specific repositories)

#### Token Permissions

Use GitHub fine-grained personal access tokens with minimal required permissions:

- **Repository metadata**: Read-only access
- **Contents**: Read and write (for branch creation)
- **Pull requests**: Read and write (for PR creation)

Limit token access to only the repositories in your allowlist.

### Migration Guide

If you have an existing deployment without the allowlist:

1. **Identify authorized repositories**: Determine which repositories your application should access
2. **Set the environment variable**:
   ```bash
   export GITHUB_ALLOWED_REPOSITORIES="owner1/repo1,owner2/repo2"
   ```
3. **Restart the application**: The allowlist is loaded at service initialization
4. **Verify**: Test that authorized repositories work and unauthorized ones are rejected

### Reporting Security Issues

If you discover a security vulnerability, please report it privately to the maintainers rather than opening a public issue.
