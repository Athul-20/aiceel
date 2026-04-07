# Security Endpoint Split

This note documents the split between AICCEL text PII masking and Sentinel Shield so product behavior, API integration, and usage analytics all refer to the same feature boundaries.

## What Changed

The old shared text-security endpoint was:

- `POST /v1/engine/security/process`

That route mixed two product features behind one public API surface:

- PII Masking
- Sentinel Shield

The backend now exposes separate public endpoints:

- `POST /v1/pii/mask`
- `POST /v1/sentinel/analyze`

The old shared route has now been removed from the public API surface. Only the split routes above are supported.

## Module To Endpoint Mapping

- `PII Masking (text)` -> `POST /v1/pii/mask`
- `Sentinel Shield` -> `POST /v1/sentinel/analyze`
- `PII Masking (PDF)` -> `POST /v1/engine/security/pdf/mask`
- `Pandora Vault Encrypt` -> `POST /v1/engine/security/vault/encrypt`
- `Pandora Vault Decrypt` -> `POST /v1/engine/security/vault/decrypt`

## Metering / Usage Labels

Usage analytics now distinguishes the text features by product-facing labels:

- `pii.masking`
- `sentinel.shield`

Historical rows recorded before the removal may still appear as:

- `engine.security`

On the Usage page:

- the graph legend shows friendly names such as `PII Masking` and `Sentinel Shield`
- the hover tooltip shows the concrete endpoint path used for that series
- generic request rows for these split security endpoints are suppressed so the chart does not show duplicate transport-level lines

## Why This Split Is Better

- clearer API docs for integrators
- cleaner usage analytics and billing visibility
- better product-to-endpoint alignment
- safer future schema evolution for each feature

## Migration Guidance

For new client code:

- use `POST /v1/pii/mask` for privacy masking/tokenization
- use `POST /v1/sentinel/analyze` for prompt-injection and adversarial prompt analysis

For older client code that previously used `POST /v1/engine/security/process`:

- requests will now fail because that route has been removed
- update those clients to `POST /v1/pii/mask` or `POST /v1/sentinel/analyze`
- historical analytics may still show earlier `engine.security` rows because they were already written before the route removal
