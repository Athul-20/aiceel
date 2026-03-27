from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserAuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=300)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    default_workspace_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    user: UserOut


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    scopes: list[str] = Field(default_factory=list, max_length=64)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=5000)
    monthly_quota_units: int | None = Field(default=None, ge=100, le=1000000000)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    workspace_id: int | None = None
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int | None = None
    monthly_quota_units: int | None = None
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    key: ApiKeyOut


class ProviderKeyUpsertRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=400)


class ProviderKeyStatus(BaseModel):
    provider: str
    workspace_id: int | None = None
    is_configured: bool
    key_hint: str | None = None
    updated_at: datetime | None = None


class ProviderKeyStatusResponse(BaseModel):
    items: list[ProviderKeyStatus]


class ServiceOut(BaseModel):
    slug: str
    name: str
    description: str
    requires_api_key: bool
    beta: bool = False


class PlaygroundRequest(BaseModel):
    service_slug: str
    agent_id: int | None = None
    prompt: str = Field(min_length=1, max_length=6000)


class RuntimeSetup(BaseModel):
    lazy_proxy_imports: bool = True
    load_on_first_access: bool = True
    max_rss_mb: int = Field(default=512, ge=128, le=8192)
    tffi_target_ms: int = Field(default=120, ge=20, le=15000)


class CognitiveSetup(BaseModel):
    strategy: str = Field(default="react", pattern="^(direct|react|cot)$")
    enforce_json_schema: bool = True
    planner_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    parallel_tool_execution: bool = True


class SecuritySetup(BaseModel):
    regex_scan: bool = True
    semantic_entity_recognition: bool = True
    reversible_tokenization: bool = True
    injection_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    fail_closed: bool = True
    encryption_mode: str = Field(default="aes-256-gcm")
    pbkdf2_iterations: int = Field(default=600000, ge=100000, le=2000000)
    sandbox_enabled: bool = True
    sandbox_memory_mb: int = Field(default=512, ge=64, le=4096)


class OrchestrationSetup(BaseModel):
    semantic_routing: bool = True
    dag_resolution: bool = True
    max_concurrency: int = Field(default=8, ge=1, le=64)
    retry_budget: int = Field(default=2, ge=0, le=10)


class ObservabilitySetup(BaseModel):
    trace_propagation: bool = True
    chain_of_thought_inspection: bool = False
    metrics_sampling_rate: float = Field(default=1.0, ge=0.1, le=1.0)


class IntegrationSetup(BaseModel):
    rest_api: bool = True
    sse_streaming: bool = True
    mcp_interop: bool = True
    webhook_forwarding: bool = False
    webhook_url: str | None = Field(default=None, max_length=1024)


class PlatformSetupResponse(BaseModel):
    runtime: RuntimeSetup
    cognitive: CognitiveSetup
    security: SecuritySetup
    orchestration: OrchestrationSetup
    observability: ObservabilitySetup
    integrations: IntegrationSetup
    updated_at: datetime | None = None


class PlatformFeature(BaseModel):
    subsystem: str
    title: str
    description: str
    capabilities: list[str]


class PlatformFeaturesResponse(BaseModel):
    items: list[PlatformFeature]


class IntegrationLabRequest(BaseModel):
    language: str = Field(pattern="^(python|javascript|js)$")
    code: str = Field(min_length=1, max_length=4000)
    input_text: str | None = Field(default="", max_length=2000)


class IntegrationLabResponse(BaseModel):
    language: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int


class SecurityReport(BaseModel):
    blocked: bool
    prompt_injection_detected: bool
    pii_masked: bool
    risk_score: float = 0.0
    detected_markers: list[str] = Field(default_factory=list)
    sensitive_entities: list[dict[str, str]] = Field(default_factory=list)
    notes: list[str]
    sanitized_prompt: str
    tokenized_prompt: str | None = None
    token_map: dict[str, str] = Field(default_factory=dict)


class PlaygroundResponse(BaseModel):
    service_slug: str
    service_name: str
    agent_name: str | None = None
    output: str
    used_auth: str
    config_snapshot: dict[str, str]
    security_report: SecurityReport
    generated_at: datetime


