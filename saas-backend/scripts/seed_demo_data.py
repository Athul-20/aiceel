from __future__ import annotations

from app.database import Base, get_engine, get_session_factory
from app.models import AgentProfile, ApiKey, User
from app.security import create_api_key, hash_api_key, hash_password
from app.tenancy import ensure_personal_workspace


def seed() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    db = get_session_factory()()
    try:
        demo_email = "demo@aiccel.dev"
        user = db.query(User).filter(User.email == demo_email).first()
        if user is None:
            user = User(email=demo_email, password_hash=hash_password("DemoPass123!"))
            db.add(user)
            db.commit()
            db.refresh(user)
        workspace = ensure_personal_workspace(db, user)

        existing_key = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active.is_(True)).first()
        if existing_key is None:
            raw_key, key_prefix = create_api_key()
            key = ApiKey(
                user_id=user.id,
                workspace_id=workspace.id,
                name="Demo SDK Key",
                key_prefix=key_prefix,
                key_hash=hash_api_key(raw_key),
                scopes_csv="",
                is_active=True,
            )
            db.add(key)
            db.commit()
            print(f"Created demo API key (save now): {raw_key}")

        existing_agent = db.query(AgentProfile).filter(AgentProfile.user_id == user.id, AgentProfile.is_active.is_(True)).first()
        if existing_agent is None:
            agent = AgentProfile(
                user_id=user.id,
                workspace_id=workspace.id,
                name="Demo Planner",
                role="assistant",
                provider="openai",
                model="gpt-4o-mini",
                system_prompt="Create deterministic, secure rollout plans.",
                tools_csv="search,workflow",
                is_active=True,
            )
            db.add(agent)
            db.commit()

        print("Demo seed complete for demo@aiccel.dev / DemoPass123!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
