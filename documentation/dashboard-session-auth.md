# Dashboard Session Authentication

## Summary

The AICCEL dashboard now uses bearer/session authentication for logged-in UI actions instead of requiring a browser-stored raw API key.

This applies to in-app feature flows such as:

- Playground
- PII Masking
- BioMed Masking
- Pandora Data Lab
- Pandora Vault
- Sandbox Lab
- Agent Builder
- Swarm
- Console
- Provider, usage, webhook, and workspace operations

API keys still exist, but they are now intended for:

- External API consumers
- Scripts and CLIs
- CI jobs
- Server-to-server integrations

## Why This Change Was Made

The previous model required the frontend dashboard to keep a raw API key in local storage. That caused several issues:

- Logged-in users could still see "activate API key" blockers
- Browser-local state could drift from backend truth
- Revoked or stale keys created confusing UI states
- Raw reusable secrets were exposed to browser storage

Using the authenticated session for dashboard actions gives a cleaner SaaS experience and removes the dashboard's dependency on a locally stored API key.

## How It Works

### Frontend

After login, the frontend sends:

- `Authorization: Bearer <access_token>`
- `X-Workspace-ID: <workspace_id>` when a workspace is selected

The dashboard feature client now builds requests from session auth instead of injecting `X-API-Key` for normal in-app usage.

### Backend

Feature routes still depend on `get_user_from_api_key`, but that dependency now supports both auth modes:

1. If a bearer token is present, the backend resolves the user and workspace from the session.
2. If no bearer token is present, it falls back to `X-API-Key`.

This keeps existing external API-key clients working while allowing the dashboard to operate with standard session auth.

## Billing And Usage

Billing does not depend on API keys.

Usage is still recorded against the resolved workspace, and may optionally include the user and API key metadata when available.

Recommended billing model:

- Auth determines who is allowed to perform the action
- Workspace determines who pays for the action

That means the platform can:

- Bill dashboard usage authenticated by bearer/session
- Bill external usage authenticated by API key
- Deduct credits from the same workspace balance in both cases

## Product Behavior After This Change

### Dashboard

- Logged-in users can use dashboard features without activating a local API key
- Dashboard readiness reflects the authenticated session
- The API Keys screen explains that keys are for external use

### External API Usage

- API keys remain valid for direct API calls
- Newly created keys are only shown once
- Stored database records continue to keep hashed key material only

## Security Notes

- Raw API keys are no longer required for standard dashboard activity
- API keys should continue to be treated as long-lived external credentials
- The backend should remain the source of truth for workspace membership, RBAC, metering, and billing

## Files Updated

- `saas-backend/app/deps.py`
- `saas-backend/app/routers/security.py`
- `saas-frontend/src/api.js`
- `saas-frontend/src/context/AppContext.jsx`
- `saas-frontend/src/components/Settings.jsx`
- dashboard feature components that previously required a local API key
