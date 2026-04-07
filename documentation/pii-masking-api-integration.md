# AICCEL PII Masking API Integration Guide

This document describes the existing PII masking API in this codebase so another implementation agent can integrate it into a separate application without reverse-engineering the backend.

It is based on the current backend routes and schemas in:

- [engine.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/routers/engine.py)
- [pdf_masking.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/routers/pdf_masking.py)
- [deps.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/deps.py)
- [schemas.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/schemas.py)
- [engine_core.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/engine_core.py)
- [privacy.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/aiccel/privacy.py)

## 1. What Exists Today

There are three closely related security API paths:

1. Text PII masking:
   - `POST /v1/pii/mask`
2. Sentinel Shield text analysis:
   - `POST /v1/sentinel/analyze`
3. PDF masking:
   - `POST /v1/engine/security/pdf/mask`

Related support endpoints:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `GET /v1/api-keys`
- `POST /v1/api-keys`
- `DELETE /v1/api-keys/{id}`
- `GET /v1/security/features`
- `GET /health`

## 2. Authentication Model

The security routes use a shared dependency that accepts either:

- `Authorization: Bearer <access_token>`
- `X-API-Key: <raw_api_key>`

This is implemented in [deps.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/deps.py).

### Which auth mode to use

For a separate external application, the recommended mode is:

- `X-API-Key`

Use bearer auth only if the external app is acting on behalf of an already signed-in user and you control the full login/session flow.

### Optional workspace scoping

The backend also supports:

- `X-Workspace-ID: <integer>`

This is optional. In API-key mode, the workspace is usually resolved from the key record itself.

## 3. Base URL

In local development, the frontend currently points to:

```text
http://127.0.0.1:8000
```

So the full URLs are typically:

- `http://127.0.0.1:8000/v1/pii/mask`
- `http://127.0.0.1:8000/v1/sentinel/analyze`
- `http://127.0.0.1:8000/v1/engine/security/pdf/mask`

## 4. Quick Start For Another App

### Option A: API key flow

1. Sign in with bearer auth.
2. Create an API key.
3. Store the raw API key securely in the external app backend or secret store.
4. Call PII endpoints with `X-API-Key`.

### Option B: Bearer/session flow

1. Register or log in.
2. Store `access_token` and `refresh_token`.
3. Call PII endpoints with `Authorization: Bearer <access_token>`.
4. Refresh when needed.

For external system integration, Option A is simpler and more stable.

## 5. Auth Endpoints

### 5.1 Register

`POST /v1/auth/register`

Request:

```json
{
  "email": "user@company.com",
  "password": "SecurePassword123!"
}
```

Response shape:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt_...",
  "user": {
    "id": 1,
    "email": "user@company.com"
  }
}
```

### 5.2 Login

`POST /v1/auth/login`

Request:

```json
{
  "email": "user@company.com",
  "password": "SecurePassword123!"
}
```

Response shape:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt_...",
  "user": {
    "id": 1,
    "email": "user@company.com",
    "default_workspace_id": 1
  }
}
```

### 5.3 Refresh

`POST /v1/auth/refresh`

Request:

```json
{
  "refresh_token": "rt_..."
}
```

## 6. API Key Endpoints

These routes require bearer auth, not API key auth.

### 6.1 List API keys

`GET /v1/api-keys`

Headers:

- `Authorization: Bearer <access_token>`
- optional `X-Workspace-ID: <id>`

### 6.2 Create API key

`POST /v1/api-keys`

Headers:

- `Authorization: Bearer <access_token>`
- `Content-Type: application/json`

Request:

```json
{
  "name": "Production Key"
}
```

Response:

```json
{
  "api_key": "ak_live_xxxxxxxxxxxx",
  "key": {
    "id": 1,
    "name": "Production Key",
    "workspace_id": 1,
    "key_prefix": "ak_live_xxxx",
    "scopes": ["engine.security", "usage.read"],
    "rate_limit_per_minute": null,
    "monthly_quota_units": null,
    "is_active": true,
    "created_at": "2026-04-02T10:00:00Z",
    "last_used_at": null
  }
}
```

Important:

- The raw `api_key` is returned only once.
- Save it immediately in a secure secret store.

### 6.3 Revoke API key

`DELETE /v1/api-keys/{id}`

