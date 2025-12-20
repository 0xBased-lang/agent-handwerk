"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from itf_shared import setup_logging, get_logger
from itf_shared.remote import HeartbeatClient
from itf_shared.models import Industry

from phone_agent.config import get_settings
from phone_agent.api import (
    health,
    calls,
    appointments,
    webhooks,
    sms_webhooks,
    email_webhooks,
    triage,
    recall,
    outbound,
    analytics,
    crm,
    web_audio,
    compliance,
    handwerk_demo,
    handwerk,
    websocket_analytics,
    chat_websocket,
    jobs,
    elektro,
)
from phone_agent.api import tenant_api, email_api
from phone_agent.db import init_db, close_db
from phone_agent.services.campaign_scheduler import CampaignScheduler, SchedulerConfig
from phone_agent.api.rate_limits import limiter
from phone_agent.industry.gesundheit.compliance import (
    start_audit_persistence,
    stop_audit_persistence,
)
from phone_agent.services.data_retention import (
    start_retention_scheduler,
    stop_retention_scheduler,
)
from phone_agent.api.websocket_analytics import (
    start_websocket_broadcasts,
    stop_websocket_broadcasts,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "detail": str(exc.detail),
        },
    )


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with structured response.

    Provides consistent error format across all HTTP errors.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _status_code_to_error_type(exc.status_code),
            "message": str(exc.detail),
            "status_code": exc.status_code,
        },
    )


def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors with detailed field information.

    Provides structured error response for Pydantic validation failures.
    """
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({
            "field": field or "request",
            "message": error["msg"],
            "type": error["type"],
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": errors,
        },
    )


def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions.

    Logs the error and returns a generic 500 response without exposing
    internal details in production.
    """
    log = get_logger(__name__)
    log.error(
        "Unhandled exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )

    settings = get_settings()
    detail = str(exc) if settings.debug else "An internal error occurred"

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": detail,
        },
    )


