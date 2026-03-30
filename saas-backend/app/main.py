from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import time
import uuid

from typing import Any, cast
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, get_engine, ensure_sqlite_compat_schema, get_db
from app.routers import (
    agents,
    api_keys,
    audit,
    auth,
    engine as engine_router,
    biomed,
    lab,
    pandora as pandora_router,
    pdf_masking,
    platform,
    playground,
    providers,
    quotas,
    security,
    security_center,
    services,
    swarm,
    usage,
    webhooks,
    workspaces,
)


# ── Logging ───────────────────────────────────────────────
# Configure the parent "aiccel" logger so all sub-loggers 
# (aiccel.api, aiccel.privacy, aiccel.biomed, etc) share this config.
root_logger = logging.getLogger("aiccel")
if not root_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

settings = get_settings()
logger = logging.getLogger("aiccel.api")


# ── Lifespan (replaces deprecated @app.on_event) ──────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler: runs once on startup, yields during the
    application lifetime, and can perform cleanup after shutdown."""
    db_engine = get_engine()
    
    # Robust Database Initialization with Retry Logic
    max_retries = 5
    retry_delay = 2
    for i in range(max_retries):
        try:
            Base.metadata.create_all(bind=db_engine)
            ensure_sqlite_compat_schema()
            logger.info("Database initialized successfully.")
            break
        except Exception as e:
            if i == max_retries - 1:
                logger.critical(f"Final database connection attempt failed: {e}")
                raise
            logger.warning(f"Database connection attempt {i+1} failed ({e}). Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
            
    yield
    # Cleanup logic (if any) goes here
    logger.info("Application shutting down...")


app = FastAPI(title=settings.app_name, lifespan=lifespan)


# ── Error helpers ──────────────────────────────────────────

def _error_response(request: Request, status_code: int, code: str, message: str, details=None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    payload = {
        "detail": message,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


# ── Middleware ─────────────────────────────────────────────

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:24]}"
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": elapsed_ms,
            "status_code": 500,
            "client_ip": request.client.host if request.client else None,
            "event": "request.error",
        }
        logger.exception(json.dumps(log, ensure_ascii=True))
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "duration_ms": elapsed_ms,
        "status_code": response.status_code,
        "client_ip": request.client.host if request.client else None,
        "event": "request.completed",
    }
    logger.info(json.dumps(log, ensure_ascii=True))
    return response


# Keep CORS outermost so browser clients receive CORS headers even when inner handlers fail.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Redacted-Count", "X-Entity-Summary"],
)


# ── Exception handlers ────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    details = exc.detail if isinstance(exc.detail, (dict, list)) else None
    return _error_response(request, exc.status_code, "http_error", detail, details=details)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _error_response(
        request,
        422,
        "validation_error",
        "Input validation failed",
        details=exc.errors(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error", exc_info=exc)
    return _error_response(request, 500, "internal_error", "Internal server error")


# ── Health ─────────────────────────────────────────────────

@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Production grade health check with dependency verification."""
    status = {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    try:
        # Verify database connectivity
        db.execute(text("SELECT 1"))
        status["database"] = "connected"
    except Exception as e:
        status["status"] = "degraded"
        status["database"] = f"error: {str(e)}"
    
    return status


# ── Router registration ───────────────────────────────────

app.include_router(auth.router)
app.include_router(pdf_masking.router)
app.include_router(api_keys.router)
app.include_router(services.router)
app.include_router(agents.router)
app.include_router(swarm.router)
app.include_router(security.router)
app.include_router(security_center.router)
app.include_router(platform.router)
app.include_router(providers.router)
app.include_router(lab.router)
app.include_router(playground.router)
app.include_router(engine_router.router)
app.include_router(pandora_router.router)
app.include_router(usage.router)
app.include_router(quotas.router)
app.include_router(audit.router)
app.include_router(webhooks.router)
app.include_router(biomed.router)
app.include_router(workspaces.router)
