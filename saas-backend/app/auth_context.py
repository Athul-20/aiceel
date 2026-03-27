from __future__ import annotations

from dataclasses import dataclass

from app.models import ApiKey, User, Workspace


@dataclass
class AuthContext:
    user: User
    auth_mode: str
    workspace: Workspace | None = None
    role: str | None = None
    api_key_record: ApiKey | None = None
    scopes: set[str] | None = None

