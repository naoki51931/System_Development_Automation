"""Request-local counters used only by the local performance-test mode."""

from __future__ import annotations

from contextvars import ContextVar
from time import perf_counter
from typing import Any


_request_timings: ContextVar[dict[str, float] | None] = ContextVar(
    "request_timings", default=None
)


def start_request_timing() -> tuple[Any, dict[str, float]]:
    timings: dict[str, float] = {"sql_count": 0.0}
    return _request_timings.set(timings), timings


def reset_request_timing(token: Any) -> None:
    _request_timings.reset(token)


def current_timings() -> dict[str, float] | None:
    return _request_timings.get()


def add_duration(name: str, started_at: float) -> None:
    timings = current_timings()
    if timings is not None:
        timings[name] = timings.get(name, 0.0) + (perf_counter() - started_at) * 1000