Headers:

- `Authorization: Bearer <access_token>`

## 7. Capability Discovery

### 7.1 Security feature metadata

`GET /v1/security/features`

This returns high-level platform/security metadata and states that security routes accept:

- bearer session auth
- API key auth

Useful if the external app wants to validate feature availability before enabling UI paths.

## 8. Core Text PII Endpoint

### 8.1 Route

`POST /v1/pii/mask`

### 8.2 Purpose

This route processes plain text for:

- PII detection
- masking/tokenization
- risk scoring

### 8.3 Headers

Use one of:

- `X-API-Key: <raw_api_key>`
- `Authorization: Bearer <access_token>`

Also send:

- `Content-Type: application/json`

Optional:

- `X-Workspace-ID: <integer>`

### 8.4 Request body

Current public request schema:

```json
{
  "text": "Contact jane@acme.com or call +1-212-555-0100",
  "reversible": true,
  "token_format": "opaque",
  "remove_email": true,
  "remove_phone": true,
  "remove_person": true,
  "remove_blood_group": true,
  "remove_passport": true,
  "remove_pancard": true,
  "remove_organization": true
}
```

`token_format` supports three values:

- `opaque`
  - current backward-compatible placeholders like `__AICCEL_TOKEN_1__`
- `typed`
  - semantic placeholders like `__AICCEL_EMAIL_1__`
- `masked_readable`
  - partially visible masked values like `jane***e@acme.com`

### 8.5 Response body

All reversible responses now include:

- `token_format`
- `token_map`
- `token_metadata`

#### Opaque format example

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact __AICCEL_TOKEN_1__ or call __AICCEL_TOKEN_2__",
  "tokenized_text": "Contact __AICCEL_TOKEN_1__ or call __AICCEL_TOKEN_2__",
  "token_format": "opaque",
  "token_map": {
    "__AICCEL_TOKEN_1__": "jane@acme.com",
    "__AICCEL_TOKEN_2__": "+1-212-555-0100"
  },
  "token_metadata": {
    "__AICCEL_TOKEN_1__": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "__AICCEL_TOKEN_1__"
    },
    "__AICCEL_TOKEN_2__": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "__AICCEL_TOKEN_2__"
    }
  },
  "generated_at": "2026-04-02T10:47:58.245721Z"
}
```

#### Typed format example

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact __AICCEL_EMAIL_1__ or call __AICCEL_PHONE_1__",
  "tokenized_text": "Contact __AICCEL_EMAIL_1__ or call __AICCEL_PHONE_1__",
  "token_format": "typed",
  "token_map": {
    "__AICCEL_EMAIL_1__": "jane@acme.com",
    "__AICCEL_PHONE_1__": "+1-212-555-0100"
  },
  "token_metadata": {
    "__AICCEL_EMAIL_1__": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "__AICCEL_EMAIL_1__"
    },
    "__AICCEL_PHONE_1__": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "__AICCEL_PHONE_1__"
    }
  },
  "generated_at": "2026-04-02T10:47:58.245721Z"
}
```