class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(default="assistant", min_length=2, max_length=80)
    provider: str = Field(default="openai", pattern="^(openai|groq|google)$")
    model: str = Field(default="gpt-4o-mini", min_length=2, max_length=80)
    system_prompt: str = Field(min_length=10, max_length=6000)
    tools: list[str] = Field(default_factory=list, max_length=12)


class AgentOut(BaseModel):
    id: int
    name: str
    role: str
    provider: str
    model: str
    system_prompt: str
    tools: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SwarmRunRequest(BaseModel):
    objective: str = Field(min_length=8, max_length=4000)
    lead_agent_id: int | None = None
    collaborator_agent_ids: list[int] = Field(default_factory=list, max_length=6)


class SwarmRunResponse(BaseModel):
    objective: str
    lead_agent: str
    collaborators: list[str]
    stages: list[str]
    final_output: str
    used_auth: str
    generated_at: datetime


class EngineRuntimeRequest(BaseModel):
    modules: list[str] = Field(default_factory=list, max_length=64)
    access_sequence: list[str] = Field(default_factory=list, max_length=128)


class EngineRuntimeResponse(BaseModel):
    loaded_modules: list[str]
    deferred_modules: list[str]
    lazy_load_events: int
    estimated_tffi_ms: int
    estimated_peak_rss_mb: int
    within_limits: bool
    generated_at: datetime


class EngineCognitivePlanRequest(BaseModel):
    goal: str = Field(min_length=4, max_length=4000)
    context: str | None = Field(default="", max_length=8000)
    tools: list[str] = Field(default_factory=list, max_length=16)


class EngineCognitivePlanResponse(BaseModel):
    strategy: str
    plan_steps: list[str]
    compiled_schema: dict
    planner_temperature: float
    generated_at: datetime


class SensitiveEntity(BaseModel):
    kind: str
    value_preview: str


class EngineSecurityProcessRequest(BaseModel):
    text: str = Field(min_length=1, max_length=16000)
    reversible: bool = True
    remove_email: bool = True
    remove_phone: bool = True
    remove_person: bool = True
    remove_blood_group: bool = True
    remove_passport: bool = True
    remove_pancard: bool = True
    remove_organization: bool = True


class EngineSecurityProcessResponse(BaseModel):
    blocked: bool
    risk_score: float
    detected_markers: list[str]
    sensitive_entities: list[SensitiveEntity]
    sanitized_text: str
    tokenized_text: str
    token_map: dict[str, str]
    generated_at: datetime


class VaultEncryptRequest(BaseModel):
    plaintext: str = Field(min_length=1, max_length=32000)
    passphrase: str = Field(min_length=8, max_length=256)


class VaultEncryptResponse(BaseModel):
    algorithm: str
    encrypted_blob: str
    generated_at: datetime


class VaultDecryptRequest(BaseModel):
    encrypted_blob: str = Field(min_length=1, max_length=64000)
    passphrase: str = Field(min_length=8, max_length=256)


class VaultDecryptResponse(BaseModel):
    plaintext: str
    generated_at: datetime


class OrchestrationTaskAssignment(BaseModel):
    task: str
    assigned_agent: str
    dependency_on: str | None = None
    status: str


class EngineOrchestrationRequest(BaseModel):
    objective: str = Field(min_length=4, max_length=4000)
    lead_agent_id: int | None = None
    collaborator_agent_ids: list[int] = Field(default_factory=list, max_length=8)
    tasks: list[str] = Field(default_factory=list, max_length=24)


class EngineOrchestrationResponse(BaseModel):
    lead_agent: str
    collaborators: list[str]
    assignments: list[OrchestrationTaskAssignment]
    dag_enabled: bool
    semantic_routing: bool
    stages: list[str]
    generated_at: datetime


class TraceSpan(BaseModel):
    name: str
    duration_ms: int


class EngineTraceRequest(BaseModel):
    trace_name: str = Field(min_length=2, max_length=120)
    stages: list[str] = Field(default_factory=list, max_length=48)


class EngineTraceResponse(BaseModel):
    trace_id: str
    sampled: bool
    spans: list[TraceSpan]
    metrics: dict[str, float]
    generated_at: datetime


