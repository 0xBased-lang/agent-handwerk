"""Load testing for Phone Agent API endpoints.

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8080

Or headless mode:
    locust -f tests/load/locustfile.py --host=http://localhost:8080 \
           --users 100 --spawn-rate 10 --run-time 5m --headless

Dashboard available at: http://localhost:8089
"""
from __future__ import annotations

import json
import random
import uuid
from typing import Any

from locust import HttpUser, between, task, events
from locust.runners import MasterRunner


# Test data pools
INDUSTRIES = ["gesundheit", "handwerk", "gastro", "freie_berufe"]
CALL_STATUSES = ["ringing", "in_progress", "completed", "failed"]
PHONE_NUMBERS = [f"+49151{random.randint(10000000, 99999999)}" for _ in range(100)]


class PhoneAgentAPIUser(HttpUser):
    """Simulates typical Phone Agent API usage patterns.

    This user performs a realistic mix of operations:
    - Reading calls (high frequency)
    - Creating calls (medium frequency)
    - Updating calls (medium frequency)
    - Health checks (low frequency)
    """

    wait_time = between(0.5, 2.0)  # Wait 0.5-2 seconds between requests

    def on_start(self):
        """Initialize user session with created call IDs."""
        self.call_ids: list[str] = []
        self.industry = random.choice(INDUSTRIES)

    @task(10)  # High frequency - reading is most common
    def list_calls(self):
        """List calls with optional filtering."""
        params = {}

        # Randomly add filters
        if random.random() > 0.5:
            params["industry"] = self.industry
        if random.random() > 0.7:
            params["status"] = random.choice(CALL_STATUSES)
        if random.random() > 0.8:
            params["limit"] = random.choice([10, 25, 50])

        with self.client.get(
            "/api/v1/calls",
            params=params,
            catch_response=True,
            name="/api/v1/calls [LIST]"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)  # Medium frequency - creating calls
    def create_call(self):
        """Create a new call."""
        caller = random.choice(PHONE_NUMBERS)
        callee = random.choice(PHONE_NUMBERS)

        # Ensure different numbers
        while callee == caller:
            callee = random.choice(PHONE_NUMBERS)

        payload = {
            "direction": random.choice(["inbound", "outbound"]),
            "caller_id": caller,
            "callee_id": callee,
            "industry": self.industry,
            "metadata": {
                "test_run": True,
                "user_id": str(uuid.uuid4()),
            }
        }

        with self.client.post(
            "/api/v1/calls",
            json=payload,
            catch_response=True,
            name="/api/v1/calls [CREATE]"
        ) as response:
            if response.status_code == 201:
                try:
                    data = response.json()
                    call_id = data.get("id")
                    if call_id:
                        self.call_ids.append(call_id)
                        # Keep list manageable
                        if len(self.call_ids) > 50:
                            self.call_ids.pop(0)
                    response.success()
                except Exception as e:
                    response.failure(f"Failed to parse response: {e}")
            elif response.status_code == 429:
                response.failure("Rate limited")
            elif response.status_code == 422:
                response.failure("Validation error")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(3)  # Medium-low frequency - updating calls
    def update_call(self):
        """Update an existing call."""
        if not self.call_ids:
            return

        call_id = random.choice(self.call_ids)

        payload = {
            "status": random.choice(CALL_STATUSES),
            "duration_seconds": random.randint(30, 600),
        }

        with self.client.patch(
            f"/api/v1/calls/{call_id}",
            json=payload,
            catch_response=True,
            name="/api/v1/calls/{id} [UPDATE]"
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(2)  # Low frequency - getting specific call
    def get_call(self):
        """Get a specific call by ID."""
        if not self.call_ids:
            return

        call_id = random.choice(self.call_ids)

        with self.client.get(
            f"/api/v1/calls/{call_id}",
            catch_response=True,
            name="/api/v1/calls/{id} [GET]"
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(1)  # Low frequency - health checks
    def health_check(self):
        """Check API health."""
        with self.client.get(
            "/api/v1/health",
            catch_response=True,
            name="/api/v1/health"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")


class WebhookUser(HttpUser):
    """Simulates incoming webhook traffic from Twilio/sipgate.

    This user generates realistic webhook payloads at high frequency
    to test webhook processing under load.
    """

    wait_time = between(0.1, 0.5)  # Webhooks can come in rapidly
    weight = 2  # Less common than API users

    def on_start(self):
        """Initialize with simulated Twilio call SIDs."""
        self.call_sids = [f"CA{uuid.uuid4().hex[:32]}" for _ in range(20)]

    @task(10)
    def twilio_call_status(self):
        """Simulate Twilio call status webhook."""
        call_sid = random.choice(self.call_sids)

        payload = {
            "CallSid": call_sid,
            "AccountSid": "AC" + uuid.uuid4().hex[:32],
            "CallStatus": random.choice([
                "initiated", "ringing", "answered", "completed", "busy", "no-answer"
            ]),
            "Direction": random.choice(["inbound", "outbound-api"]),
            "From": random.choice(PHONE_NUMBERS),
            "To": random.choice(PHONE_NUMBERS),
            "CallDuration": str(random.randint(0, 600)),
        }

        with self.client.post(
            "/webhooks/twilio/status",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            catch_response=True,
            name="/webhooks/twilio/status"
        ) as response:
            # Webhooks may fail signature validation in load tests
            if response.status_code in (200, 400, 403):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)
    def twilio_voice(self):
        """Simulate Twilio voice webhook (TwiML request)."""
        call_sid = random.choice(self.call_sids)

        payload = {
            "CallSid": call_sid,
            "AccountSid": "AC" + uuid.uuid4().hex[:32],
            "From": random.choice(PHONE_NUMBERS),
            "To": random.choice(PHONE_NUMBERS),
            "Direction": "inbound",
        }

        with self.client.post(
            "/webhooks/twilio/voice",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            catch_response=True,
            name="/webhooks/twilio/voice"
        ) as response:
            if response.status_code in (200, 400, 403):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


class HighLoadAPIUser(HttpUser):
    """High-frequency API user for stress testing.

    This user hammers the API with minimal wait times to find
    breaking points and rate limit effectiveness.
    """

    wait_time = between(0.01, 0.1)  # Very aggressive
    weight = 1  # Less common, used for stress tests

    @task(5)
    def rapid_list_calls(self):
        """Rapid-fire call listing."""
        with self.client.get(
            "/api/v1/calls",
            catch_response=True,
            name="/api/v1/calls [RAPID]"
        ) as response:
            # Expect rate limiting to kick in
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(1)
    def rapid_health_check(self):
        """Rapid-fire health checks."""
        with self.client.get(
            "/api/v1/health",
            catch_response=True,
            name="/api/v1/health [RAPID]"
        ) as response:
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


# Event hooks for reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start."""
    print("\n" + "=" * 60)
    print("PHONE AGENT LOAD TEST STARTED")
    print("=" * 60)
    if isinstance(environment.runner, MasterRunner):
        print(f"Running distributed test with {environment.runner.worker_count} workers")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test summary."""
    print("\n" + "=" * 60)
    print("PHONE AGENT LOAD TEST COMPLETED")
    print("=" * 60)

    stats = environment.stats
    print(f"\nTotal Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Median Response Time: {stats.total.median_response_time}ms")
    print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95)}ms")
    print(f"99th Percentile: {stats.total.get_response_time_percentile(0.99)}ms")
    print(f"Requests/s: {stats.total.current_rps:.2f}")

    if stats.total.num_failures > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        print(f"\nFailure Rate: {failure_rate:.2f}%")
        print("\nTop Failures:")
        for name, err in list(stats.errors.items())[:5]:
            print(f"  - {name}: {err.occurrences} occurrences")
