"""Real-Time Analytics WebSocket Endpoints.

Provides WebSocket connections for live dashboard updates:
- Real-time KPI streaming
- Live call activity feed
- Circuit breaker status
- System health metrics

Usage:
    ws://host/api/v1/ws/dashboard  - Dashboard KPIs (updates every 5s)
    ws://host/api/v1/ws/calls      - Live call activity feed
    ws://host/api/v1/ws/health     - System health metrics
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Set
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Connection Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for different channels."""

    def __init__(self):
        self._connections: dict[str, Set[WebSocket]] = {
            "dashboard": set(),
            "calls": set(),
            "health": set(),
        }
        self._running = False
        self._broadcast_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = set()
        self._connections[channel].add(websocket)
        logger.info(f"WebSocket connected to {channel}, total: {len(self._connections[channel])}")

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket connection."""
        if channel in self._connections:
            self._connections[channel].discard(websocket)
            logger.info(f"WebSocket disconnected from {channel}, remaining: {len(self._connections[channel])}")

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Broadcast message to all connections in a channel."""
        if channel not in self._connections:
            return

        disconnected = []
        for websocket in self._connections[channel]:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        # Clean up disconnected
        for ws in disconnected:
            self._connections[channel].discard(ws)

    def get_connection_count(self, channel: str) -> int:
        """Get number of active connections for a channel."""
        return len(self._connections.get(channel, set()))

    def start_broadcast_loops(self) -> None:
        """Start background broadcast loops for all channels."""
        if self._running:
            return

        self._running = True
        self._broadcast_tasks["dashboard"] = asyncio.create_task(
            self._dashboard_broadcast_loop()
        )
        self._broadcast_tasks["health"] = asyncio.create_task(
            self._health_broadcast_loop()
        )
        logger.info("WebSocket broadcast loops started")

    async def stop_broadcast_loops(self) -> None:
        """Stop all broadcast loops."""
        self._running = False
        for name, task in self._broadcast_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._broadcast_tasks.clear()
        logger.info("WebSocket broadcast loops stopped")

    async def _dashboard_broadcast_loop(self) -> None:
        """Broadcast dashboard KPIs every 5 seconds."""
        while self._running:
            try:
                if self._connections.get("dashboard"):
                    kpis = await get_dashboard_kpis()
                    await self.broadcast("dashboard", {
                        "type": "kpi_update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": kpis,
                    })
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dashboard broadcast error: {e}")
                await asyncio.sleep(5)

    async def _health_broadcast_loop(self) -> None:
        """Broadcast health metrics every 10 seconds."""
        while self._running:
            try:
                if self._connections.get("health"):
                    health = await get_health_metrics()
                    await self.broadcast("health", {
                        "type": "health_update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": health,
                    })
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health broadcast error: {e}")
                await asyncio.sleep(10)


# Global connection manager
manager = ConnectionManager()


# ============================================================================
# Data Fetching Functions
# ============================================================================

async def get_dashboard_kpis() -> dict[str, Any]:
    """Fetch current dashboard KPIs."""
    try:
        from phone_agent.db.session import get_db_context
        from phone_agent.db.repositories.analytics import AnalyticsService

        async with get_db_context() as session:
            service = AnalyticsService(session)

            # Get today's metrics
            from datetime import date
            today = date.today()

            call_metrics = await service.get_daily_metrics(today)
            weekly_summary = await service.get_weekly_summary(today)

            return {
                "calls": {
                    "today": call_metrics.get("total_calls", 0) if call_metrics else 0,
                    "this_week": weekly_summary.get("total_calls", 0) if weekly_summary else 0,
                    "completion_rate": call_metrics.get("completion_rate", 0.0) if call_metrics else 0.0,
                    "avg_duration": call_metrics.get("avg_duration", 0.0) if call_metrics else 0.0,
                },
                "appointments": {
                    "today": call_metrics.get("appointments_booked", 0) if call_metrics else 0,
                    "conversion_rate": call_metrics.get("appointment_conversion_rate", 0.0) if call_metrics else 0.0,
                },
                "active_connections": {
                    "dashboard": manager.get_connection_count("dashboard"),
                    "calls": manager.get_connection_count("calls"),
                    "health": manager.get_connection_count("health"),
                },
            }

    except Exception as e:
        logger.error(f"Error fetching KPIs: {e}")
        return {
            "error": str(e),
            "calls": {"today": 0, "this_week": 0, "completion_rate": 0.0, "avg_duration": 0.0},
            "appointments": {"today": 0, "conversion_rate": 0.0},
        }


async def get_health_metrics() -> dict[str, Any]:
    """Fetch system health metrics."""
    try:
        from phone_agent.core.retry import get_circuit_breaker_status
        from phone_agent.core.metrics import get_metrics

        # Get latency metrics
        metrics = get_metrics()
        latency_stats = metrics.get_stats()

        # Get circuit breaker status
        circuit_status = get_circuit_breaker_status()

        # Get audit logger status
        from phone_agent.industry.gesundheit.compliance import get_audit_logger
        audit_logger = get_audit_logger()

        return {
            "latency": {
                "stt": latency_stats.get("stt", {}),
                "llm": latency_stats.get("llm", {}),
                "tts": latency_stats.get("tts", {}),
                "e2e": latency_stats.get("e2e", {}),
            },
            "circuit_breakers": circuit_status,
            "audit_logger": {
                "pending_entries": audit_logger.pending_count,
            },
            "status": "healthy",
        }

    except Exception as e:
        logger.error(f"Error fetching health metrics: {e}")
        return {
            "error": str(e),
            "status": "error",
        }


