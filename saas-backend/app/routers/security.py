from fastapi import APIRouter, Depends

from app.deps import get_user_from_api_key
from app.models import User
from app.schemas import SecurityFeature, SecurityFeaturesResponse


router = APIRouter(prefix="/v1/security", tags=["security"])


@router.get("/features", response_model=SecurityFeaturesResponse)
def list_security_features(
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
) -> SecurityFeaturesResponse:
    _, auth_mode = user_auth
    return SecurityFeaturesResponse(
        auth_mode=auth_mode,
        api_key_required=True,
        features=[
            SecurityFeature(
                name="API-Key Gate",
                description="Platform setup, orchestration, and playground endpoints require X-API-Key.",
            ),
            SecurityFeature(
                name="Neural Privacy Engine",
                description="Regex scanning with GLiNER-style semantic entity recognition and reversible tokenization controls.",
            ),
            SecurityFeature(
                name="Adversarial Input Defense",
                description="Hybrid prompt-injection gating using heuristics plus optional HF jailbreak classification with fail-closed behavior.",
            ),
            SecurityFeature(
                name="Cryptographic Vault",
                description="AES-256-GCM mode with PBKDF2-HMAC-SHA256 key derivation settings.",
            ),
            SecurityFeature(
                name="Sandboxed Code Execution",
                description="Isolated execution with resource controls for memory-sensitive operations.",
            ),
        ],
        how_to_use=[
            "1) Login and create an AICCEL API key.",
            "2) Paste key into the dashboard API key slot.",
            "3) Configure each subsystem tab with your preferred policy values.",
            "4) Send requests with header: X-API-Key: <your_key>.",
            "5) Validate behavior in the unified secure playground.",
        ],
    )
