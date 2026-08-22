import logging

from app.workers.metrics import NAMESPACE, WorkerMetrics, publish_or_log


class RecordingCloudWatch:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def put_metric_data(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(kwargs)


def test_worker_metrics_match_production_alarm_contract():
    client = RecordingCloudWatch()
    metrics = WorkerMetrics(client, service_name="ai-platform-prod-worker")

    metrics.publish(heartbeat_age_seconds=0, dead_letter_count=3)

    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["Namespace"] == NAMESPACE == "SystemNavigator/Production"
    by_name = {item["MetricName"]: item for item in request["MetricData"]}
    assert set(by_name) == {"WorkerHeartbeatAgeSeconds", "DeadLetterCount"}
    assert by_name["WorkerHeartbeatAgeSeconds"]["Value"] == 0
    assert by_name["WorkerHeartbeatAgeSeconds"]["Unit"] == "Seconds"
    assert by_name["DeadLetterCount"]["Value"] == 3
    assert by_name["DeadLetterCount"]["Unit"] == "Count"
    assert by_name["DeadLetterCount"]["Dimensions"] == [
        {"Name": "Environment", "Value": "production"},
        {"Name": "ServiceName", "Value": "ai-platform-prod-worker"},
    ]


def test_metric_failure_is_logged_without_stopping_worker(caplog):
    metrics = WorkerMetrics(
        RecordingCloudWatch(RuntimeError("AWS request failed secret=must-not-log")),
        service_name="ai-platform-prod-worker",
    )

    with caplog.at_level(logging.ERROR):
        publish_or_log(metrics, heartbeat_age_seconds=0, dead_letter_count=0)

    assert "WORKER_METRIC_EMISSION_FAILED" in caplog.text
    assert "secret" not in caplog.text.lower()
    assert "must-not-log" not in caplog.text
