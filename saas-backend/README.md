# AICCEL Cloud Backend (FastAPI)

Production-ready API-first SaaS backend for AICCEL capabilities (runtime, cognitive planning, security pipeline, orchestration, observability, integrations, agent studio, swarm, playground, and provider dispatch).

## Stack
- FastAPI + SQLAlchemy + Alembic
- Postgres (recommended) / SQLite (quick local)
- Redis (rate limiting + queue backend)
- RQ worker queue (async workflow jobs)

## Embedded AICCEL Framework
- The full `aiccel` framework is vendored directly inside backend at `apps/saas-backend/aiccel`.
- Backend runtime uses this embedded package, so backend deployments do not depend on a separate top-level `aiccel` package.
- Example: Pandora execution now uses embedded `aiccel.sandbox.SandboxExecutor`.

## Core SaaS Controls Implemented
- Multi-tenant model: organizations, workspaces, membership roles
- RBAC: `owner`, `admin`, `developer`, `viewer`
- API key scopes + per-key rate/quota overrides
- Plan-tier usage quotas + billing-style metering events
- Audit logs for auth/key/provider/platform/workflow actions
- Webhooks: `workflow.completed`, `workflow.failed`, `quota.near_limit`, `key.revoked`
- Idempotency keys for mutating endpoints (`Idempotency-Key` header)
- Correlation IDs (`X-Request-ID`) + structured request logs
- Standardized error envelope with backward-compatible `detail`
- JWT access + refresh strategy
- Brute-force protection for auth
- Provider secret encryption at rest

## Local Development
```bash
cd apps/saas-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### SQLite quick start
```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Postgres + Redis recommended
Set these in `.env`:
```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/aiccel
REDIS_URL=redis://localhost:6379/0
```
Then:
```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Run worker (for async workflows + webhook deliveries):
```bash
rq worker aiccel-jobs
```

## Migrations
```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

## Seed Demo Data
```bash
python scripts/seed_demo_data.py
```

## Tests
```bash
pytest -q
```

## API Docs
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Examples: [`docs/API_EXAMPLES.md`](docs/API_EXAMPLES.md)

## Minimal SDK
- Python client: [`sdk/python/aiccel_client.py`](sdk/python/aiccel_client.py)

## Changelog (This Upgrade)
- Added multi-tenant workspace/org schema and RBAC support.
- Added usage analytics, quota status, webhook management, and audit log APIs.
- Added idempotency, request correlation IDs, structured logs, and standardized errors.
- Added RQ async workflow job endpoint support.
- Added Alembic migration scaffolding and initial schema migration.
- Added CI-ready pytest coverage for auth, tenancy isolation, scopes, security, and workflow endpoints.
