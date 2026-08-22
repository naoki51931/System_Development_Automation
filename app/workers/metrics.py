import logging
import os


LOGGER = logging.getLogger(__name__)
NAMESPACE = "SystemNavigator/Production"
ENVIRONMENT = "production"


class WorkerMetrics:
    def __init__(self, client=None, *, namespace=NAMESPACE, service_name=None):
        if client is None:
            import boto3

            client = boto3.client("cloudwatch")
        self.client = client
        self.namespace = namespace
        self.service_name = service_name or os.getenv(
            "APP_WORKER_SERVICE_NAME", "ai-platform-prod-worker"
        )

    def publish(self, *, heartbeat_age_seconds: float, dead_letter_count: int) -> None:
        dimensions = [
            {"Name": "Environment", "Value": ENVIRONMENT},
            {"Name": "ServiceName", "Value": self.service_name},
        ]
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    "MetricName": "WorkerHeartbeatAgeSeconds",
                    "Dimensions": dimensions,
                    "Value": max(0.0, float(heartbeat_age_seconds)),
                    "Unit": "Seconds",
                },
                {
                    "MetricName": "DeadLetterCount",
                    "Dimensions": dimensions,
                    "Value": int(dead_letter_count),
                    "Unit": "Count",
                },
            ],
        )


def production_metrics_from_environment():
    if os.getenv("APP_ENV") != ENVIRONMENT:
        return None
    namespace = os.getenv("APP_WORKER_METRICS_NAMESPACE", NAMESPACE)
    if namespace != NAMESPACE:
        raise RuntimeError("Production worker metric namespace is fixed")
    return WorkerMetrics(namespace=namespace)


def publish_or_log(metrics, *, heartbeat_age_seconds: float, dead_letter_count: int):
    if metrics is None:
        return
    try:
        metrics.publish(
            heartbeat_age_seconds=heartbeat_age_seconds,
            dead_letter_count=dead_letter_count,
        )
    except Exception:
        # Monitoring failure must be visible without terminating job processing.
        # Do not include an SDK exception body: it can contain request metadata.
        LOGGER.error("WORKER_METRIC_EMISSION_FAILED")