#### Masked-readable format example

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact jane***e@acme.com or call +1-***-***-0100",
  "tokenized_text": "Contact jane***e@acme.com or call +1-***-***-0100",
  "token_format": "masked_readable",
  "token_map": {
    "jane***e@acme.com": "jane@acme.com",
    "+1-***-***-0100": "+1-212-555-0100"
  },
  "token_metadata": {
    "jane***e@acme.com": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "jane***e@acme.com"
    },
    "+1-***-***-0100": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "+1-***-***-0100"
    }
  },
  "generated_at": "2026-04-02T10:47:58.245721Z"
}
```

### 8.6 Meaning of key fields

- `blocked`
  - `true` means the backend considered the input unsafe enough to block.
- `risk_score`
  - numeric score for security/privacy risk.
- `detected_markers`
  - list of prompt injection / adversarial markers if found.
- `sensitive_entities`
  - entity summaries safe for UI display.
- `sanitized_text`
  - masked output text you can display or pass to downstream systems.
- `tokenized_text`
  - tokenized output, aligned with `sanitized_text` in this endpoint.
- `token_format`
  - tells the client whether the response used `opaque`, `typed`, or `masked_readable` formatting.
- `token_map`
  - reverse map used for reversible tokenization when `reversible=true`.
- `token_metadata`
  - per-token metadata including entity kind, ordinal index, and typed canonical placeholder.

### 8.7 Important implementation note

The engine core supports more entity toggles internally than the public request schema currently exposes.

Internally supported options include:

- `remove_ssn`
- `remove_card`
- `remove_address`
- `remove_dob`
- `remove_bank_account`

These are handled in [engine_core.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/engine_core.py#L103), but they are not currently declared in the public `EngineSecurityProcessRequest` model in [schemas.py](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/app/schemas.py#L157).

Practical implication:

- Another app should rely on the documented public fields above unless you also extend the backend schema.


## 9. Sentinel Shield Endpoint

### 9.1 Route

`POST /v1/sentinel/analyze`

### 9.2 Purpose

This route analyzes text for prompt-injection, adversarial markers, and instruction-override risk.

### 9.3 Notes

- It uses the same underlying security engine as the legacy shared route.
- New usage analytics label this traffic as `sentinel.shield`.
- New client integrations should call this route instead of the old shared text security endpoint.

## 9. PDF PII Endpoint

### 9.1 Route

`POST /v1/engine/security/pdf/mask`

### 9.2 Purpose

This route:

- accepts a PDF upload
- detects sensitive values using GLiNER + regex + structured extraction
- permanently redacts matching regions
- returns the redacted PDF as binary

### 9.3 Headers

Use one of:

- `X-API-Key: <raw_api_key>`
- `Authorization: Bearer <access_token>`

The request is multipart, so do not manually force JSON content type.

### 9.4 Form-data fields

Required:

- `file`
  - binary PDF upload

Optional:

- `options`
  - JSON string containing masking toggles

Example `options`:

```json
{
  "remove_email": true,
  "remove_phone": true,
  "remove_person": true,
  "remove_blood_group": true,
  "remove_passport": true,
  "remove_pancard": true,
  "remove_organization": true,
  "remove_ssn": true,
  "remove_card": true,
  "remove_address": true,
  "remove_dob": true,
  "remove_bank_account": true
}
```

### 9.5 Response

The response body is:

- `application/pdf`

The route also returns these headers:

- `X-Redacted-Count`
- `X-Entity-Summary`
- `Access-Control-Expose-Headers: X-Redacted-Count, X-Entity-Summary`

Example meaning:

- `X-Redacted-Count: 14`
- `X-Entity-Summary: [{"type":"emails","value":"jane@acme.com","page":1}, ...]`

### 9.6 Constraints

- only `.pdf` files are accepted
- PDF max size is `20 MB`
- encrypted/password-protected PDFs are rejected

## 10. Example Calls

### 10.1 cURL text masking with API key

```bash
curl -X POST "http://127.0.0.1:8000/v1/pii/mask" \
  -H "X-API-Key: ak_live_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Contact jane@acme.com or call +1-212-555-0100\",\"reversible\":true,\"token_format\":\"typed\"}"
```

### 10.2 cURL PDF masking with API key

```bash
curl -X POST "http://127.0.0.1:8000/v1/engine/security/pdf/mask" \
  -H "X-API-Key: ak_live_YOUR_KEY" \
  -F "file=@sample.pdf" \
  -F "options={\"remove_email\":true,\"remove_phone\":true,\"remove_person\":true,\"remove_organization\":true}"
