"""Device heartbeat client for remote monitoring."""

from __future__ import annotations

import asyncio
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from itf_shared.logging import get_logger
from itf_shared.models import DeviceInfo, DeviceStatus, Industry

log = get_logger(__name__)


class HeartbeatClient:
    """Sends periodic heartbeats to central monitoring server.

    Collects device metrics and status, sends to configured endpoint.
    Works over Tailscale network for secure communication.
    """

    def __init__(
        self,
        device_id: str,
        product: str,
        industry: Industry,
        endpoint: str | None = None,
        interval: int = 60,
        on_command: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize heartbeat client.

        Args:
            device_id: Unique device identifier
            product: Product name (phone-agent, etc.)
            industry: Target industry
            endpoint: Heartbeat API endpoint URL (optional for local-only)
            interval: Seconds between heartbeats
            on_command: Callback for remote commands (action, params)
        """
        self.device_id = device_id
        self.product = product
        self.industry = industry
        self.endpoint = endpoint
        self.interval = interval
        self.on_command = on_command

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._start_time = datetime.now(timezone.utc)

    async def start(self) -> None:
        """Start the heartbeat loop."""
        if self._running:
            return

        self._running = True
        self._start_time = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._heartbeat_loop())
        log.info("Heartbeat client started", device_id=self.device_id)

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Heartbeat client stopped", device_id=self.device_id)

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                device_info = self._collect_metrics()
                await self._send_heartbeat(device_info)
            except Exception as e:
                log.error("Heartbeat failed", error=str(e))

            await asyncio.sleep(self.interval)

    def _collect_metrics(self) -> DeviceInfo:
        """Collect current device metrics."""
        now = datetime.now(timezone.utc)
        uptime = int((now - self._start_time).total_seconds())

        return DeviceInfo(
            device_id=self.device_id,
            product=self.product,
            industry=self.industry,
            status=DeviceStatus.ONLINE,
            last_seen=now,
            uptime_seconds=uptime,
            os_version=platform.platform(),
            tailscale_ip=self._get_tailscale_ip(),
            cpu_temp_celsius=self._get_cpu_temp(),
            memory_used_percent=self._get_memory_usage(),
            disk_used_percent=self._get_disk_usage(),
        )

    async def _send_heartbeat(self, device_info: DeviceInfo) -> None:
        """Send heartbeat to monitoring endpoint."""
        if not self.endpoint:
            # Local-only mode: just log
            log.debug(
                "Heartbeat (local)",
                device_id=device_info.device_id,
                cpu_temp=device_info.cpu_temp_celsius,
                memory=device_info.memory_used_percent,
            )
            return

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json=device_info.model_dump(mode="json"),
                timeout=10.0,
            )
            response.raise_for_status()

            # Check for remote commands
            data = response.json()
            if command := data.get("command"):
                log.info("Received remote command", command=command)
                if self.on_command:
                    self.on_command(command, data.get("params", {}))

    def _get_tailscale_ip(self) -> str:
        """Get Tailscale IP address."""
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_cpu_temp(self) -> float:
        """Get CPU temperature in Celsius (Raspberry Pi)."""
        try:
            temp_file = Path("/sys/class/thermal/thermal_zone0/temp")
            if temp_file.exists():
                return int(temp_file.read_text().strip()) / 1000.0
        except (OSError, ValueError):
            pass
        return 0.0

    def _get_memory_usage(self) -> float:
        """Get memory usage percentage."""
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem_total = mem_available = 0
            for line in lines:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
            if mem_total > 0:
                return (1 - mem_available / mem_total) * 100
        except (OSError, ValueError, IndexError):
            pass
        return 0.0

    def _get_disk_usage(self) -> float:
        """Get root disk usage percentage."""
        try:
            import shutil

            usage = shutil.disk_usage("/")
            return (usage.used / usage.total) * 100
        except (OSError, AttributeError):
            pass
        return 0.0
