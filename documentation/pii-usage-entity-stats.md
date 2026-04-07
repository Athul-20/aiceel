# PII Usage Entity Stats

This feature adds aggregate-only entity detection analytics to the Usage page for PII masking activity.

## What It Shows

For PII text masking and PDF masking traffic, the Usage page can now show counts such as:

- Emails detected
- Phones detected
- People detected
- Organizations detected
- Addresses detected
- Passports detected
- PAN cards detected
- Blood groups detected
- SSNs detected
- Cards detected
- Birth dates detected
- Bank accounts detected

These counts are shown for the currently selected Usage scope:

- Workspace
- API
- A selected API key in the API view

They also respect the selected:

- Month
- Year

## Privacy Model

This feature is intentionally aggregate-only.

The backend does not store:

- raw detected values
- original request text
- token maps
- masked-readable output values
- per-entity previews in usage analytics

Instead, each usage event stores only aggregate counts such as:

```json
{
  "entity_counts": {
    "email": 2,
    "phone": 1,
    "person": 3
  },
  "entity_total": 6
}
```

This keeps the Usage page useful without turning the security layer into a sensitive-data log.

## Where It Is Recorded

The aggregate counts are attached only to meter events for:

- `pii.masking`
- `sentinel.shield`
- `engine.pdf.mask`

They are then aggregated in:

- `GET /v1/usage/summary`
- `GET /v1/usage/events`

## Backend Behavior

### Text masking

For `POST /v1/pii/mask` and `POST /v1/sentinel/analyze`:

- the endpoint already knows the detected entity kinds from `sensitive_entities`
- the metering layer now stores only per-kind counts

### PDF masking

For `POST /v1/engine/security/pdf/mask`:

- the endpoint already knows the detected entity types before redaction is written
- the metering layer now stores only per-kind counts derived from those detected types

## Usage Page Behavior

The Usage page now includes a `Detected Entity Stats` section.

It shows aggregate counts for the selected scope and time period and includes a note that no raw sensitive values are stored in analytics.

## API Shape

### Usage summary

`GET /v1/usage/summary` now includes:

```json
{
  "workspace_id": 1,
  "plan_tier": "free",
  "limits": {
    "monthly_units": 5000
  },
  "usage": {
    "request_count": 12,
    "token_count": 0,
    "runtime_ms": 336,
    "unit_count": 36,
    "period_start": "2026-04-01",
    "period_type": "month"
  },
  "entity_counts": {
    "email": 5,
    "phone": 3,
    "person": 2
  }
}
```

### Usage events

`GET /v1/usage/events` now includes per-event aggregate counts:

```json
{
  "id": 101,
  "feature": "pii.masking",
  "units": 3,
  "tokens": 0,
  "runtime_ms": 28,
  "status": "ok",
  "api_key_id": 7,
  "request_id": "req_xxx",
  "entity_counts": {
    "email": 1,
    "phone": 1
  },
  "created_at": "2026-04-07T10:00:00Z"
}
```

## Files Updated

Backend:

- [models.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/models.py)
- [database.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/database.py)
- [metering.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/metering.py)
- [usage.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/routers/usage.py)
- [engine.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/routers/engine.py)
- [pdf_masking.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/routers/pdf_masking.py)
- [schemas.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/schemas.py)

Frontend:

- [Settings.jsx](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-frontend/src/components/Settings.jsx)

Related docs:

- [pii-masking-api-integration.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-integration.md)
- [pii-masking-api-change-log.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-change-log.md)
