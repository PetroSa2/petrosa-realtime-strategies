# Manual Deployment Guide

Use the repository's manual deployment workflow when an operator needs to deploy
without a source-code change.

## Before dispatch

- Confirm the target environment and requested semantic-version bump.
- Confirm the deployment credentials and workflow permissions are configured.
- Use the GitHub Actions MCP operations when available; use the GitHub UI or CLI
  only as the documented fallback.

## Dispatch

From the workflow form, provide:

- `environment`: `staging` or `production`.
- `version_bump`: `patch`, `minor`, or `major`.
- `reason`: a concise operational reason.

The equivalent CLI command is:

```bash
gh workflow run manual-deploy.yml \
  -f environment=staging \
  -f version_bump=patch \
  -f reason="Redeploy after configuration change"
```

## Version policy

- `patch`: fixes, configuration changes, security updates, or documentation.
- `minor`: backward-compatible features or new endpoints.
- `major`: breaking API, schema, or required-dependency changes.

The workflow creates the version, builds the image, updates deployment manifests,
applies the deployment, and waits for rollout completion.

## Verify

Inspect the workflow summary and confirm that the target deployment reports a
successful rollout. Then check service health, readiness, metrics, and recent
application logs through the Kubernetes MCP or the platform's normal operator
interface.

If rollout verification fails, stop the release and follow the platform rollback
runbook. Do not bypass branch protection or apply unreviewed manifest changes.
