"""Time-series metrics for services and databases."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import TimeWindow, Tool, ToolOutput


class MetricQuery(TimeWindow):
    service: str = Field(description="Service or database name, e.g. payments-db")
    metric: str | None = Field(None, description="Metric name; omit to return every metric for the service")


def _num(v: float) -> float:
    return round(v, 2)


class QueryMetricsTool(Tool):
    name = "query_metrics"
    description = (
        "Fetch 5-minute-resolution metric series for a service. Application services expose request_rate, "
        "error_rate, latency_p99_ms, cpu_pct, memory_pct (some have extras); databases expose cpu_pct, "
        "connections, disk_used_pct, replication_lag_s, query_latency_p99_ms. Each series (evidence `id`) "
        "includes its points and min/max/mean, the time of the maximum, and first/last values."
    )
    Input = MetricQuery

    def run(self, data: dict[str, Any], q: MetricQuery) -> ToolOutput:
        series = [s for s in data["metrics"] if s["service"] == q.service]
        if not series:
            services = sorted({s["service"] for s in data["metrics"]})
            return ToolOutput(note=f"No metrics for '{q.service}'. Services with metrics: {', '.join(services)}")
        if q.metric:
            available = sorted(s["metric"] for s in series)
            series = [s for s in series if s["metric"] == q.metric]
            if not series:
                return ToolOutput(note=f"No metric '{q.metric}' for {q.service}. Available: {', '.join(available)}")
        records = []
        for s in series:
            points = [p for p in s["points"] if q.in_window(p[0])]
            if not points:
                continue
            values = [p[1] for p in points]
            peak = max(points, key=lambda p: p[1])
            records.append({
                "id": s["id"],
                "service": s["service"],
                "metric": s["metric"],
                "unit": s["unit"],
                "points": points,
                "stats": {
                    "first": _num(values[0]),
                    "last": _num(values[-1]),
                    "min": _num(min(values)),
                    "max": _num(max(values)),
                    "mean": _num(sum(values) / len(values)),
                    "max_at": peak[0],
                },
            })
        note = f"{len(records)} series" if records else "No data points in the requested window"
        return ToolOutput(records=records, note=note)

    def summarize(self, r: dict[str, Any]) -> str:
        s = r["stats"]
        trend = ", ".join(f"{p[0][11:16]}={_num(p[1])}" for p in r["points"][:: max(1, len(r["points"]) // 6)])
        return (f"metric {r['service']} {r['metric']} [{r['unit']}]: first {s['first']}, max {s['max']} at "
                f"{s['max_at']}, last {s['last']} (samples: {trend})")
