from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class AICCELClient:
    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 30.0

    def _request(self, method: str, path: str, *, headers: dict | None = None, json: dict | None = None):
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.request(method, path, headers=headers, json=json)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    def register(self, email: str, password: str) -> dict:
        return self._request("POST", "/v1/auth/register", json={"email": email, "password": password})

    def login(self, email: str, password: str) -> dict:
        return self._request("POST", "/v1/auth/login", json={"email": email, "password": password})

    def create_api_key(self, bearer_token: str, name: str, scopes: list[str] | None = None) -> dict:
        payload = {"name": name}
        if scopes is not None:
            payload["scopes"] = scopes
        return self._request("POST", "/v1/api-keys", headers={"Authorization": f"Bearer {bearer_token}"}, json=payload)

    def list_services(self) -> list[dict]:
        return self._request("GET", "/v1/services")

    def upsert_provider_key(self, api_key: str, provider: str, provider_api_key: str) -> dict:
        return self._request(
            "PUT",
            f"/v1/providers/{provider}",
            headers={"X-API-Key": api_key},
            json={"api_key": provider_api_key},
        )

    def run_workflow(self, api_key: str, payload: dict) -> dict:
        return self._request(
            "POST",
            "/v1/engine/workflows/agent-run",
            headers={"X-API-Key": api_key},
            json=payload,
        )

