#!/usr/bin/env python3
"""Unified load testing runner for Phone Agent.

This script runs all load tests and generates a comprehensive report.

Usage:
    python tests/load/run_load_tests.py --profile quick
    python tests/load/run_load_tests.py --profile standard
    python tests/load/run_load_tests.py --profile stress

Profiles:
    quick    - Fast smoke test (1 min)
    standard - Normal load test (5 min)
    stress   - High load stress test (15 min)
    soak     - Extended soak test (60 min)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TestProfile:
    """Load test profile configuration."""
    name: str
    description: str
    # API load test (locust)
    api_users: int
    api_spawn_rate: int
    api_duration: str  # locust format: "1m", "5m", etc.
    # WebSocket test
    ws_connections: int
    ws_duration: float
    # AI pipeline test
    ai_calls: int
    ai_duration: float


# Predefined test profiles
PROFILES = {
    "quick": TestProfile(
        name="quick",
        description="Quick smoke test - verify basic functionality",
        api_users=10,
        api_spawn_rate=5,
        api_duration="1m",
        ws_connections=5,
        ws_duration=30,
        ai_calls=3,
        ai_duration=20,
    ),
    "standard": TestProfile(
        name="standard",
        description="Standard load test - typical production load",
        api_users=50,
        api_spawn_rate=10,
        api_duration="5m",
        ws_connections=20,
        ws_duration=60,
        ai_calls=10,
        ai_duration=60,
    ),
    "stress": TestProfile(
        name="stress",
        description="Stress test - find breaking points",
        api_users=200,
        api_spawn_rate=20,
        api_duration="10m",
        ws_connections=50,
        ws_duration=120,
        ai_calls=30,
        ai_duration=120,
    ),
    "soak": TestProfile(
        name="soak",
        description="Soak test - check for memory leaks over time",
        api_users=25,
        api_spawn_rate=5,
        api_duration="60m",
        ws_connections=10,
        ws_duration=3600,
        ai_calls=5,
        ai_duration=3600,
    ),
}


def check_server_running(host: str = "localhost", port: int = 8080) -> bool:
    """Check if the Phone Agent server is running."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((host, port))
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def run_api_load_test(profile: TestProfile, host: str) -> dict[str, Any]:
    """Run locust API load test.

    Args:
        profile: Test profile configuration
        host: Target host URL

    Returns:
        Test results dictionary
    """
    print(f"\n{'=' * 60}")
    print("🌐 Running API Load Test (Locust)")
    print("=" * 60)

    locust_file = Path(__file__).parent / "locustfile.py"

    # Run locust in headless mode
    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(locust_file),
        "--host", host,
        "--users", str(profile.api_users),
        "--spawn-rate", str(profile.api_spawn_rate),
        "--run-time", profile.api_duration,
        "--headless",
        "--csv", "/tmp/locust_results",
        "--only-summary",
    ]

    print(f"   Users: {profile.api_users}")
    print(f"   Spawn Rate: {profile.api_spawn_rate}/s")
    print(f"   Duration: {profile.api_duration}")
    print(f"\nRunning: {' '.join(cmd[:6])}...")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min timeout
        )
        duration = time.time() - start_time

        # Parse CSV results if available
        stats_file = Path("/tmp/locust_results_stats.csv")
        stats = {}
        if stats_file.exists():
            import csv
            with open(stats_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name") == "Aggregated":
                        stats = {
                            "requests": int(row.get("Request Count", 0)),
                            "failures": int(row.get("Failure Count", 0)),
                            "avg_response_time": float(row.get("Average Response Time", 0)),
                            "p50": float(row.get("50%", 0)),
                            "p95": float(row.get("95%", 0)),
                            "p99": float(row.get("99%", 0)),
                            "rps": float(row.get("Requests/s", 0)),
                        }
                        break

        return {
            "success": result.returncode == 0,
            "duration": duration,
            "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stats": stats,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Test timed out",
            "duration": time.time() - start_time,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration": time.time() - start_time,
        }


async def run_websocket_test(profile: TestProfile, host: str) -> dict[str, Any]:
    """Run WebSocket stress test.

    Args:
        profile: Test profile configuration
        host: Target host URL

    Returns:
        Test results dictionary
    """
    print(f"\n{'=' * 60}")
    print("🔌 Running WebSocket Stress Test")
    print("=" * 60)

    from tests.load.websocket_stress import run_websocket_stress_test, print_results

    ws_host = host.replace("http://", "ws://").replace("https://", "wss://")

    print(f"   Connections: {profile.ws_connections}")
    print(f"   Duration: {profile.ws_duration}s")
    print(f"   Target: {ws_host}")

    start_time = time.time()

    try:
        results = await run_websocket_stress_test(
            ws_url=ws_host,
            num_connections=profile.ws_connections,
            duration_seconds=profile.ws_duration,
        )

        print_results(results)

        return {
            "success": results.success_rate >= 80,
            "duration": time.time() - start_time,
            "connections_attempted": results.connections_attempted,
            "connections_successful": results.connections_successful,
            "success_rate": results.success_rate,
            "messages_sent": results.total_messages_sent,
            "avg_latency_ms": results.avg_latency,
            "p95_latency_ms": results.p95_latency,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration": time.time() - start_time,
        }


async def run_ai_pipeline_test(profile: TestProfile) -> dict[str, Any]:
    """Run AI pipeline stress test.

    Args:
        profile: Test profile configuration

    Returns:
        Test results dictionary
    """
    print(f"\n{'=' * 60}")
    print("🧠 Running AI Pipeline Stress Test")
    print("=" * 60)

    from tests.load.ai_pipeline_stress import run_ai_pipeline_test as ai_test, print_results

    print(f"   Concurrent Calls: {profile.ai_calls}")
    print(f"   Duration: {profile.ai_duration}s")

    start_time = time.time()

    try:
        results = await ai_test(
            concurrent_calls=profile.ai_calls,
            duration_seconds=profile.ai_duration,
        )

        print_results(results)

        total_stats = results.get_latency_stats("total_latency_ms")

        return {
            "success": results.success_rate >= 95,
            "duration": time.time() - start_time,
            "concurrent_calls": results.concurrent_calls,
            "total_requests": results.total_requests,
            "success_rate": results.success_rate,
            "throughput_rps": results.throughput,
            "avg_latency_ms": total_stats["avg"],
            "p95_latency_ms": total_stats["p95"],
            "memory_peak_mb": max(results.memory_samples) if results.memory_samples else 0,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration": time.time() - start_time,
        }


def generate_report(
    profile: TestProfile,
    api_results: dict[str, Any],
    ws_results: dict[str, Any],
    ai_results: dict[str, Any],
) -> str:
    """Generate comprehensive load test report.

    Args:
        profile: Test profile used
        api_results: API test results
        ws_results: WebSocket test results
        ai_results: AI pipeline test results

    Returns:
        Formatted report string
    """
    report = []
    report.append("\n" + "=" * 70)
    report.append("📊 PHONE AGENT LOAD TEST REPORT")
    report.append("=" * 70)
    report.append(f"\nProfile: {profile.name} - {profile.description}")
    report.append(f"Timestamp: {datetime.now().isoformat()}")

    # Overall status
    all_passed = all([
        api_results.get("success", False),
        ws_results.get("success", False),
        ai_results.get("success", False),
    ])

    report.append(f"\nOverall Status: {'✅ PASSED' if all_passed else '❌ FAILED'}")

    # API Results
    report.append(f"\n{'─' * 70}")
    report.append("🌐 API Load Test Results")
    report.append(f"   Status: {'✅' if api_results.get('success') else '❌'}")

    if api_results.get("stats"):
        stats = api_results["stats"]
        report.append(f"   Requests: {stats.get('requests', 0):,}")
        report.append(f"   Failures: {stats.get('failures', 0)}")
        report.append(f"   Avg Response: {stats.get('avg_response_time', 0):.1f}ms")
        report.append(f"   p95 Response: {stats.get('p95', 0):.1f}ms")
        report.append(f"   Throughput: {stats.get('rps', 0):.1f} req/s")
    elif api_results.get("error"):
        report.append(f"   Error: {api_results['error']}")

    # WebSocket Results
    report.append(f"\n{'─' * 70}")
    report.append("🔌 WebSocket Stress Test Results")
    report.append(f"   Status: {'✅' if ws_results.get('success') else '❌'}")

    if not ws_results.get("error"):
        report.append(f"   Connections: {ws_results.get('connections_successful', 0)}/{ws_results.get('connections_attempted', 0)}")
        report.append(f"   Success Rate: {ws_results.get('success_rate', 0):.1f}%")
        report.append(f"   Messages Sent: {ws_results.get('messages_sent', 0):,}")
        report.append(f"   Avg Latency: {ws_results.get('avg_latency_ms', 0):.1f}ms")
        report.append(f"   p95 Latency: {ws_results.get('p95_latency_ms', 0):.1f}ms")
    else:
        report.append(f"   Error: {ws_results['error']}")

    # AI Pipeline Results
    report.append(f"\n{'─' * 70}")
    report.append("🧠 AI Pipeline Stress Test Results")
    report.append(f"   Status: {'✅' if ai_results.get('success') else '❌'}")

    if not ai_results.get("error"):
        report.append(f"   Concurrent Calls: {ai_results.get('concurrent_calls', 0)}")
        report.append(f"   Total Requests: {ai_results.get('total_requests', 0):,}")
        report.append(f"   Success Rate: {ai_results.get('success_rate', 0):.1f}%")
        report.append(f"   Throughput: {ai_results.get('throughput_rps', 0):.2f} req/s")
        report.append(f"   Avg Latency: {ai_results.get('avg_latency_ms', 0):.1f}ms")
        report.append(f"   p95 Latency: {ai_results.get('p95_latency_ms', 0):.1f}ms")
        if ai_results.get("memory_peak_mb"):
            report.append(f"   Peak Memory: {ai_results['memory_peak_mb']:.1f}MB")
    else:
        report.append(f"   Error: {ai_results['error']}")

    # Recommendations
    report.append(f"\n{'─' * 70}")
    report.append("💡 Recommendations:")

    if api_results.get("stats", {}).get("p95", 0) > 500:
        report.append("   • API p95 latency high - consider caching or query optimization")
    if ws_results.get("success_rate", 100) < 95:
        report.append("   • WebSocket success rate low - check connection handling")
    if ai_results.get("p95_latency_ms", 0) > 1000:
        report.append("   • AI pipeline latency high - optimize STT/LLM/TTS")
    if ai_results.get("memory_peak_mb", 0) > 500:
        report.append("   • High memory usage - consider streaming or cleanup")

    if all_passed:
        report.append("   • All tests passed! System ready for production load.")

    report.append("=" * 70)

    return "\n".join(report)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Phone Agent load tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/load/run_load_tests.py --profile quick
    python tests/load/run_load_tests.py --profile standard --host http://staging:8080
    python tests/load/run_load_tests.py --profile stress --skip-api

Profiles:
    quick    - 1 min smoke test (10 users, 5 WS, 3 AI calls)
    standard - 5 min load test (50 users, 20 WS, 10 AI calls)
    stress   - 10 min stress test (200 users, 50 WS, 30 AI calls)
    soak     - 60 min soak test (25 users, 10 WS, 5 AI calls)
        """,
    )
    parser.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        default="quick",
        help="Test profile to use (default: quick)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8080",
        help="Target host URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip API load test",
    )
    parser.add_argument(
        "--skip-ws",
        action="store_true",
        help="Skip WebSocket test",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI pipeline test",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for JSON results",
    )

    args = parser.parse_args()
    profile = PROFILES[args.profile]

    print("\n" + "=" * 60)
    print("🚀 PHONE AGENT LOAD TEST RUNNER")
    print("=" * 60)
    print(f"\nProfile: {profile.name}")
    print(f"Description: {profile.description}")
    print(f"Target: {args.host}")

    # Check server
    if not args.skip_api or not args.skip_ws:
        if not check_server_running():
            print("\n⚠️  Warning: Server doesn't appear to be running at localhost:8080")
            print("   Some tests may fail. Start with: python -m phone_agent")
            response = input("\n   Continue anyway? [y/N]: ")
            if response.lower() != "y":
                print("Aborted.")
                return

    # Run tests
    api_results: dict[str, Any] = {"skipped": True}
    ws_results: dict[str, Any] = {"skipped": True}
    ai_results: dict[str, Any] = {"skipped": True}

    if not args.skip_api:
        api_results = run_api_load_test(profile, args.host)

    if not args.skip_ws:
        ws_results = await run_websocket_test(profile, args.host)

    if not args.skip_ai:
        ai_results = await run_ai_pipeline_test(profile)

    # Generate report
    report = generate_report(profile, api_results, ws_results, ai_results)
    print(report)

    # Save JSON results if requested
    if args.output:
        results = {
            "profile": profile.name,
            "timestamp": datetime.now().isoformat(),
            "host": args.host,
            "api": api_results,
            "websocket": ws_results,
            "ai_pipeline": ai_results,
        }
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    # Add parent directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    sys.path.insert(0, str(Path(__file__).parent.parent))

    asyncio.run(main())
