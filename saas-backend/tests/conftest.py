from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aiccel_saas.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-1234567890")
os.environ.setdefault("PROVIDER_MOCK_FALLBACK", "true")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
