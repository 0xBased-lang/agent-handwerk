"""WebSocket stress testing for Phone Agent Twilio Media Streams.

This script simulates multiple concurrent WebSocket connections
to the Twilio media stream endpoint, sending audio data at realistic rates.

Run with:
    python tests/load/websocket_stress.py --connections 50 --duration 60

Requirements:
    pip install websockets aiohttp
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed


@dataclass
class ConnectionMetrics:
    """Metrics for a single WebSocket connection."""
    call_sid: str
    connected_at: float = 0.0
    disconnected_at: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    errors: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.disconnected_at == 0:
            return time.time() - self.connected_at
        return self.disconnected_at - self.connected_at

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)


@dataclass
class TestResults:
    """Aggregate test results."""
    start_time: float
    end_time: float = 0.0
    connections_attempted: int = 0
    connections_successful: int = 0
    connections_failed: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    connection_metrics: list[ConnectionMetrics] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return (self.end_time or time.time()) - self.start_time

    @property
    def success_rate(self) -> float:
        if self.connections_attempted == 0:
            return 0.0
        return self.connections_successful / self.connections_attempted * 100

    @property
    def avg_latency(self) -> float:
        all_latencies = []
        for m in self.connection_metrics:
            all_latencies.extend(m.latencies)
        if not all_latencies:
            return 0.0
        return statistics.mean(all_latencies)

    @property
    def p95_latency(self) -> float:
        all_latencies = []
        for m in self.connection_metrics:
            all_latencies.extend(m.latencies)
        if not all_latencies:
            return 0.0
        all_latencies.sort()
        idx = int(len(all_latencies) * 0.95)
        return all_latencies[idx] if idx < len(all_latencies) else all_latencies[-1]


def generate_audio_chunk(size: int = 160) -> str:
    """Generate fake μ-law audio data (similar to Twilio format).

    Args:
        size: Number of bytes (160 = 20ms at 8kHz)

    Returns:
        Base64-encoded audio data
    """
    # Generate random bytes simulating μ-law audio
    audio_data = bytes([random.randint(0, 255) for _ in range(size)])
    return base64.b64encode(audio_data).decode("ascii")


def create_media_message(stream_sid: str, sequence: int) -> dict[str, Any]:
    """Create a Twilio media stream message.

    Args:
        stream_sid: The stream identifier
        sequence: Message sequence number

    Returns:
        Twilio-format media message
    """
    return {
        "event": "media",
        "sequenceNumber": str(sequence),
        "media": {
            "track": "inbound",
            "chunk": str(sequence),
            "timestamp": str(int(time.time() * 1000)),
            "payload": generate_audio_chunk(160),
        },
        "streamSid": stream_sid,
    }


def create_start_message(stream_sid: str, call_sid: str) -> dict[str, Any]:
    """Create a Twilio stream start message."""
    return {
        "event": "start",
        "sequenceNumber": "1",
        "start": {
            "streamSid": stream_sid,
            "accountSid": "AC" + uuid.uuid4().hex[:32],
            "callSid": call_sid,
            "tracks": ["inbound"],
            "customParameters": {},
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1,
            },
        },
        "streamSid": stream_sid,
    }


async def simulate_media_stream(
    ws_url: str,
    call_sid: str,
    duration_seconds: float,
    results: TestResults,
) -> ConnectionMetrics:
    """Simulate a single Twilio media stream connection.

    Args:
        ws_url: WebSocket URL to connect to
        call_sid: Simulated call SID
        duration_seconds: How long to maintain the connection
        results: Shared results object

    Returns:
        Connection metrics
    """
    metrics = ConnectionMetrics(call_sid=call_sid)
    stream_sid = "MZ" + uuid.uuid4().hex[:32]

    try:
        results.connections_attempted += 1

        async with websockets.connect(
            f"{ws_url}/webhooks/twilio/media/{call_sid}",
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as websocket:
            metrics.connected_at = time.time()
            results.connections_successful += 1

            # Send start message
            start_msg = json.dumps(create_start_message(stream_sid, call_sid))
            await websocket.send(start_msg)
            metrics.messages_sent += 1
            metrics.bytes_sent += len(start_msg)

            # Simulate audio streaming at 20ms intervals (50 packets/sec)
            sequence = 2
            end_time = time.time() + duration_seconds

            while time.time() < end_time:
                try:
                    # Send media packet
                    send_start = time.time()
                    media_msg = json.dumps(create_media_message(stream_sid, sequence))
                    await websocket.send(media_msg)
                    metrics.messages_sent += 1
                    metrics.bytes_sent += len(media_msg)
                    sequence += 1

                    # Check for responses (non-blocking)
                    try:
                        response = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=0.01,
                        )
                        latency = (time.time() - send_start) * 1000
                        metrics.latencies.append(latency)
                        metrics.messages_received += 1
                        metrics.bytes_received += len(response)
                    except asyncio.TimeoutError:
                        pass

                    # Maintain ~50 packets/second rate
                    elapsed = time.time() - send_start
                    if elapsed < 0.02:
                        await asyncio.sleep(0.02 - elapsed)

                except ConnectionClosed:
                    metrics.errors.append("Connection closed by server")
                    break
                except Exception as e:
                    metrics.errors.append(f"Error during streaming: {e}")
                    break

            # Send stop message
            stop_msg = json.dumps({"event": "stop", "streamSid": stream_sid})
            try:
                await websocket.send(stop_msg)
                metrics.messages_sent += 1
                metrics.bytes_sent += len(stop_msg)
            except Exception:
                pass

    except websockets.exceptions.InvalidStatusCode as e:
        metrics.errors.append(f"Connection rejected: {e.status_code}")
        results.connections_failed += 1
    except Exception as e:
        metrics.errors.append(f"Connection failed: {e}")
        results.connections_failed += 1
    finally:
        metrics.disconnected_at = time.time()
        results.total_messages_sent += metrics.messages_sent
        results.total_messages_received += metrics.messages_received
        results.total_bytes_sent += metrics.bytes_sent
        results.total_bytes_received += metrics.bytes_received
        results.connection_metrics.append(metrics)

    return metrics


async def run_websocket_stress_test(
    ws_url: str,
    num_connections: int,
    duration_seconds: float,
    ramp_up_seconds: float = 5.0,
) -> TestResults:
    """Run WebSocket stress test with multiple concurrent connections.

    Args:
        ws_url: Base WebSocket URL
        num_connections: Number of concurrent connections
        duration_seconds: Duration of each connection
        ramp_up_seconds: Time to ramp up to full connections

    Returns:
        Aggregate test results
    """
    results = TestResults(start_time=time.time())

    # Calculate delay between connection starts
    delay = ramp_up_seconds / num_connections if num_connections > 1 else 0

    # Create tasks for all connections
    tasks = []
    for i in range(num_connections):
        call_sid = f"CA{uuid.uuid4().hex[:32]}"
        task = asyncio.create_task(
            simulate_media_stream(ws_url, call_sid, duration_seconds, results)
        )
        tasks.append(task)

        # Stagger connection starts
        if delay > 0 and i < num_connections - 1:
            await asyncio.sleep(delay)

    # Wait for all connections to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    results.end_time = time.time()
    return results


def print_results(results: TestResults) -> None:
    """Print formatted test results."""
    print("\n" + "=" * 60)
    print("WEBSOCKET STRESS TEST RESULTS")
    print("=" * 60)

    print(f"\n📊 Connection Summary:")
    print(f"   Total Duration: {results.duration:.2f}s")
    print(f"   Connections Attempted: {results.connections_attempted}")
    print(f"   Connections Successful: {results.connections_successful}")
    print(f"   Connections Failed: {results.connections_failed}")
    print(f"   Success Rate: {results.success_rate:.1f}%")

    print(f"\n📦 Data Transfer:")
    print(f"   Messages Sent: {results.total_messages_sent:,}")
    print(f"   Messages Received: {results.total_messages_received:,}")
    print(f"   Bytes Sent: {results.total_bytes_sent / 1024:.2f} KB")
    print(f"   Bytes Received: {results.total_bytes_received / 1024:.2f} KB")
    print(f"   Throughput: {results.total_messages_sent / results.duration:.1f} msg/s")

    if results.connection_metrics:
        durations = [m.duration for m in results.connection_metrics if m.duration > 0]
        if durations:
            print(f"\n⏱️  Timing:")
            print(f"   Average Latency: {results.avg_latency:.2f}ms")
            print(f"   95th Percentile Latency: {results.p95_latency:.2f}ms")
            print(f"   Average Connection Duration: {statistics.mean(durations):.2f}s")

    # Print errors summary
    all_errors = []
    for m in results.connection_metrics:
        all_errors.extend(m.errors)

    if all_errors:
        print(f"\n⚠️  Errors ({len(all_errors)} total):")
        error_counts: dict[str, int] = {}
        for err in all_errors:
            error_counts[err] = error_counts.get(err, 0) + 1

        for err, count in sorted(error_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"   - {err}: {count} occurrences")

    # Performance verdict
    print(f"\n{'=' * 60}")
    if results.success_rate >= 95 and results.avg_latency < 100:
        print("✅ PASSED - WebSocket performance is excellent")
    elif results.success_rate >= 80 and results.avg_latency < 200:
        print("⚠️  WARNING - WebSocket performance is acceptable but could improve")
    else:
        print("❌ FAILED - WebSocket performance needs improvement")
    print("=" * 60)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WebSocket stress testing for Phone Agent"
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8080",
        help="WebSocket server URL (default: ws://localhost:8080)",
    )
    parser.add_argument(
        "-c", "--connections",
        type=int,
        default=10,
        help="Number of concurrent connections (default: 10)",
    )
    parser.add_argument(
        "-d", "--duration",
        type=float,
        default=30.0,
        help="Duration of each connection in seconds (default: 30)",
    )
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=5.0,
        help="Ramp-up time in seconds (default: 5)",
    )

    args = parser.parse_args()

    print(f"\n🚀 Starting WebSocket Stress Test")
    print(f"   URL: {args.url}")
    print(f"   Concurrent Connections: {args.connections}")
    print(f"   Connection Duration: {args.duration}s")
    print(f"   Ramp-up Time: {args.ramp_up}s")

    results = await run_websocket_stress_test(
        ws_url=args.url,
        num_connections=args.connections,
        duration_seconds=args.duration,
        ramp_up_seconds=args.ramp_up,
    )

    print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
