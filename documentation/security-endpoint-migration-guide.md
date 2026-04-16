# Security Endpoint Migration Guide

## Summary

The old shared security endpoint has been split into dedicated public APIs:

- `POST /v1/pii/mask`
- `POST /v1/sentinel/analyze`

The former shared route:

- `POST /v1/engine/security/process`

has been removed from the current source code and should no longer be used for new integrations.

## What Changed

Before the split, both of these product features used the same public endpoint:

- PII Masking
- Sentinel Shield

That caused a few issues:

- Usage analytics grouped both products under the same internal meter label: `engine.security`
- API docs were harder to understand
- External clients could not tell which feature they were calling from usage data alone
- Product-level reporting was muddy because one route represented two different modules

After the split:

- PII Masking uses `POST /v1/pii/mask`
- Sentinel Shield uses `POST /v1/sentinel/analyze`
- Usage analytics now write feature-specific labels:
  - `pii.masking`
  - `sentinel.shield`

## Current Endpoint Mapping

### PII Masking

- Endpoint: `POST /v1/pii/mask`
- Usage label: `pii.masking`
- Test script: `documentation/test_pii_masking_api.py`

### Sentinel Shield

- Endpoint: `POST /v1/sentinel/analyze`
- Usage label: `sentinel.shield`
- Test script: `documentation/test_sentinel_shield_api.py`

### Sandbox Lab

- Endpoint: `POST /v1/lab/execute`
- Usage label: `lab.execute`
- Test script: `documentation/test_sandbox_api.py`

## Why You May Still See Legacy Usage Labels

You may still see a legacy label in the Usage dashboard:

- `Removed Shared Security Route`

This does **not** mean the old endpoint is still the active path for new calls.

It exists only because historical usage rows from before the split are still stored in the database with the old feature label:

- `engine.security`

The frontend maps that old historical label to a more explicit display name so older records remain understandable.

## Why PII May Not Show In The API Usage Graph

If PII is missing from the API chart while Sentinel or Sandbox appears, the usual reasons are:

1. No new API-key PII calls have been made against `POST /v1/pii/mask` in the selected period.
2. The PII activity you are expecting is older historical traffic that was recorded under the old shared label `engine.security`.
3. The PII action was performed from the logged-in dashboard session instead of the API-key view you are currently filtering on.
4. The chart only shows the busiest recent endpoint series, so sparse activity can drop out if many other endpoints are active.

Important distinction:

- API Usage view shows rows where `api_key_id` is present
- Workspace Usage view shows session/workspace usage where `api_key_id` is absent

So a dashboard PII run can appear in `Workspace` while an external API call appears in `API`.

## Did We Actually Remove The Legacy Endpoint?

Yes, from the current application source, the public shared route was removed.

The current codebase now uses:

- `POST /v1/pii/mask`
- `POST /v1/sentinel/analyze`

The old shared route string still appears in two places intentionally:

1. Usage cleanup logic in `saas-backend/app/routers/usage.py`
   - This suppresses old duplicate request rows such as `request:POST /v1/engine/security/process`
2. Historical label mapping in `saas-frontend/src/components/Settings.jsx`
   - This renders old `engine.security` records as `Removed Shared Security Route`

Those references are for historical analytics cleanup only. They do **not** re-enable the old API.

## If The Old Route Still Appears To Work

If `POST /v1/engine/security/process` still seems to respond in your local environment, the most likely explanation is that your backend process is still running an older build that was started before the route was removed.

In that case:

1. Stop the backend server completely.
2. Start it again from the current codebase.
3. Re-test only these routes:
   - `POST /v1/pii/mask`
   - `POST /v1/sentinel/analyze`

If the server was not restarted, an older in-memory process can continue serving removed routes even though the source code no longer defines them.

## How Legacy Clients Should Migrate

### Old PII Call

```http
POST /v1/engine/security/process
```

### New PII Call

```http
POST /v1/pii/mask
```

### Old Sentinel Call

```http
POST /v1/engine/security/process
```

### New Sentinel Call

```http
POST /v1/sentinel/analyze
```

## Migration Checklist

- Replace any client use of `POST /v1/engine/security/process`
- Update PII integrations to `POST /v1/pii/mask`
- Update Sentinel integrations to `POST /v1/sentinel/analyze`
- Restart backend services after deploying the new code
- Re-run API smoke tests using the updated scripts in `documentation/`
- Verify Usage analytics now show `PII Masking` and `Sentinel Shield` instead of the shared legacy label for new traffic

## Quick Test Commands

### PII

```powershell
$env:AICCEL_API_KEY="your_api_key_here"
python C:\MY_PROJECTS\AICCEL\AICCEL_SAAS\documentation	est_pii_masking_api.py
```

### Sentinel Shield

```powershell
$env:AICCEL_API_KEY="your_api_key_here"
python C:\MY_PROJECTS\AICCEL\AICCEL_SAAS\documentation	est_sentinel_shield_api.py
```

### Sandbox

```powershell
$env:AICCEL_API_KEY="your_api_key_here"
python C:\MY_PROJECTS\AICCEL\AICCEL_SAAS\documentation	est_sandbox_api.py
```

## Practical Recommendation

To confirm the split is working cleanly:

1. Restart the backend
2. Run one fresh API-key PII request
3. Run one fresh API-key Sentinel request
4. Open Usage -> API
5. Use `Last 24H`

At that point, the graph should show new series such as:

- `PII Masking`
- `Sentinel Shield`
- `Sandbox Lab`

Any `Removed Shared Security Route` entry at that point is historical carry-over, not a new call path.
