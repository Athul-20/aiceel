# AICCEL SaaS Frontend (React + Vite)

## Run
```bash
cd apps/saas-frontend
npm install
copy .env.example .env
npm run dev -- --host 127.0.0.1 --port 5173
```

App runs at `http://127.0.0.1:5173` and expects backend at `http://127.0.0.1:8000` by default.

## Environment
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Included SaaS Views
- Full-width control center + setup tabs for runtime/cognitive/security/orchestration/observability/integrations
- API key + provider key management
- Agent Studio + Swarm Lab + secure playground + integration lab
- Feature API explorer for all engine endpoints
- Usage analytics + quota status
- Webhook endpoint management + delivery history
- Audit logs
- Workspace administration (create/switch, member roles)