class LLMDispatchRequest(BaseModel):
    provider: str = Field(pattern="^(openai|groq|google)$")
    model: str = Field(default="gpt-4o-mini", min_length=2, max_length=120)
    prompt: str = Field(min_length=1, max_length=16000)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=1, le=4096)


class LLMDispatchResponse(BaseModel):
    provider: str
    model: str
    mode: str = Field(pattern="^(live|mock)$")
    provider_endpoint: str | None = None
    output: str
    used_key_hint: str
    token_usage: dict[str, int]
    generated_at: datetime


class WorkflowAgentRunRequest(BaseModel):
    objective: str = Field(min_length=8, max_length=4000)
    prompt: str = Field(min_length=1, max_length=16000)
    service_slug: str = Field(default="secure-playground", min_length=2, max_length=120)
    provider: str = Field(default="openai", pattern="^(openai|groq|google)$")
    model: str = Field(default="gpt-4o-mini", min_length=2, max_length=120)
    lead_agent_id: int | None = None
    collaborator_agent_ids: list[int] = Field(default_factory=list, max_length=8)
    runtime_modules: list[str] = Field(default_factory=list, max_length=64)


class WorkflowAgentRunResponse(BaseModel):
    service_slug: str
    security: EngineSecurityProcessResponse
    cognitive: EngineCognitivePlanResponse
    runtime: EngineRuntimeResponse
    orchestration: EngineOrchestrationResponse
    trace: EngineTraceResponse
    llm_dispatch: LLMDispatchResponse
    final_output: str
    used_auth: str
    generated_at: datetime


class WorkflowJobQueuedResponse(BaseModel):
    job_id: str
    status: str
    queued_at: datetime


class WorkflowJobStatusResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: dict | None = None
    error: str | None = None


class IntegrationEndpointSpec(BaseModel):
    name: str
    method: str
    path: str
    description: str
    sample_payload: dict


class EngineIntegrationManifestResponse(BaseModel):
    base_path: str
    endpoints: list[IntegrationEndpointSpec]
    curl_examples: list[str]
    generated_at: datetime


class SecurityFeature(BaseModel):
    name: str
    description: str


class SecurityFeaturesResponse(BaseModel):
    auth_mode: str
    api_key_required: bool
    features: list[SecurityFeature]
    how_to_use: list[str]


class UsageSummaryResponse(BaseModel):
    workspace_id: int
    plan_tier: str
    limits: dict[str, int]
    usage: dict[str, int | str]


class UsageEventOut(BaseModel):
    id: int
    feature: str
    units: int
    tokens: int
    runtime_ms: int
    status: str
    request_id: str | None = None
    created_at: datetime


class QuotaStatusResponse(BaseModel):
    workspace_id: int
    near_limit: bool
    limit_units: int
    used_units: int
    remaining_units: int


class AuditLogOut(BaseModel):
    id: int
    action: str
    target_type: str | None = None
    target_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    created_at: datetime
    metadata: dict = Field(default_factory=dict)


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=8, max_length=1024)
    secret: str = Field(min_length=8, max_length=256)
    event_types: list[str] = Field(default_factory=list, max_length=32)


class WebhookOut(BaseModel):
    id: int
    url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
    last_failure_at: datetime | None = None


class WebhookDeliveryOut(BaseModel):
    id: int
    event_type: str
    status: str
    attempts: int
    response_code: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceOut(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str
    plan_tier: str
    is_active: bool
    role: str
    created_at: datetime
    updated_at: datetime


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)


class WorkspaceMemberCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(owner|admin|developer|viewer)$")


class WorkspaceMemberOut(BaseModel):
    user_id: int
    email: EmailStr
    role: str
    created_at: datetime


class WorkspaceSwitchRequest(BaseModel):
    workspace_id: int = Field(ge=1)

class BiomedMaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=16000)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    labels: list[str] | None = Field(default=None, max_length=20)

class BiomedMaskResponse(BaseModel):
    masked_text: str
    mask_mapping: dict[str, str]
    extracted_entities: dict[str, list[str]]
    generated_at: datetime