def _status_code_to_error_type(status_code: int) -> str:
    """Map HTTP status codes to error type strings."""
    error_types = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        410: "gone",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        502: "bad_gateway",
        503: "service_unavailable",
        504: "gateway_timeout",
    }
    return error_types.get(status_code, "error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    log = get_logger(__name__)

    # Setup logging
    setup_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        device_id=settings.device_id,
    )

    log.info(
        "Starting Phone Agent",
        version="0.1.0",
        environment=settings.environment,
        device_id=settings.device_id,
    )

    # Initialize database
    log.info("Initializing database")
    await init_db()
    log.info("Database initialized successfully")

    # Start DSGVO audit persistence (CRITICAL for compliance)
    log.info("Starting DSGVO audit persistence")
    await start_audit_persistence()
    log.info("DSGVO audit persistence started")

    # Start data retention scheduler (DSGVO cleanup at 3 AM daily)
    retention_enabled = getattr(settings, "data_retention_enabled", True)
    if retention_enabled:
        log.info("Starting data retention scheduler")
        await start_retention_scheduler(run_at_hour=3)
        log.info("Data retention scheduler started (runs at 3 AM daily)")

    # Start WebSocket broadcast loops for real-time dashboard
    log.info("Starting WebSocket broadcast loops")
    await start_websocket_broadcasts()
    log.info("WebSocket broadcasts started")

    # Start heartbeat client
    heartbeat: HeartbeatClient | None = None
    if settings.remote_enabled:
        # Get industry from settings (defaults to GESUNDHEIT for backward compatibility)
        industry_name = getattr(settings, "industry", {})
        if isinstance(industry_name, dict):
            industry_name = industry_name.get("name", "gesundheit")
        elif hasattr(industry_name, "name"):
            industry_name = industry_name.name
        else:
            industry_name = "gesundheit"

        # Map industry name to Industry enum
        # Note: GASTRO enum value is "gastronomie_hotellerie" but config uses "gastro"
        industry_map = {
            "gesundheit": Industry.GESUNDHEIT,
            "handwerk": Industry.HANDWERK,
            "gastro": Industry.GASTRO,
            "gastronomie_hotellerie": Industry.GASTRO,
            "freie_berufe": Industry.FREIE_BERUFE,
        }
        industry_enum = industry_map.get(industry_name, Industry.GESUNDHEIT)

        heartbeat = HeartbeatClient(
            device_id=settings.device_id,
            product="phone-agent",
            industry=industry_enum,
            endpoint=settings.heartbeat_endpoint,
            interval=settings.heartbeat_interval,
        )
        await heartbeat.start()

    # Start campaign scheduler for recall campaigns
    scheduler: CampaignScheduler | None = None
    if getattr(settings, "campaign_scheduler_enabled", True):
        scheduler_config = SchedulerConfig(
            poll_interval_seconds=getattr(settings, "campaign_poll_interval", 60),
            max_concurrent_calls=getattr(settings, "max_concurrent_calls", 5),
        )
        scheduler = CampaignScheduler(config=scheduler_config)
        await scheduler.start()
        log.info("Campaign scheduler started")

    # Initialize AI models (configurable preloading)
    preload_models = getattr(settings, "preload_ai_models", False)
    if preload_models:
        log.info("Preloading AI models...")
        try:
            from phone_agent.dependencies import get_stt, get_llm, get_tts
            from phone_agent.ai.status import get_model_registry, ModelStatus

            registry = get_model_registry()

            # Preload STT
            try:
                registry.update_status("stt", ModelStatus.LOADING)
                stt = get_stt()
                stt.load()
                registry.register_stt(stt)
                log.info("STT model preloaded")
            except Exception as e:
                registry.update_status("stt", ModelStatus.ERROR, str(e))
                log.error("Failed to preload STT model", error=str(e))

            # Preload LLM
            try:
                registry.update_status("llm", ModelStatus.LOADING)
                llm = get_llm()
                llm.load()
                registry.register_llm(llm)
                log.info("LLM model preloaded")
            except Exception as e:
                registry.update_status("llm", ModelStatus.ERROR, str(e))
                log.error("Failed to preload LLM model", error=str(e))

            # Preload TTS
            try:
                registry.update_status("tts", ModelStatus.LOADING)
                tts = get_tts()
                tts.load()
                registry.register_tts(tts)
                log.info("TTS model preloaded")
            except Exception as e:
                registry.update_status("tts", ModelStatus.ERROR, str(e))
                log.error("Failed to preload TTS model", error=str(e))

            log.info("AI model preloading complete", status=registry.get_overall_status())

        except Exception as e:
            log.error("AI model preloading failed", error=str(e))
    else:
        log.info("AI models will be loaded on first request (lazy loading)")

    yield

    # Shutdown
    log.info("Shutting down Phone Agent")
    if scheduler:
        await scheduler.stop()
        log.info("Campaign scheduler stopped")

    if heartbeat:
        await heartbeat.stop()

    # Stop WebSocket broadcasts
    log.info("Stopping WebSocket broadcasts")
    await stop_websocket_broadcasts()
    log.info("WebSocket broadcasts stopped")

    # Stop data retention scheduler
    log.info("Stopping data retention scheduler")
    await stop_retention_scheduler()
    log.info("Data retention scheduler stopped")

    # Stop DSGVO audit persistence (flush remaining logs)
    log.info("Stopping DSGVO audit persistence")
    await stop_audit_persistence()
    log.info("DSGVO audit persistence stopped")

    # Close database connections
    await close_db()
    log.info("Database connections closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="IT-Friends Phone Agent",
        description="AI-powered telephone system for German SME automation",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Rate limiting
    app.state.limiter = limiter

    # Exception handlers (order matters - most specific first)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # CORS middleware
    # Note: Cannot use wildcard origins with credentials, so in debug mode
    # we specify common localhost origins explicitly
    cors_origins = (
        [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ]
        if settings.debug
        else []
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(calls.router, prefix="/api/v1", tags=["Calls"])
    app.include_router(appointments.router, prefix="/api/v1", tags=["Appointments"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["Webhooks"])
    app.include_router(sms_webhooks.router, prefix="/api/v1/webhooks", tags=["SMS Webhooks"])
    app.include_router(email_webhooks.router, prefix="/api/v1", tags=["Email Webhooks"])
    app.include_router(triage.router, prefix="/api/v1", tags=["Triage"])
    app.include_router(recall.router, prefix="/api/v1", tags=["Recall Campaigns"])
    app.include_router(outbound.router, prefix="/api/v1", tags=["Outbound Calling"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
    app.include_router(crm.router, prefix="/api/v1", tags=["CRM"])
    app.include_router(web_audio.router, prefix="/api/v1", tags=["Web Audio"])
    app.include_router(compliance.router, prefix="/api/v1", tags=["Compliance"])
    app.include_router(handwerk_demo.router, tags=["Handwerk Demo"])
    app.include_router(handwerk.router, prefix="/api/v1", tags=["Handwerk"])
    app.include_router(elektro.router, prefix="/api/v1", tags=["Elektro-Betrieb"])
    app.include_router(websocket_analytics.router, prefix="/api/v1/ws", tags=["WebSocket Analytics"])
    app.include_router(chat_websocket.router, prefix="/api/v1", tags=["Chat"])
    app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs"])
    app.include_router(tenant_api.router, prefix="/api/v1", tags=["Multi-Tenant"])
    app.include_router(email_api.router, prefix="/api/v1", tags=["Email Agent"])

    # Mount static files for browser testing
    # Try multiple paths: production Docker path first, then local development paths
    log = get_logger(__name__)
    static_dir = None
    possible_paths = [
        Path("/app/static"),  # Production Docker
        Path(__file__).parent.parent.parent.parent / "static",  # Local: solutions/phone-agent/static
        Path.cwd() / "static",  # Current working directory
        Path.cwd() / "solutions/phone-agent/static",  # From project root
    ]

    for path in possible_paths:
        if path.exists() and path.is_dir():
            static_dir = path
            break

    if static_dir:
        log.info(f"Mounting static files from {static_dir}")
        try:
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
            log.info("Static files mounted successfully")
        except Exception as e:
            log.error(f"Failed to mount static files: {e}")
    else:
        log.warning(f"No static directory found in any of: {[str(p) for p in possible_paths]}")

    return app


# Create application instance
app = create_app()


def run() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "phone_agent.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
