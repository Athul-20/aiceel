# AICCEL Cloud API Examples

## Auth
```bash
curl -X POST http://127.0.0.1:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"StrongPass123!"}'
```

## Create API Key
```bash
curl -X POST http://127.0.0.1:8000/v1/api-keys \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: create-key-001" \
  -d '{"name":"Production Key","scopes":["engine.workflow","providers.write","usage.read"]}'
```

## Configure Provider Key
```bash
curl -X PUT http://127.0.0.1:8000/v1/providers/openai \
  -H "X-API-Key: <AICCEL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-live-..."}'
```

## Run End-to-End Workflow
```bash
curl -X POST http://127.0.0.1:8000/v1/engine/workflows/agent-run \
  -H "X-API-Key: <AICCEL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "objective":"Ship agentic onboarding",
    "prompt":"Build secure rollout plan with auditability",
    "service_slug":"secure-playground",
    "provider":"openai",
    "model":"gpt-4o-mini"
  }'
```

## Usage and Quotas
```bash
curl -X GET http://127.0.0.1:8000/v1/usage/summary -H "X-API-Key: <AICCEL_API_KEY>"
curl -X GET http://127.0.0.1:8000/v1/quotas/status -H "X-API-Key: <AICCEL_API_KEY>"
```

## Webhooks
```bash
curl -X POST http://127.0.0.1:8000/v1/webhooks \
  -H "X-API-Key: <AICCEL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "url":"https://example.com/webhooks/aiccel",
    "secret":"my-webhook-secret",
    "event_types":["workflow.completed","workflow.failed","quota.near_limit","key.revoked"]
  }'
```

## Standardized Error Envelope
```json
{
  "detail": "API key missing required scope 'engine.workflow'",
  "error": {
    "code": "http_error",
    "message": "API key missing required scope 'engine.workflow'",
    "request_id": "req_1a2b3c4d"
  }
}
```