```

### 10.3 JavaScript text example

```js
async function maskText(apiKey, text) {
  const response = await fetch("http://127.0.0.1:8000/v1/pii/mask", {
    method: "POST",
    headers: {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      text,
      reversible: true,
      remove_email: true,
      remove_phone: true,
      remove_person: true,
      remove_blood_group: true,
      remove_passport: true,
      remove_pancard: true,
      remove_organization: true,
      token_format: "typed",
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error?.error?.message || "PII masking failed");
  }

  return response.json();
}
```

### 10.4 JavaScript PDF example

```js
async function maskPdf(apiKey, file) {
  const form = new FormData();
  form.append("file", file);
  form.append(
    "options",
    JSON.stringify({
      remove_email: true,
      remove_phone: true,
      remove_person: true,
      remove_organization: true,
      remove_ssn: true,
      remove_card: true,
      remove_address: true,
      remove_dob: true,
      remove_bank_account: true,
    })
  );

  const response = await fetch("http://127.0.0.1:8000/v1/engine/security/pdf/mask", {
    method: "POST",
    headers: {
      "X-API-Key": apiKey,
    },
    body: form,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error?.error?.message || "PDF masking failed");
  }

  const blob = await response.blob();
  const redactedCount = Number(response.headers.get("X-Redacted-Count") || "0");
  const entitySummaryRaw = response.headers.get("X-Entity-Summary") || "[]";
  const entitySummary = JSON.parse(entitySummaryRaw);

  return { blob, redactedCount, entitySummary };
}
```

### 10.5 Python text example

```python
import requests

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "ak_live_YOUR_KEY"

payload = {
    "text": "Contact jane@acme.com or call +1-212-555-0100",
    "reversible": True,
    "remove_email": True,
    "remove_phone": True,
    "remove_person": True,
    "remove_blood_group": True,
    "remove_passport": True,
    "remove_pancard": True,
    "remove_organization": True,
    "token_format": "masked_readable",
}

response = requests.post(
    f"{BASE_URL}/v1/pii/mask",
    headers={
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=60,
)

response.raise_for_status()
print(response.json())
```

## 11. Expected Error Cases

### Text route

Likely failures:

- `401`
  - missing or invalid bearer/API key
- `403`
  - user/workspace role is too low
- `422`
  - invalid request body shape

### PDF route

Likely failures:

- `400`
  - non-PDF upload
  - invalid PDF
  - encrypted/password-protected PDF
  - file larger than 20 MB
- `401`
  - missing or invalid auth
- `403`
  - insufficient access

## 12. Usage and Metering

These routes generate usage events.

Current meter event labels:

- text masking:
  - `pii.masking`
- Sentinel Shield text analysis:
  - `sentinel.shield`
- legacy shared route:
  - `engine.security` (historical rows written before the shared route was removed)
- PDF masking:
  - `engine.pdf.mask`

So another app can verify integration by calling the endpoint and then checking:

- `GET /v1/usage/events`
- `GET /v1/usage/summary`

## 13. Recommended Integration Architecture

For another application:

1. Keep the raw AICCEL API key on that app's backend only.
2. Do not expose the raw key to the browser if avoidable.
3. Create your own backend proxy/controller for:
   - text masking
   - PDF masking
4. Forward only the necessary fields to AICCEL.
5. Return normalized responses to your own frontend.

This is safer than embedding the AICCEL key directly in client-side code.

## 14. Suggested Handoff To Another Codex

If another Codex instance is going to implement this integration, the task can be framed as:

1. Add a backend service wrapper for `POST /v1/pii/mask`.
2. Add a multipart upload wrapper for `POST /v1/engine/security/pdf/mask`.
3. Store the AICCEL raw API key in server-side secrets/env, not local storage.
4. Surface:
   - masked text
   - entity previews
   - risk score
   - blocked status
   - PDF blob download
   - redacted count
   - entity summary
5. Add error handling for `400`, `401`, `403`, and `422`.
6. If needed, add a setup page for bearer login + API key creation.

## 15. Important Caveats

- The removed shared route `POST /v1/engine/security/process` is no longer available for new integrations.
- The text endpoint currently exposes fewer boolean toggles publicly than the PDF route supports.
- `token_format` defaults to `opaque`, so existing clients remain backward compatible unless they explicitly request `typed` or `masked_readable`.
- `masked_readable` is easier for LLM extraction prompts, but it intentionally reveals partial shape information from the original value.
- Usage timestamps are stored in UTC on the backend; frontend consumers should normalize timezone display explicitly.
- API key creation returns the raw key only once.
- PDF masking returns binary data plus metadata in headers, not JSON.
- Auth currently supports both bearer and API key mode for these security routes.

## 16. Minimal Endpoint Checklist

If the goal is only "integrate existing PII masking into another app", the minimum set is:

- `POST /v1/auth/login`
- `POST /v1/api-keys`
- `POST /v1/pii/mask`
- `POST /v1/engine/security/pdf/mask`

Optional but useful:

- `GET /v1/security/features`
- `GET /v1/usage/events`
- `GET /v1/usage/summary`
- `GET /health`






