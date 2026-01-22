"""
Locust load testing for Client Analysis Agent API.

Run with:
    locust -f tests/locustfile.py --host=http://localhost:8000

Web UI: http://localhost:8089

For headless mode:
    locust -f tests/locustfile.py --host=http://localhost:8000 \
           --headless -u 10 -r 2 -t 60s
"""

import random
import string
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


# Sample test data
SAMPLE_COMPANIES = [
    ("ООО Газпром", "7736050003"),
    ("ПАО Сбербанк", "7707083893"),
    ("ООО Яндекс", "7736207543"),
    ("ПАО Лукойл", "7708004767"),
    ("ООО Тестовая компания", ""),
]

SAMPLE_INNS = [
    "7707083893",
    "7736050003",
    "7708004767",
    "7736207543",
    "5024088641",
]


def random_company():
    """Return random company name and INN."""
    return random.choice(SAMPLE_COMPANIES)


def random_inn():
    """Return random INN."""
    return random.choice(SAMPLE_INNS)


class HealthCheckUser(HttpUser):
    """
    User that only checks health endpoints.
    Useful for baseline performance testing.
    """

    wait_time = between(0.5, 2)
    weight = 3  # Higher weight = more users of this type

    @task(10)
    def health_check(self):
        """Check basic health endpoint."""
        with self.client.get(
            "/api/v1/utility/health",
            catch_response=True,
            name="/api/v1/utility/health"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def metrics_endpoint(self):
        """Check Prometheus metrics."""
        self.client.get("/metrics", name="/metrics")

    @task(2)
    def custom_metrics(self):
        """Check custom application metrics."""
        self.client.get("/metrics/custom", name="/metrics/custom")


class APIUser(HttpUser):
    """
    User that interacts with main API endpoints.
    Simulates typical API usage patterns.
    """

    wait_time = between(1, 5)
    weight = 2

    def on_start(self):
        """Setup before starting tasks."""
        self.session_id = None
        self.report_id = None

    @task(5)
    def get_recent_reports(self):
        """Fetch list of recent reports."""
        self.client.get(
            "/api/v1/reports/recent?limit=10",
            name="/api/v1/reports/recent"
        )

    @task(3)
    def get_analytics(self):
        """Fetch analytics data."""
        self.client.get(
            "/api/v1/analytics/summary",
            name="/api/v1/analytics/summary"
        )

    @task(2)
    def search_reports(self):
        """Search for reports by company name."""
        company, _ = random_company()
        self.client.get(
            f"/api/v1/reports/search?query={company[:10]}",
            name="/api/v1/reports/search"
        )

    @task(1)
    def export_json(self):
        """Test JSON export if we have a report ID."""
        if self.report_id:
            self.client.get(
                f"/api/v1/export/json/{self.report_id}",
                name="/api/v1/export/json/[id]"
            )


class AnalysisUser(HttpUser):
    """
    User that triggers analysis workflows.
    Heavy operations - use sparingly in load tests.
    """

    wait_time = between(10, 30)  # Long wait between analyses
    weight = 1  # Lower weight = fewer users of this type

    @task(1)
    def trigger_analysis(self):
        """
        Trigger a company analysis.
        Note: This is a heavy operation, use sparingly.
        """
        company, inn = random_company()

        with self.client.post(
            "/api/v1/agent/analyze-client",
            json={
                "client_name": company,
                "inn": inn,
                "additional_notes": "Load test analysis"
            },
            catch_response=True,
            name="/api/v1/agent/analyze-client",
            timeout=120  # Analysis can take up to 2 minutes
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
                try:
                    data = response.json()
                    self.session_id = data.get("session_id")
                except Exception:
                    pass
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Analysis failed: {response.status_code}")


class AdminUser(HttpUser):
    """
    User that accesses admin endpoints.
    Requires ADMIN_TOKEN to be set.
    """

    wait_time = between(5, 15)
    weight = 1

    def on_start(self):
        """Setup admin token."""
        import os
        self.admin_token = os.environ.get(
            "ADMIN_TOKEN",
            "test_admin_token_with_minimum_32_characters_for_security"
        )

    @task(3)
    def cache_stats(self):
        """Get cache statistics."""
        self.client.get(
            "/api/v1/admin/cache/stats",
            headers={"X-Auth-Token": self.admin_token},
            name="/api/v1/admin/cache/stats"
        )

    @task(2)
    def llm_stats(self):
        """Get LLM usage statistics."""
        self.client.get(
            "/api/v1/admin/llm/stats",
            headers={"X-Auth-Token": self.admin_token},
            name="/api/v1/admin/llm/stats"
        )

    @task(1)
    def system_metrics(self):
        """Get system metrics."""
        self.client.get(
            "/api/v1/admin/metrics/system",
            headers={"X-Auth-Token": self.admin_token},
            name="/api/v1/admin/metrics/system"
        )


# Event handlers for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 60)
    print("Load test starting...")
    print("Target host:", environment.host)
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 60)
    print("Load test completed!")
    if environment.stats.total.num_requests > 0:
        print(f"Total requests: {environment.stats.total.num_requests}")
        print(f"Total failures: {environment.stats.total.num_failures}")
        print(f"Avg response time: {environment.stats.total.avg_response_time:.2f}ms")
        print(f"Requests/s: {environment.stats.total.current_rps:.2f}")
    print("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log slow requests."""
    if response_time > 5000:  # > 5 seconds
        print(f"SLOW REQUEST: {name} took {response_time:.0f}ms")
