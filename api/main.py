"""
Main FastAPI application entry point.
Configures CORS, authentication, error envelopes, route mounting, and static frontend serving.
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure codebase is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_DIR = PROJECT_ROOT / "codebase"
for p in (str(PROJECT_ROOT), str(CODEBASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import db, worker
from api.runtime import ensure_js_runtime_on_path, check_js_runtime
from api.routes.health import router as health_router
from api.routes.config import router as config_router
from api.routes.uploads import router as uploads_router
from api.routes.jobs import router as jobs_router
from api.routes.media import router as media_router
from api.routes.imports import router as imports_router
from api.routes.cookies import router as cookies_router

import hashlib
import logging
import time
from pydantic import BaseModel

logger = logging.getLogger(__name__)

APP_ENV = os.environ.get("APP_ENV", "local")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD")
API_TOKEN = os.environ.get("API_TOKEN")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN")
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

# In-memory sliding window rate limiter
_rate_limits: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX_REQUESTS = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db.init_db()
    ensure_js_runtime_on_path()
    check_js_runtime()

    # Auto-seed pre-processed demo match if not present
    demo_job_dir = PROJECT_ROOT / "data" / "jobs" / "demo-match"
    if not (demo_job_dir / "windows.json").exists() or not db.get_job("demo-match"):
        try:
            from tools.seed_demo_job import setup_demo_job
            setup_demo_job()
        except Exception as e:
            logger.warning("Could not auto-seed demo match: %s", e)

    queue_task = asyncio.create_task(worker.queue_manager_loop())
    yield
    # Shutdown
    queue_task.cancel()
    try:
        await queue_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Football Highlight Generator API",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS configuration
if CORS_ORIGIN:
    origins = [o.strip() for o in CORS_ORIGIN.split(",") if o.strip()]
else:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rate Limiting Middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/uploads") or path.startswith("/api/jobs"):
        if request.method in ("POST", "PUT"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            timestamps = _rate_limits.setdefault(client_ip, [])
            _rate_limits[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
            if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Please slow down.",
                        }
                    },
                )
            _rate_limits[client_ip].append(now)
    return await call_next(request)


# Auth & Demo Password Middleware
@app.middleware("http")
async def check_auth_and_demo(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)

    # Public endpoints
    if path in ("/api/health", "/api/sample/clip", "/api/demo/auth"):
        return await call_next(request)

    # 1. Check DEMO_PASSWORD gate if configured
    if DEMO_PASSWORD:
        expected_cookie = hashlib.sha256(f"demo_session_{DEMO_PASSWORD}".encode()).hexdigest()
        cookie_val = request.cookies.get("demo_session")
        auth_header = request.headers.get("Authorization", "")
        has_token = API_TOKEN and auth_header.startswith("Bearer ") and auth_header[7:].strip() == API_TOKEN
        if cookie_val != expected_cookie and not has_token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "code": "DEMO_AUTH_REQUIRED",
                        "message": "Demo password required to access this instance",
                    }
                },
            )

    # 2. Check Bearer Token Auth if API_TOKEN configured
    if API_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:].strip() != API_TOKEN:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid or missing Bearer token",
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


# Standard Error Shape Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error_body = detail
    else:
        error_body = {
            "code": "HTTP_ERROR",
            "message": str(detail),
        }
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_body},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder
    raw_errors = exc.errors()
    first_msg = raw_errors[0]["msg"] if raw_errors else "Validation error"
    safe_errors = jsonable_encoder(raw_errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": first_msg,
                "detail": safe_errors,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
            }
        },
    )


# Mount API routers
app.include_router(health_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(imports_router, prefix="/api")
app.include_router(cookies_router, prefix="/api")


class DemoAuthPayload(BaseModel):
    password: str


@app.post("/api/demo/auth")
async def demo_auth(payload: DemoAuthPayload, response: Response):
    """Authenticate with optional DEMO_PASSWORD."""
    expected = os.environ.get("DEMO_PASSWORD")
    if not expected:
        return {"ok": True, "authenticated": True, "message": "No password configured"}
    if payload.password != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_PASSWORD", "message": "Incorrect password"},
        )
    session_hash = hashlib.sha256(f"demo_session_{expected}".encode()).hexdigest()
    response.set_cookie(
        key="demo_session",
        value=session_hash,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400 * 7,
    )
    return {"ok": True, "authenticated": True}


@app.get("/api/sample/clip")
async def get_sample_clip():
    """Serve short synthetic sample match clip (<= 3 MB) for quick testing."""
    candidates = [
        PROJECT_ROOT / "raw videos" / "short_match_60s.mp4",
        PROJECT_ROOT / "data" / "demo" / "source.mp4",
        PROJECT_ROOT / "data" / "demo" / "synthetic_match.mp4",
        Path("/app/demo_assets/source.mp4"),
        Path("/app/demo_assets/synthetic_match.mp4"),
        PROJECT_ROOT / "demo_assets" / "synthetic_match.mp4",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return FileResponse(
                candidate,
                media_type="video/mp4",
                filename="sample_match.mp4",
            )
    raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "Sample clip not found"})


# Serve Frontend in Production
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or ".." in full_path or full_path.startswith("."):
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found"})
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
