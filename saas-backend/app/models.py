from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspaces: Mapped[list["Workspace"]] = relationship("Workspace", back_populates="organization")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    plan_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="workspaces")
    members: Mapped[list["WorkspaceMember"]] = relationship("WorkspaceMember", back_populates="workspace")
    users_default: Mapped[list["User"]] = relationship("User", back_populates="default_workspace")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    default_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    default_workspace: Mapped["Workspace | None"] = relationship("Workspace", back_populates="users_default")
    memberships: Mapped[list["WorkspaceMember"]] = relationship("WorkspaceMember", back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="owner")

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="owner")
    agents: Mapped[list["AgentProfile"]] = relationship("AgentProfile", back_populates="owner")
    provider_credentials: Mapped[list["ProviderCredential"]] = relationship(
        "ProviderCredential",
        back_populates="owner",
    )
    platform_config: Mapped["PlatformConfig | None"] = relationship(
        "PlatformConfig",
        back_populates="owner",
        uselist=False,
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="memberships")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    owner: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    scopes_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_quota_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="api_keys")


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="assistant")
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="gpt-4o-mini")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools_csv: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    owner: Mapped["User"] = relationship("User", back_populates="agents")


class PlatformConfig(Base):
    __tablename__ = "platform_configs"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_platform_config_workspace"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    runtime_json: Mapped[str] = mapped_column(Text, nullable=False)
    cognitive_json: Mapped[str] = mapped_column(Text, nullable=False)
    security_json: Mapped[str] = mapped_column(Text, nullable=False)
    orchestration_json: Mapped[str] = mapped_column(Text, nullable=False)
    observability_json: Mapped[str] = mapped_column(Text, nullable=False)
    integrations_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    owner: Mapped["User"] = relationship("User", back_populates="platform_config")


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_provider_credentials_workspace_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    owner: Mapped["User"] = relationship("User", back_populates="provider_credentials")


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("workspace_id", "period_start", "period_type", name="uq_usage_counter_workspace_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="month")
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class MeterEvent(Base):
    __tablename__ = "meter_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)
    feature: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(250), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    event_types_csv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("webhook_endpoints.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class IdempotencyKeyRecord(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", "method", "path", name="uq_idempotency_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