async def get_recent_calls(limit: int = 10) -> list[dict[str, Any]]:
    """Fetch recent call activity."""
    try:
        from phone_agent.db.session import get_db_context
        from phone_agent.db.repositories.calls import CallRepository

        async with get_db_context() as session:
            repo = CallRepository(session)
            calls = await repo.get_recent(limit=limit)

            return [
                {
                    "id": str(call.id),
                    "direction": call.direction,
                    "status": call.status,
                    "duration": call.duration,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "caller_id": call.caller_id,
                }
                for call in calls
            ]

    except Exception as e:
        logger.error(f"Error fetching recent calls: {e}")
        return []


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard KPIs.

    Broadcasts KPI updates every 5 seconds to all connected clients.

    Message format:
    {
        "type": "kpi_update",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {
            "calls": {"today": 45, "this_week": 312, ...},
            "appointments": {"today": 12, "conversion_rate": 0.27, ...},
            ...
        }
    }
    """
    await manager.connect(websocket, "dashboard")

    try:
        # Send initial data
        kpis = await get_dashboard_kpis()
        await websocket.send_json({
            "type": "initial",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": kpis,
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client ping or message
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,  # 60s timeout
                )

                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")

                # Handle refresh request
                elif data == "refresh":
                    kpis = await get_dashboard_kpis()
                    await websocket.send_json({
                        "type": "kpi_update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": kpis,
                    })

            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    finally:
        manager.disconnect(websocket, "dashboard")


@router.websocket("/calls")
async def websocket_calls(websocket: WebSocket):
    """WebSocket endpoint for live call activity feed.

    Streams new call events as they happen.

    Message format:
    {
        "type": "call_event",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {
            "event": "call_started|call_ended|appointment_booked",
            "call_id": "uuid",
            "details": {...}
        }
    }
    """
    await manager.connect(websocket, "calls")

    try:
        # Send recent calls as initial data
        recent = await get_recent_calls(limit=10)
        await websocket.send_json({
            "type": "initial",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"recent_calls": recent},
        })

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )

                if data == "ping":
                    await websocket.send_text("pong")

                elif data == "refresh":
                    recent = await get_recent_calls(limit=10)
                    await websocket.send_json({
                        "type": "recent_calls",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {"recent_calls": recent},
                    })

            except asyncio.TimeoutError:
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Calls WebSocket error: {e}")
    finally:
        manager.disconnect(websocket, "calls")


@router.websocket("/health")
async def websocket_health(websocket: WebSocket):
    """WebSocket endpoint for system health metrics.

    Broadcasts health updates every 10 seconds.

    Message format:
    {
        "type": "health_update",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {
            "latency": {"stt": {...}, "llm": {...}, ...},
            "circuit_breakers": {"groq_api": {"state": "closed", ...}},
            "audit_logger": {"pending_entries": 0},
            "status": "healthy"
        }
    }
    """
    await manager.connect(websocket, "health")

    try:
        # Send initial health data
        health = await get_health_metrics()
        await websocket.send_json({
            "type": "initial",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": health,
        })

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )

                if data == "ping":
                    await websocket.send_text("pong")

                elif data == "refresh":
                    health = await get_health_metrics()
                    await websocket.send_json({
                        "type": "health_update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": health,
                    })

            except asyncio.TimeoutError:
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Health WebSocket error: {e}")
    finally:
        manager.disconnect(websocket, "health")


# ============================================================================
# Event Broadcasting (called from other parts of the system)
# ============================================================================

async def broadcast_call_event(
    event_type: str,
    call_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Broadcast a call event to all connected clients.

    Call this from call handlers when events occur.

    Args:
        event_type: Type of event (call_started, call_ended, appointment_booked)
        call_id: Call UUID
        details: Additional event details
    """
    await manager.broadcast("calls", {
        "type": "call_event",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "event": event_type,
            "call_id": call_id,
            "details": details or {},
        },
    })


async def broadcast_kpi_update(kpis: dict[str, Any]) -> None:
    """Broadcast KPI update to dashboard clients.

    Args:
        kpis: KPI data to broadcast
    """
    await manager.broadcast("dashboard", {
        "type": "kpi_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": kpis,
    })


# ============================================================================
# Lifecycle Management
# ============================================================================

async def start_websocket_broadcasts() -> None:
    """Start WebSocket broadcast loops.

    Call this during application startup.
    """
    manager.start_broadcast_loops()


async def stop_websocket_broadcasts() -> None:
    """Stop WebSocket broadcast loops.

    Call this during application shutdown.
    """
    await manager.stop_broadcast_loops()
