"""Health check endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from phone_agent.config import get_settings
from phone_agent.db.session import get_db_context
from phone_agent.ai.status import get_model_registry


router = APIRouter()


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    status: str
    message: str | None = None
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str
    device_id: str
    environment: str
    checks: dict[str, Any]


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    checks: dict[str, str]


@router.get("/health")
async def health_check() -> HealthResponse:
    """Perform health check.

    Returns basic health status and component checks.
    Components checked:
    - API: Always ok if reachable
    - Database: Connectivity test via SELECT 1
    - AI Models: STT/LLM/TTS load status
    - Telephony: SIP/FreeSWITCH connection status
    """
    settings = get_settings()

    # Perform component checks
    checks: dict[str, Any] = {
        "api": "ok",
        "database": await _check_database(),
        "ai_models": await _check_ai_models(),
        "telephony": await _check_telephony(),
    }

    # Determine overall status
    status = _determine_overall_status(checks)

    return HealthResponse(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="0.1.0",
        device_id=settings.device_id,
        environment=settings.environment,
        checks=checks,
    )


@router.get("/ready")
async def readiness_check() -> ReadinessResponse:
    """Check if the service is ready to accept traffic.

    Ready means:
    - Database is connected
    - Core services are initialized
    - Telephony is configured (if enabled)
    """
    checks: dict[str, str] = {}

    # Check database
    db_status = await _check_database()
    checks["database"] = db_status if isinstance(db_status, str) else db_status.get("status", "error")

    # Check telephony configuration
    settings = get_settings()
    if settings.telephony.enabled:
        tel_status = await _check_telephony()
        checks["telephony"] = tel_status if isinstance(tel_status, str) else tel_status.get("status", "error")

        # Telephony should be at least configured for ready
        if checks["telephony"] in ("not_configured", "error"):
            return ReadinessResponse(status="not_ready", checks=checks)
    else:
        checks["telephony"] = "disabled"

    # Ready if database is ok
    if checks["database"] == "ok":
        return ReadinessResponse(status="ready", checks=checks)
    else:
        return ReadinessResponse(status="not_ready", checks=checks)


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    """Check if the service is alive.

    Simple check that the process is running and can respond.
    """
    return {"status": "alive"}


@router.get("/health/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """Get detailed health information.

    Returns comprehensive status including:
    - AI model details
    - Database connection pool stats
    - Telephony connection details
    """
    settings = get_settings()

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "device_id": settings.device_id,
        "environment": settings.environment,
        "components": {
            "database": await _get_database_details(),
            "ai_models": await _get_ai_model_details(),
            "telephony": await _get_telephony_details(),
        },
    }


async def _check_database() -> str | dict[str, Any]:
    """Check database connectivity.

    Executes SELECT 1 to verify connection.

    Returns:
        "ok" if connected, error details otherwise
    """
    try:
        async with get_db_context() as db:
            result = await db.execute(text("SELECT 1"))
            result.fetchone()
        return "ok"
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


async def _check_ai_models() -> str | dict[str, Any]:
    """Check if AI models are loaded.

    Returns overall status of STT/LLM/TTS models.
    """
    try:
        registry = get_model_registry()
        overall = registry.get_overall_status()

        if overall == "ok":
            return "ok"
        elif overall == "partial":
            # Get which models are loaded
            status = registry.get_detailed_status()
            loaded = [
                name for name, info in status["models"].items()
                if info["status"] == "loaded"
            ]
            return {
                "status": "partial",
                "loaded": loaded,
            }
        elif overall == "error":
            return {
                "status": "error",
                "message": "One or more models failed to load",
            }
        else:
            return "not_loaded"
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


async def _check_telephony() -> str | dict[str, Any]:
    """Check telephony status.

    Returns:
        "ok" - SIP registered or FreeSWITCH connected
        "disabled" - Telephony not enabled
        "not_configured" - Enabled but not configured
        "error" - Connection failed
    """
    settings = get_settings()

    if not settings.telephony.enabled:
        return "disabled"

    # Check SIP configuration
    if settings.telephony.sip.server:
        try:
            from phone_agent.dependencies import get_sip_client
            sip_client = get_sip_client()
            if sip_client is not None:
                # Check registration status
                if hasattr(sip_client, 'is_registered') and sip_client.is_registered:
                    return "ok"
                else:
                    return {
                        "status": "not_registered",
                        "server": settings.telephony.sip.server,
                    }
        except Exception as e:
            return {
                "status": "error",
                "backend": "sip",
                "message": str(e),
            }

    # Check FreeSWITCH configuration
    if settings.telephony.freeswitch.enabled:
        try:
            from phone_agent.dependencies import get_freeswitch_client
            fs_client = get_freeswitch_client()
            if fs_client is not None:
                if hasattr(fs_client, 'is_connected') and fs_client.is_connected:
                    return "ok"
                else:
                    return {
                        "status": "not_connected",
                        "host": settings.telephony.freeswitch.host,
                    }
        except Exception as e:
            return {
                "status": "error",
                "backend": "freeswitch",
                "message": str(e),
            }

    # Check Twilio configuration
    if settings.telephony.twilio.enabled:
        if settings.telephony.twilio.account_sid:
            return {
                "status": "configured",
                "backend": "twilio",
            }

    # Check sipgate configuration
    if settings.telephony.sipgate.enabled:
        if settings.telephony.sipgate.username:
            return {
                "status": "configured",
                "backend": "sipgate",
            }

    return "not_configured"


def _determine_overall_status(checks: dict[str, Any]) -> str:
    """Determine overall health status from component checks.

    Args:
        checks: Dictionary of component statuses

    Returns:
        "healthy" - All components ok
        "degraded" - Some components have issues
        "unhealthy" - Critical components failed
    """
    # Extract status strings
    statuses = []
    for value in checks.values():
        if isinstance(value, str):
            statuses.append(value)
        elif isinstance(value, dict):
            statuses.append(value.get("status", "error"))
        else:
            statuses.append("unknown")

    # Check for critical failures
    critical_components = ["database"]
    for component in critical_components:
        if component in checks:
            status = checks[component]
            if isinstance(status, dict) and status.get("status") == "error":
                return "unhealthy"
            elif status == "error":
                return "unhealthy"

    # Check if all are ok
    if all(s == "ok" for s in statuses):
        return "healthy"

    # Check for any errors
    if any(s == "error" for s in statuses):
        return "degraded"

    # Some components not fully operational
    return "degraded"


async def _get_database_details() -> dict[str, Any]:
    """Get detailed database information."""
    try:
        from phone_agent.db.session import get_engine

        engine = get_engine()
        pool = engine.pool

        return {
            "status": "ok",
            "driver": str(engine.url.drivername),
            "pool": {
                "size": pool.size() if hasattr(pool, 'size') else None,
                "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else None,
                "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else None,
                "overflow": pool.overflow() if hasattr(pool, 'overflow') else None,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


async def _get_ai_model_details() -> dict[str, Any]:
    """Get detailed AI model information."""
    try:
        registry = get_model_registry()
        return registry.get_detailed_status()
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


async def _get_telephony_details() -> dict[str, Any]:
    """Get detailed telephony information."""
    settings = get_settings()

    details: dict[str, Any] = {
        "enabled": settings.telephony.enabled,
    }

    if not settings.telephony.enabled:
        return details

    # SIP details
    if settings.telephony.sip.server:
        details["sip"] = {
            "server": settings.telephony.sip.server,
            "port": settings.telephony.sip.port,
            "username": settings.telephony.sip.username[:3] + "***" if settings.telephony.sip.username else None,
        }

    # FreeSWITCH details
    if settings.telephony.freeswitch.enabled:
        details["freeswitch"] = {
            "host": settings.telephony.freeswitch.host,
            "port": settings.telephony.freeswitch.port,
        }

    # Twilio details
    if settings.telephony.twilio.enabled:
        details["twilio"] = {
            "configured": bool(settings.telephony.twilio.account_sid),
            "from_number": settings.telephony.twilio.from_number or None,
        }

    # sipgate details
    if settings.telephony.sipgate.enabled:
        details["sipgate"] = {
            "configured": bool(settings.telephony.sipgate.username),
            "caller_id": settings.telephony.sipgate.caller_id or None,
        }

    return details
