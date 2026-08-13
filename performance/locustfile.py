import json
import os
from collections import defaultdict
from statistics import median

from locust import HttpUser, between, constant_throughput, events, task


timing_samples = defaultdict(list)


def percentile(values, quantile):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * quantile))]


@events.request.add_listener
def record_server_timing(
    request_type,
    name,
    response_time,
    response_length,
    response,
    exception,
    **_kwargs,
):
    if exception or response is None:
        return
    metrics = {
        "client": float(response_time),
        "response_size": float(response_length),
    }
    for item in response.headers.get("Server-Timing", "").split(","):
        metric, _, parameters = item.strip().partition(";")
        for parameter in parameters.split(";"):
            if parameter.startswith("dur="):
                metrics[metric] = float(parameter[4:])
            elif metric == "sql_count" and parameter.startswith('desc="'):
                metrics[metric] = float(parameter[6:-1])
    timing_samples[(request_type, name)].append(metrics)


@events.quitting.add_listener
def write_breakdown(environment=None, **_kwargs):
    output = os.getenv("PERFORMANCE_BREAKDOWN_FILE")
    if not output:
        return
    rows = []
    for (method, path), samples in sorted(timing_samples.items()):
        clients = [sample["client"] for sample in samples]
        row = {
            "method": method,
            "path": path,
            "request_count": len(samples),
            "p50": median(clients),
            "p95": percentile(clients, 0.95),
            "p99": percentile(clients, 0.99),
        }
        for metric in (
            "total",
            "query",
            "auth",
            "authorization",
            "db_session",
            "response_size",
            "sql_count",
        ):
            values = [sample.get(metric, 0.0) for sample in samples]
            row[metric] = sum(values) / len(values)
        rows.append(row)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump({"endpoints": rows}, stream, indent=2)


class PortalUser(HttpUser):
    wait_time = (
        constant_throughput(float(os.environ["TARGET_RPS_PER_USER"]))
        if os.getenv("TARGET_RPS_PER_USER")
        else between(0.1, 0.5)
    )

    def on_start(self):
        users = self.client.get(
            "/api/v1/auth/local/users", name="normal:login-users"
        ).json()
        login = self.client.post(
            "/api/v1/auth/local/login",
            json={
                "user_id": next(
                    (
                        u["id"]
                        for u in users
                        if u["email"] == "organization_owner@quality.local"
                    ),
                    users[0]["id"],
                )
            },
            name="normal:login",
        ).json()
        self.csrf = login["csrf_token"]
        me = self.client.get("/api/v1/auth/me", name="normal:me").json()
        self.org = me["organizations"][0]["id"]
        page = self.client.get(
            f"/api/v1/projects?organization_id={self.org}", name="list:projects"
        ).json()
        self.project = page["items"][0]["id"] if page["items"] else ""
        self.room = ""

    @task(3)
    def projects(self):
        self.client.get(
            f"/api/v1/projects?organization_id={self.org}", name="list:projects"
        )

    @task
    def project_detail(self):
        if self.project:
            self.client.get(
                f"/api/v1/projects/{self.project}", name="normal:project-detail"
            )

    @task(2)
    def notifications(self):
        self.client.get(
            f"/api/v1/notifications?organization_id={self.org}",
            name="list:notifications",
        )

    @task
    def chat_list(self):
        if self.room:
            self.client.get(
                f"/api/v1/chat-rooms/{self.room}/messages", name="list:chat-messages"
            )

    @task
    def chat_post(self):
        if self.room:
            self.client.post(
                f"/api/v1/chat-rooms/{self.room}/messages",
                name="normal:chat-post",
                headers={"X-CSRF-Token": self.csrf},
                json={"body": "local load message", "message_type": "user"},
            )

    @task
    def artifacts(self):
        self.client.get(
            f"/api/v1/artifacts?organization_id={self.org}", name="list:artifacts"
        )

    @task
    def reviews(self):
        self.client.get(
            f"/api/v1/reviews?organization_id={self.org}", name="list:reviews"
        )
