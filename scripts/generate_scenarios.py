"""Generate the synthetic incident scenarios (data/incidents/) and their ground truth (data/ground_truth/).

Each scenario below is a declarative spec: the injected signals (metric anomalies, log lines, changes,
health checks, past incidents), which of them are key or deliberately misleading, tool faults, and the
ground truth. The generator adds seeded background noise (normal traffic logs, benign warnings, noisy
metrics, unrelated changes and postmortems) so signals must be found among normal data. Output is
deterministic: re-running reproduces identical files.

    python scripts/generate_scenarios.py
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WINDOW_START, WINDOW_END, STEP = -60, 30, 5  # minutes relative to incident onset (t0)

BASELINES: dict[str, dict[str, float]] = {
    "api-gateway": {"request_rate": 420, "error_rate": 0.4, "latency_p99_ms": 180, "cpu_pct": 38, "memory_pct": 52},
    "checkout-service": {"request_rate": 85, "error_rate": 0.3, "latency_p99_ms": 320, "cpu_pct": 41, "memory_pct": 58},
    "payment-service": {"request_rate": 60, "error_rate": 0.2, "latency_p99_ms": 450, "cpu_pct": 33, "memory_pct": 55},
    "inventory-service": {"request_rate": 140, "error_rate": 0.2, "latency_p99_ms": 90, "cpu_pct": 30, "memory_pct": 49},
    # auth-service traffic is the share of caller requests that need a live token check (cached tokens skip it)
    "auth-service": {"request_rate": 80, "error_rate": 0.1, "latency_p99_ms": 40, "cpu_pct": 25, "memory_pct": 44},
    "search-service": {"request_rate": 150, "error_rate": 0.2, "latency_p99_ms": 210, "cpu_pct": 46, "memory_pct": 61},
    "notification-worker": {"request_rate": 30, "error_rate": 0.2, "latency_p99_ms": 900, "cpu_pct": 22, "memory_pct": 48, "queue_lag_s": 4},
    "payments-db": {"cpu_pct": 35, "connections": 120, "disk_used_pct": 61, "replication_lag_s": 0.4, "query_latency_p99_ms": 12},
    "inventory-db": {"cpu_pct": 30, "connections": 90, "disk_used_pct": 54, "replication_lag_s": 0.3, "query_latency_p99_ms": 9},
}
UNITS = {
    "request_rate": "req/s", "error_rate": "%", "latency_p99_ms": "ms", "cpu_pct": "%", "memory_pct": "%",
    "queue_lag_s": "s", "connections": "count", "disk_used_pct": "%", "replication_lag_s": "s",
    "query_latency_p99_ms": "ms", "restarts": "count",
}
INTEGER_METRICS = {"connections", "restarts"}

EDGES = [
    ("api-gateway", "checkout-service", "sync_http"), ("api-gateway", "search-service", "sync_http"),
    ("api-gateway", "auth-service", "sync_http"), ("checkout-service", "payment-service", "sync_http"),
    ("checkout-service", "inventory-service", "sync_http"), ("checkout-service", "auth-service", "sync_http"),
    ("checkout-service", "notification-queue", "queue"), ("payment-service", "payments-db", "database"),
    ("payment-service", "payment-provider", "external_http"), ("inventory-service", "inventory-db", "database"),
    ("inventory-service", "inventory-cache", "cache"), ("notification-worker", "notification-queue", "queue"),
    ("notification-worker", "email-provider", "external_http"), ("search-service", "search-index", "sync_http"),
]
HEALTHY_DETAIL = {
    "payment-provider": "status page: all systems operational",
    "email-provider": "status page: all systems operational",
    "payments-db": "accepting connections; SELECT 1 ok",
    "inventory-db": "accepting connections; SELECT 1 ok",
}

BACKGROUND_LOGS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "api-gateway": (
        ["GET /api/v1/products 200 {ms}ms", "POST /api/v1/checkout 200 {ms}ms", "GET /api/v1/search 200 {ms}ms", "POST /api/v1/login 200 {ms}ms"],
        ["upstream response slow: {slow}ms (route=/api/v1/search)", "rate limiter: client {id} near burst limit"],
        ["client closed connection before response (499) route=/api/v1/products"],
    ),
    "checkout-service": (
        ["order {id} created in {ms}ms", "cart {id} priced in {ms}ms", "GET /cart/{id} 200 {ms}ms"],
        ["slow inventory reservation: {slow}ms for cart {id}", "retrying idempotent call to payment-service (attempt 2)"],
        ["order {id} rejected: card declined by issuer"],
    ),
    "payment-service": (
        ["charge {id} authorized in {ms}ms", "refund {id} processed", "POST /charges 201 {ms}ms"],
        ["payment-provider responded in {slow}ms for charge {id}"],
        ["charge {id} failed: insufficient funds (declined)"],
    ),
    "inventory-service": (
        ["reserved 2 units for cart {id}", "stock lookup sku={id} in {ms}ms", "cache hit ratio 0.9{n}"],
        ["cache miss storm for sku prefix {id}: {n} misses/s"],
        ["reservation {id} expired before confirmation"],
    ),
    "auth-service": (
        ["token issued for user {id}", "token validated for user {id} in {ms}ms", "session refreshed for user {id}"],
        ["login failed for user {id}: bad password"],
        ["rejected malformed Authorization header from {id}"],
    ),
    "search-service": (
        ["query 'shoes' served in {ms}ms", "query 'jacket' served in {ms}ms", "suggestions served in {ms}ms"],
        ["search-index shard 3 responded in {slow}ms"],
        ["query parse error: unbalanced quotes"],
    ),
    "notification-worker": (
        ["sent order confirmation for order {id}", "batch of 100 messages processed in {ms}ms"],
        ["email-provider responded in {slow}ms"],
        ["bounce for recipient {id}@example.com"],
    ),
    "payments-db": (
        ["checkpoint complete: wrote {n}12 buffers", "autovacuum: processing table public.payments"],
        ["slow query {slow}ms: SELECT * FROM refunds WHERE created_at > $1"],
        ["canceling statement due to user request"],
    ),
    "inventory-db": (
        ["checkpoint complete: wrote {n}40 buffers", "autovacuum: processing table public.stock_levels"],
        ["slow query {slow}ms: SELECT sku, qty FROM stock_levels WHERE warehouse_id = $1"],
        ["canceling statement due to user request"],
    ),
}

DAY = 24 * 60
BACKGROUND_CHANGES = [
    (-6 * DAY - 200, "api-gateway", "deploy", "Deploy v7.4.2: upgrade TLS library; minor routing fixes", "v7.4.2", "deploy-bot"),
    (-5 * DAY + 90, "auth-service", "config_change", "Lower log level for /healthz from INFO to WARN", None, "s.okafor"),
    (-3 * DAY - 240, "inventory-service", "deploy", "Deploy v4.1.9: add SKU bulk lookup endpoint", "v4.1.9", "deploy-bot"),
    (-2 * DAY + 30, "search-service", "deploy", "Deploy v5.3.1: query parser fixes", "v5.3.1", "deploy-bot"),
    (-DAY - 360, "payment-service", "deploy", "Deploy v3.1.3: refund flow improvements", "v3.1.3", "deploy-bot"),
    (-DAY - 120, "notification-worker", "config_change", "Increase send batch size 50 -> 100", None, "m.chen"),
    (-20 * 60, "checkout-service", "deploy", "Deploy v2.13.4: cart page performance tweaks", "v2.13.4", "deploy-bot"),
    (-9 * 60, "platform", "infra", "Kubernetes node pool upgrade 1.30 -> 1.31 completed; all nodes Ready", None, "platform-team"),
]

BASE_PAST = [
    ("2026-01-14", "API gateway 502s during node pool upgrade", ["api-gateway"], "gateway 502 errors, pod restarts during node drain", "Node drain without PodDisruptionBudget", "Added PodDisruptionBudgets"),
    ("2026-02-27", "Search latency spike from index rebuild", ["search-service", "search-index"], "search p99 latency high, gateway slow upstream warnings", "Index rebuild scheduled during peak traffic", "Moved rebuilds off-peak"),
    ("2026-04-03", "Inventory reservation failures from cache eviction storm", ["inventory-service", "inventory-cache"], "inventory errors, cache misses, high database load", "Cache memory limit too low after catalogue growth", "Increased cache memory, added eviction alert"),
    ("2026-05-30", "Auth latency after signing key rotation", ["auth-service"], "login latency, token validation errors", "Key rotation caused public-key cache misses", "Pre-warm key cache before rotation"),
    ("2026-06-11", "Checkout errors from expired TLS certificate on payment-service", ["payment-service", "checkout-service"], "TLS handshake failures, checkout 5xx errors", "Certificate not renewed due to cert-manager misconfiguration", "Renewed certificate; added expiry alerting"),
    ("2026-08-08", "Payment timeouts from payments-db connection exhaustion", ["payment-service", "payments-db"], "payment timeouts, connection pool waits, slow queries", "Connection leak in nightly batch job", "Fixed leak; added pool saturation alerts"),
]


@dataclass
class M:  # metric effect; the last applicable effect for a timestamp wins
    service: str
    metric: str
    start: int
    value: float
    shape: str = "step"  # step | ramp | spike
    end: int | None = None
    start_value: float | None = None
    key: bool = False
    decoy: bool = False


@dataclass
class L:  # injected log signal
    service: str
    level: str
    message: str
    start: int
    end: int
    count: int
    key: bool = False
    decoy: bool = False


@dataclass
class C:  # change record
    offset: int
    service: str
    type: str
    description: str
    version: str | None = None
    author: str = "deploy-bot"
    key: bool = False
    decoy: bool = False


@dataclass
class H:  # health-check override
    service: str
    status: str
    detail: str
    key: bool = False
    decoy: bool = False


@dataclass
class P:  # past incident
    date: str
    title: str
    services: list[str]
    symptoms: str
    root_cause: str
    resolution: str
    key: bool = False
    decoy: bool = False


@dataclass
class Spec:
    id: str
    title: str
    t0: datetime
    alert: str
    affected: list[str]
    summary: str
    services: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    inconclusive: bool = False
    metrics: list[M] = field(default_factory=list)
    logs: list[L] = field(default_factory=list)
    changes: list[C] = field(default_factory=list)
    health: list[H] = field(default_factory=list)
    past: list[P] = field(default_factory=list)
    faults: list[dict] = field(default_factory=list)
    decoys: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


SPECS = [
    Spec(
        "S01", "api-gateway 5xx spike on checkout", utc(2026, 9, 1, 14, 0),
        "ALERT [P1] api-gateway 5xx rate 6.2% (threshold 2%) for 5 minutes, starting ~14:00 UTC. Checkout conversion down 40%.",
        ["api-gateway", "checkout-service"],
        "checkout-service v2.14.0 (new discount engine) throws NullPointerException on every discounted cart.",
        services=["checkout-service"], categories=["deployment_regression"], tags=["baseline_case"],
        changes=[C(-4, "checkout-service", "deploy", "Deploy v2.14.0: new discount engine replaces legacy pricing rules", "v2.14.0", key=True)],
        metrics=[M("checkout-service", "error_rate", 0, 18.5, key=True), M("api-gateway", "error_rate", 0, 6.2),
                 M("checkout-service", "latency_p99_ms", 0, 410)],
        logs=[L("checkout-service", "ERROR", "NullPointerException at com.shop.checkout.discount.DiscountEngine.apply(DiscountEngine.java:88) cart_id={id}", 0, 30, 40, key=True),
              L("api-gateway", "ERROR", "upstream checkout-service returned 500 for POST /api/v1/checkout", 0, 30, 25),
              L("checkout-service", "INFO", "Starting checkout-service v2.14.0 (build 8f3a2c1)", -4, -3, 3)],
        past=[P("2026-05-12", "Checkout 500s after pricing deploy", ["checkout-service"], "NullPointerException in pricing module; checkout 5xx errors", "Unhandled null coupon field in new pricing code", "Rolled back; added null checks", key=True)],
    ),
    Spec(
        "S02", "payment failures at checkout", utc(2026, 9, 2, 10, 0),
        "ALERT [P1] checkout-service payment step failing: error rate 12% since ~10:00 UTC; payment-service 5xx elevated.",
        ["checkout-service", "payment-service"],
        "A config change cut payment-service's DB pool acquire timeout from 5000 ms to 50 ms; requests fail fast while payments-db is healthy.",
        services=["payment-service"], categories=["config_error"], tags=["conflicting_evidence", "misleading_history"],
        changes=[C(-2, "payment-service", "config_change", "Set db.pool.connection_timeout_ms 5000 -> 50 (ticket OPS-2291: reduce tail latency)", None, "j.alvarez", key=True)],
        metrics=[M("payment-service", "error_rate", 0, 27, key=True), M("checkout-service", "error_rate", 0, 12),
                 M("api-gateway", "error_rate", 0, 4.1), M("payment-service", "latency_p99_ms", 0, 140)],
        logs=[L("payment-service", "ERROR", "Timeout acquiring connection from pool 'payments-db' after 50ms (active=12, idle=0, waiting=31)", 0, 30, 45, key=True),
              L("checkout-service", "WARN", "payment-service call failed: 503 Service Unavailable (order {id})", 0, 30, 25),
              L("payments-db", "WARN", "slow query 820ms: SELECT * FROM payments WHERE merchant_id = $1 ORDER BY created_at", -50, 25, 6, decoy=True)],
        decoys=[{"service": "payments-db", "category": "resource_exhaustion"}],
    ),
    Spec(
        "S03", "order emails delayed", utc(2026, 9, 3, 10, 0),
        "ALERT [P2] notification-queue consumer lag above 15 minutes (threshold 5m) since ~10:00 UTC; order confirmation emails delayed.",
        ["notification-worker"],
        "notification-worker v1.8.0 (deployed 3 days earlier) caches rendered templates without bound; heap exhaustion causes OOM kills and a growing backlog.",
        services=["notification-worker"], categories=["resource_exhaustion", "deployment_regression"], tags=["slow_onset", "misleading_dependency"],
        changes=[C(-3 * DAY, "notification-worker", "deploy", "Deploy v1.8.0: cache rendered email templates in-process", "v1.8.0", key=True)],
        metrics=[M("notification-worker", "memory_pct", -60, 97, "ramp", end=-10, start_value=80, key=True),
                 M("notification-worker", "memory_pct", -5, 88, "ramp", end=30, start_value=52, key=True),
                 M("notification-worker", "restarts", -5, 1, key=True), M("notification-worker", "restarts", 10, 2, key=True),
                 M("notification-worker", "restarts", 25, 3, key=True),
                 M("notification-worker", "queue_lag_s", -5, 960, "ramp", end=30, key=True),
                 M("notification-worker", "request_rate", -5, 6)],
        logs=[L("notification-worker", "WARN", "GC overhead high: 92% of time spent in GC over last 60s", -30, -6, 10, key=True),
              L("notification-worker", "ERROR", "java.lang.OutOfMemoryError: Java heap space at TemplateCache.put(TemplateCache.java:57)", -6, 25, 8, key=True),
              L("notification-worker", "ERROR", "container notification-worker-7c9d terminated: OOMKilled (limit 2Gi)", -5, 25, 3, key=True),
              L("notification-worker", "WARN", "email-provider responded slowly: 2400ms", -40, 20, 5, decoy=True)],
        health=[H("email-provider", "degraded", "status page: elevated latency in eu-west region", decoy=True)],
        past=[P("2026-06-20", "Email delays caused by email-provider outage", ["notification-worker", "email-provider"], "notification queue lag, email send timeouts", "Third-party email provider outage", "Waited for provider recovery; added secondary provider", decoy=True)],
        decoys=[{"service": "email-provider", "category": "dependency_failure"}],
    ),
    Spec(
        "S04", "checkout and payment errors", utc(2026, 9, 4, 16, 0),
        "ALERT [P1] checkout-service error rate 21% and api-gateway 5xx 8% since ~16:00 UTC. Customers report failed payments.",
        ["checkout-service", "api-gateway"],
        "The external payment provider's Charges API is failing (503s); payment-service opens its circuit breaker and errors cascade to checkout and the gateway.",
        services=["payment-provider"], categories=["dependency_failure"], tags=["cascading_failure", "misleading_volume"],
        changes=[C(-20, "search-service", "deploy", "Deploy v5.3.2: ranking model refresh", "v5.3.2", decoy=True)],
        metrics=[M("payment-service", "error_rate", 0, 41, key=True), M("payment-service", "latency_p99_ms", 0, 10000, key=True),
                 M("checkout-service", "error_rate", 0, 21), M("api-gateway", "error_rate", 0, 8)],
        logs=[L("payment-service", "ERROR", "POST https://api.payprovider.example/v2/charges failed: 503 Service Unavailable (attempt 3/3)", 0, 30, 35, key=True),
              L("payment-service", "WARN", "circuit breaker 'payment-provider' state change CLOSED -> OPEN", 2, 25, 4, key=True),
              L("checkout-service", "ERROR", "order {id} failed: payment-service returned 502 Bad Gateway", 0, 30, 60, decoy=True),
              L("api-gateway", "ERROR", "upstream checkout-service returned 502 for POST /api/v1/checkout", 0, 30, 30)],
        health=[H("payment-provider", "degraded", "status page: 'Elevated error rates on Charges API' (investigating)", key=True)],
        past=[P("2026-03-19", "Checkout failures from checkout-service thread pool exhaustion", ["checkout-service"], "checkout 5xx errors, 502s at gateway", "Thread pool misconfiguration in checkout-service", "Raised pool size", decoy=True)],
        decoys=[{"service": "checkout-service", "category": "resource_exhaustion"}, {"service": "checkout-service", "category": "deployment_regression"}],
    ),
    Spec(
        "S05", "sign-in and checkout failures", utc(2026, 9, 5, 9, 0),
        "ALERT [P1] checkout-service error rate 33% since ~09:00 UTC; users cannot sign in or complete checkout. A checkout-service deploy went out at 08:54 UTC.",
        ["checkout-service", "api-gateway"],
        "auth-service's TLS certificate expired at 08:59:59 after a failed renewal; callers fail TLS handshakes. The checkout deploy only changed UI strings.",
        services=["auth-service"], categories=["certificate_expiry"], tags=["misleading_deploy", "conflicting_evidence"],
        changes=[C(-6, "checkout-service", "deploy", "Deploy v2.15.1: update checkout button copy and translations (static strings only)", "v2.15.1", decoy=True)],
        # Only plaintext admin/health traffic still reaches auth-service; every TLS handshake on 8443 fails.
        metrics=[M("auth-service", "request_rate", 0, 3, key=True), M("checkout-service", "error_rate", 0, 33),
                 M("api-gateway", "error_rate", 0, 11)],
        logs=[L("auth-service", "WARN", "certificate renewal for cn=auth.internal failed: ACME order rejected (rate limited); current certificate expires 2026-09-05T08:59:59Z", -55, -40, 2, key=True),
              L("checkout-service", "ERROR", "auth-service token validation failed: javax.net.ssl.SSLHandshakeException: PKIX path validation failed: "
                "java.security.cert.CertPathValidatorException: validity check failed (peer auth.internal:8443)", 0, 30, 45, key=True),
              L("api-gateway", "ERROR", "auth check failed: x509: certificate has expired or is not yet valid: current time is after 2026-09-05T08:59:59Z (cn=auth.internal)", 0, 30, 20, key=True),
              L("checkout-service", "INFO", "Starting checkout-service v2.15.1 (build 1c77e0a)", -6, -5, 3, decoy=True)],
        health=[H("auth-service", "healthy", "HTTP /health 200 on plaintext admin port 8080")],
        past=[P("2026-04-18", "Checkout errors after checkout-service v2.9.0 deploy", ["checkout-service"], "checkout 5xx errors immediately after deploy", "Serialization bug in new release", "Rolled back v2.9.0", decoy=True)],
        decoys=[{"service": "checkout-service", "category": "deployment_regression"}],
    ),
    Spec(
        "S06", "stock reservation failures", utc(2026, 9, 6, 13, 0),
        "ALERT [P2] inventory-service error rate 15% since ~13:00 UTC; stock reservations failing at checkout. inventory-service health checks are green.",
        ["inventory-service", "checkout-service"],
        "inventory-db's primary became unreachable; the endpoint now points at a standby still in recovery (read-only), so all writes fail while reads work.",
        services=["inventory-db"], categories=["infrastructure_failure"], tags=["conflicting_evidence", "shallow_health_check"],
        metrics=[M("inventory-service", "error_rate", 0, 15, key=True),
                 M("inventory-db", "replication_lag_s", -1, 48, "spike", end=5, key=True),
                 M("inventory-db", "connections", 0, 20), M("inventory-db", "connections", 10, 85),
                 M("checkout-service", "error_rate", 0, 7),
                 M("inventory-service", "memory_pct", -60, 91, decoy=True)],
        logs=[L("inventory-db", "ERROR", "replication: lost connection to primary db-inv-1 (timeout after 10s)", -1, 0, 2, key=True),
              L("inventory-db", "INFO", "standby db-inv-2 still in recovery: promotion pending manual approval", 3, 25, 4, key=True),
              L("inventory-service", "ERROR", "UPDATE stock_reservations failed: ERROR: cannot execute UPDATE in a read-only transaction (SQLSTATE 25006)", 0, 30, 40, key=True),
              L("inventory-service", "WARN", "high heap usage: 91% of 1Gi", -50, 25, 5, decoy=True)],
        health=[H("inventory-service", "healthy", "HTTP /health 200 (checks process liveness only, not database writes)"),
                H("inventory-db", "degraded", "primary endpoint resolves to db-inv-2 (standby, read-only)", key=True)],
        decoys=[{"service": "inventory-service", "category": "resource_exhaustion"}],
    ),
    Spec(
        "S07", "checkout latency and 503s", utc(2026, 9, 7, 18, 0),
        "ALERT [P2] checkout-service p99 latency 2.9s (SLO 800ms) and elevated 503s since ~18:00 UTC.",
        ["checkout-service", "api-gateway"],
        "A marketing campaign (email blast + homepage banner at 18:00) quadrupled traffic; checkout hit its autoscaling ceiling and saturated.",
        services=["checkout-service", "api-gateway"], categories=["traffic_surge"], tags=["misleading_deploy"],
        changes=[C(-35, "inventory-service", "deploy", "Deploy v4.2.0: bump HTTP client library", "v4.2.0", decoy=True),
                 C(-5, "api-gateway", "feature_flag", "Enable 'fall-sale' homepage banner (marketing campaign launch; email blast to 2.1M customers at 18:00)", None, "marketing-ops", key=True)],
        metrics=[M("api-gateway", "request_rate", 0, 1650, key=True), M("checkout-service", "request_rate", 0, 340, key=True),
                 M("checkout-service", "cpu_pct", 0, 96, key=True), M("checkout-service", "latency_p99_ms", 0, 2900),
                 M("checkout-service", "error_rate", 0, 5.5), M("inventory-service", "request_rate", 0, 520),
                 M("inventory-service", "latency_p99_ms", 0, 140)],
        logs=[L("checkout-service", "WARN", "HPA checkout-service: desired replicas 34 exceeds maxReplicas 20", 2, 30, 8, key=True),
              L("checkout-service", "ERROR", "rejecting request: worker pool saturated (queue 500/500) -> 503", 3, 30, 30, key=True),
              L("inventory-service", "INFO", "Starting inventory-service v4.2.0 (build 77ab01e)", -35, -34, 2, decoy=True)],
        decoys=[{"service": "inventory-service", "category": "deployment_regression"}],
    ),
    Spec(
        "S08", "payment-service errors", utc(2026, 9, 8, 11, 0),
        "ALERT [P1] payment-service error rate 22% since ~11:00 UTC; payments failing.",
        ["payment-service", "checkout-service"],
        "payment-service v3.2.0 writes an idempotency_key column whose migration was never applied. The log backend times out for payment-service, so the cause must be inferred from changes and metrics.",
        services=["payment-service"], categories=["deployment_regression"], tags=["tool_failure"],
        changes=[C(-3, "payment-service", "deploy", "Deploy v3.2.0: add idempotency_key to payments table writes; ORM upgrade 5.x -> 6.x (schema migration run separately)", "v3.2.0", key=True)],
        metrics=[M("payment-service", "error_rate", 0, 22, key=True), M("checkout-service", "error_rate", 0, 9)],
        logs=[L("payment-service", "ERROR", 'INSERT INTO payments failed: column "idempotency_key" of relation "payments" does not exist', 0, 30, 40),
              L("checkout-service", "WARN", "payment-service returned 500 Internal Server Error for order {id}", 0, 30, 25, key=True)],
        past=[P("2026-02-11", "Payment failures after ORM migration", ["payment-service"], "payment-service 500 errors after deploy; SQL column errors", "Deploy shipped before its schema migration was applied", "Applied migration; added deploy gate", key=True)],
        faults=[{"tool": "query_logs", "mode": "timeout", "when": {"service": "payment-service"}, "message": "log backend query for payment-service exceeded deadline"}],
    ),
    Spec(
        "S09", "inventory latency", utc(2026, 9, 9, 15, 0),
        "ALERT [P2] inventory-service p99 latency 2.4s (SLO 300ms) since ~15:00 UTC; checkout pages slow.",
        ["inventory-service", "checkout-service"],
        "Feature flag realtime_stock_recalc was raised from 5% to 100%, making every request recompute stock; inventory-service CPU saturates. Metrics first return partial data and change history fails once.",
        services=["inventory-service"], categories=["config_error"], tags=["tool_failure", "partial_results"],
        changes=[C(-5, "inventory-service", "feature_flag", "Enable realtime_stock_recalc for 100% of traffic (previously 5%)", None, "p.nguyen", key=True)],
        metrics=[M("inventory-service", "cpu_pct", 0, 97, key=True), M("inventory-service", "latency_p99_ms", 0, 2400, key=True),
                 M("inventory-service", "error_rate", 0, 9), M("inventory-db", "cpu_pct", 0, 62),
                 M("checkout-service", "latency_p99_ms", 0, 2600)],
        logs=[L("inventory-service", "WARN", "request exceeded deadline 2000ms in StockRecalculator.recomputeAll (sku_count=48211)", 0, 30, 30, key=True),
              L("inventory-db", "WARN", "slow query 1900ms: SELECT sku, qty FROM stock_levels", 0, 30, 8)],
        faults=[{"tool": "query_metrics", "mode": "partial", "when": {"service": "inventory-service"}, "fail_attempts": 1, "message": "metrics shard unavailable"},
                {"tool": "get_change_history", "mode": "error", "fail_attempts": 1, "recoverable": True, "message": "change-history API returned 503"}],
        decoys=[{"service": "inventory-db", "category": "resource_exhaustion"}],
    ),
    Spec(
        "S10", "brief gateway latency blip", utc(2026, 9, 10, 20, 0),
        "ALERT [P3] api-gateway p99 latency 1.6s (threshold 1.5s) for ~4 minutes around 20:00 UTC; auto-resolved at 20:05 UTC. No customer reports.",
        ["api-gateway"],
        "A short latency blip with no errors, no changes and no telemetry for the most likely upstream (search-service). The evidence cannot determine a cause.",
        inconclusive=True, tags=["insufficient_evidence", "tool_failure"],
        metrics=[M("api-gateway", "latency_p99_ms", 0, 1620, "spike", end=0)],
        logs=[L("api-gateway", "WARN", "upstream response slow: {slow}ms (route=/api/v1/search)", -1, 3, 3)],
        faults=[{"tool": "query_metrics", "mode": "error", "when": {"service": "search-service"}, "recoverable": False, "message": "metrics for search-service unavailable (retention gap)"},
                {"tool": "query_logs", "mode": "timeout", "when": {"service": "search-service"}, "message": "log backend query for search-service exceeded deadline"}],
    ),
    Spec(
        "S11", "payment write failures", utc(2026, 9, 11, 12, 0),
        "ALERT [P1] payment-service error rate 30% since ~12:00 UTC. payment-service was deployed earlier today.",
        ["payment-service", "checkout-service"],
        "payments-db ran out of disk because WAL archiving was failing; inserts fail with 'No space left on device'. The earlier payment-service deploy and a similar past incident are red herrings.",
        services=["payments-db"], categories=["resource_exhaustion"], tags=["misleading_history", "misleading_deploy"],
        changes=[C(-125, "payment-service", "deploy", "Deploy v3.1.4: more detailed request logging", "v3.1.4", decoy=True)],
        metrics=[M("payments-db", "disk_used_pct", -60, 100, "ramp", end=-1, start_value=88, key=True),
                 M("payment-service", "error_rate", 0, 30, key=True), M("checkout-service", "error_rate", 0, 13)],
        logs=[L("payments-db", "WARN", "archive command failed for WAL segment 0000000100000A2F000000{n}; WAL files accumulating", -60, -5, 6, key=True),
              L("payments-db", "ERROR", 'could not extend file "base/16384/24576": No space left on device', -1, 30, 20, key=True),
              L("payment-service", "ERROR", "INSERT INTO payments failed: could not extend file: No space left on device (SQLSTATE 53100)", 0, 30, 35, key=True)],
        health=[H("payments-db", "healthy", "accepting connections; SELECT 1 ok")],
        past=[P("2026-07-30", "Payment failures after payment-service deploy v3.0.9", ["payment-service"], "payment-service 5xx errors after deploy; insert failures", "Regression in new release", "Rolled back v3.0.9", decoy=True)],
        decoys=[{"service": "payment-service", "category": "deployment_regression"}],
    ),
    Spec(
        "S12", "users signed out and throttled", utc(2026, 9, 12, 17, 0),
        "ALERT [P2] api-gateway 4xx rate 14% (baseline 1%) since ~17:00 UTC; users report being signed out and seeing 'too many requests' errors.",
        ["api-gateway"],
        "Two plausible simultaneous changes (auth token format v2 and a gateway rate-limit change) and api-gateway logs are inaccessible, so the evidence cannot separate them.",
        inconclusive=True, tags=["ambiguous", "tool_failure", "conflicting_evidence"],
        changes=[C(-3, "auth-service", "deploy", "Deploy v4.0.0: issue session tokens in format v2 (v1 still accepted during migration)", "v4.0.0"),
                 C(-3, "api-gateway", "config_change", "Update rate-limit policy: /api/* burst 200 -> 20 per client", None, "netops")],
        metrics=[M("api-gateway", "error_rate", 0, 14), M("checkout-service", "request_rate", 0, 60),
                 M("auth-service", "request_rate", 0, 105)],
        logs=[L("auth-service", "INFO", "issued session token format=v2 for user {id}", 0, 30, 15),
              L("auth-service", "WARN", "token refresh requested for expired or invalid session {id}", 0, 30, 10)],
        faults=[{"tool": "query_logs", "mode": "error", "when": {"service": "api-gateway"}, "recoverable": False, "message": "access denied: log index 'api-gateway-*' requires elevated permissions"}],
    ),
]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fill(template: str, rng: random.Random) -> str:
    return (template.replace("{ms}", str(rng.randint(18, 380)))
            .replace("{slow}", str(rng.randint(600, 1450)))
            .replace("{id}", f"{rng.getrandbits(32):08x}")
            .replace("{n}", str(rng.randint(10, 99))))


def noisy(value: float, metric: str, rng: random.Random) -> float:
    if metric == "restarts":
        return value
    if metric == "error_rate":
        return max(0.0, value * rng.uniform(0.93, 1.07) + rng.uniform(-0.05, 0.05))
    v = value * rng.uniform(0.96, 1.04)
    return float(round(v)) if metric in INTEGER_METRICS else v


def metric_value(spec: Spec, service: str, metric: str, t: float) -> float | None:
    """Noise-free value of a metric at t minutes after onset (the last applicable effect wins)."""
    effects = [e for e in spec.metrics if (e.service, e.metric) == (service, metric)]
    base = BASELINES.get(service, {}).get(metric)
    if base is None and not effects:
        return None
    base = base or 0.0
    value = base
    for e in effects:
        if t < e.start:
            continue
        if e.shape == "ramp":
            sv = base if e.start_value is None else e.start_value
            frac = 1.0 if e.end is None or t >= e.end else (t - e.start) / (e.end - e.start)
            value = sv + (e.value - sv) * frac
        elif e.end is None or t <= e.end:
            value = e.value
    return value


def build_metrics(spec: Spec, rng: random.Random) -> tuple[list[dict], list[list[str]], list[list[str]]]:
    times = list(range(WINDOW_START, WINDOW_END + 1, STEP))
    bases = {(svc, m): v for svc, ms in BASELINES.items() for m, v in ms.items()}
    for e in spec.metrics:
        bases.setdefault((e.service, e.metric), 0.0)
    records, key, decoy = [], [], []
    for i, (svc, metric) in enumerate(sorted(bases), 1):
        effects = [e for e in spec.metrics if (e.service, e.metric) == (svc, metric)]
        points = [[iso(spec.t0 + timedelta(minutes=t)), round(noisy(metric_value(spec, svc, metric, t), metric, rng), 2)]
                  for t in times]
        rid = f"M{i:02d}"
        records.append({"id": rid, "record_type": "metric_series", "service": svc, "metric": metric, "unit": UNITS[metric], "points": points})
        if any(e.key for e in effects):
            key.append([rid])
        if any(e.decoy for e in effects):
            decoy.append([rid])
    return records, key, decoy


def build_logs(spec: Spec, rng: random.Random) -> tuple[list[dict], list[list[str]], list[list[str]]]:
    raw: list[tuple[int, str, str, str, int | None]] = []
    for svc, (info, warn, err) in BACKGROUND_LOGS.items():
        # Background volume follows the service's request rate (fewer lines when traffic drops, more in a
        # surge), and routine success lines thin out as the error rate rises, so logs agree with metrics.
        base_rate = BASELINES.get(svc, {}).get("request_rate")
        t = WINDOW_START * 60 + rng.randint(0, 90)
        while t <= WINDOW_END * 60:
            traffic, success = 1.0, 1.0
            if base_rate:
                traffic = max(metric_value(spec, svc, "request_rate", t / 60), 0.0) / base_rate
                success = max(0.0, 1 - metric_value(spec, svc, "error_rate", t / 60) / 100)
            r = rng.random()
            level, pool = ("ERROR", err) if r < 0.03 else ("WARN", warn) if r < 0.15 else ("INFO", info)
            message = fill(rng.choice(pool), rng)
            if level != "INFO" or rng.random() < success:
                raw.append((t, svc, level, message, None))
            t += max(1, int(rng.randint(100, 260) / max(traffic, 0.02)))
    for idx, sig in enumerate(spec.logs):
        span = (sig.end - sig.start) * 60
        for k in range(sig.count):
            offset = span * k // (sig.count - 1) if sig.count > 1 else 0
            t = min(sig.start * 60 + offset + rng.randint(0, 40), WINDOW_END * 60)
            raw.append((t, sig.service, sig.level, fill(sig.message, rng), idx))
    raw.sort(key=lambda x: (x[0], x[1]))
    records, groups = [], {}
    for i, (t, svc, level, msg, idx) in enumerate(raw, 1):
        rid = f"L{i:04d}"
        records.append({"id": rid, "record_type": "log", "ts": iso(spec.t0 + timedelta(seconds=t)), "service": svc, "level": level, "message": msg})
        if idx is not None:
            groups.setdefault(idx, []).append(rid)
    key = [groups[i] for i, s in enumerate(spec.logs) if s.key and i in groups]
    decoy = [groups[i] for i, s in enumerate(spec.logs) if s.decoy and i in groups]
    return records, key, decoy


def build_changes(spec: Spec) -> tuple[list[dict], list[list[str]], list[list[str]]]:
    items = [(C(o, s, ty, d, v, a), False) for o, s, ty, d, v, a in BACKGROUND_CHANGES] + [(c, True) for c in spec.changes]
    items.sort(key=lambda x: x[0].offset)
    records, key, decoy = [], [], []
    for i, (c, _) in enumerate(items, 1):
        rid = f"C{i:02d}"
        rec = {"id": rid, "record_type": "change", "ts": iso(spec.t0 + timedelta(minutes=c.offset)), "service": c.service,
               "type": c.type, "description": c.description, "author": c.author, "status": "completed"}
        if c.version:
            rec["version"] = c.version
        records.append(rec)
        if c.key:
            key.append([rid])
        if c.decoy:
            decoy.append([rid])
    return records, key, decoy


def build_topology(spec: Spec) -> tuple[dict, list[list[str]], list[list[str]]]:
    edges = [{"id": f"D{i:02d}", "record_type": "edge", "caller": a, "callee": b, "kind": k} for i, (a, b, k) in enumerate(EDGES, 1)]
    components = sorted({a for a, _, _ in EDGES} | {b for _, b, _ in EDGES})
    overrides = {h.service: h for h in spec.health}
    health, key, decoy = [], [], []
    for i, svc in enumerate(components, 1):
        rid = f"H{i:02d}"
        h = overrides.get(svc)
        health.append({"id": rid, "record_type": "health", "service": svc, "status": h.status if h else "healthy",
                       "detail": h.detail if h else HEALTHY_DETAIL.get(svc, "HTTP /health 200"),
                       "checked_at": iso(spec.t0 + timedelta(minutes=WINDOW_END - 2))})
        if h and h.key:
            key.append([rid])
        if h and h.decoy:
            decoy.append([rid])
    return {"edges": edges, "health": health}, key, decoy


def build_past(spec: Spec) -> tuple[list[dict], list[list[str]], list[list[str]]]:
    items = [(P(*p), None) for p in BASE_PAST] + [(p, p) for p in spec.past]
    items.sort(key=lambda x: x[0].date)
    records, key, decoy = [], [], []
    for i, (p, own) in enumerate(items, 1):
        rid = f"P{i:02d}"
        records.append({"id": rid, "record_type": "past_incident", "date": p.date, "title": p.title, "services": p.services,
                        "symptoms": p.symptoms, "root_cause": p.root_cause, "resolution": p.resolution})
        if own and own.key:
            key.append([rid])
        if own and own.decoy:
            decoy.append([rid])
    return records, key, decoy


def write_json(path: Path, obj) -> None:
    # Write bytes, not text: text mode would turn "\n" into "\r\n" on Windows and make the files OS-dependent.
    path.write_bytes((json.dumps(obj, indent=1) + "\n").encode("utf-8"))


def content_sha256(path: Path) -> str:
    """SHA-256 of a file with line endings normalised to LF, so hashes match on any OS and any Git checkout."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def generate(spec: Spec, root: Path = DATA) -> None:
    rng = random.Random(f"incident-{spec.id}")
    metrics, mk, md = build_metrics(spec, rng)
    logs, lk, ld = build_logs(spec, rng)
    changes, ck, cd = build_changes(spec)
    topology, hk, hd = build_topology(spec)
    past, pk, pd = build_past(spec)

    folder = root / "incidents" / spec.id
    folder.mkdir(parents=True, exist_ok=True)
    brief = {
        "id": spec.id,
        "title": spec.title,
        "reported_at": iso(spec.t0 + timedelta(minutes=WINDOW_END)),
        "alert": spec.alert,
        "affected_services": spec.affected,
        "window_start": iso(spec.t0 + timedelta(minutes=WINDOW_START)),
        "window_end": iso(spec.t0 + timedelta(minutes=WINDOW_END)),
    }
    write_json(folder / "scenario.json", {"brief": brief, "faults": spec.faults})
    write_json(folder / "logs.json", logs)
    write_json(folder / "metrics.json", metrics)
    write_json(folder / "changes.json", changes)
    write_json(folder / "topology.json", topology)
    write_json(folder / "past_incidents.json", past)
    write_json(root / "ground_truth" / f"{spec.id}.json", {
        "incident_id": spec.id,
        "expected_inconclusive": spec.inconclusive,
        "root_cause_services": spec.services,
        "root_cause_categories": spec.categories,
        "summary": spec.summary,
        "key_evidence": ck + mk + lk + hk + pk,
        "misleading_evidence": cd + md + ld + hd + pd,
        "decoy_hypotheses": spec.decoys,
        "tags": spec.tags,
    })
    print(f"{spec.id}: {len(logs)} log lines, {len(metrics)} series, {len(changes)} changes, faults={len(spec.faults)}")


DATASET_VERSION = "v2.1"  # bump whenever generated evidence changes


def write_manifest(root: Path) -> dict:
    """SHA-256 of every generated file, so an evaluation can prove which dataset it used."""
    files = sorted(p for sub in ("incidents", "ground_truth") for p in (root / sub).rglob("*.json"))
    manifest = {
        "dataset_version": DATASET_VERSION,
        "hash_method": "sha256 of UTF-8 bytes with LF line endings",
        "generator_sha256": content_sha256(Path(__file__)),
        "files": {p.relative_to(root).as_posix(): content_sha256(p) for p in files},
    }
    write_json(root / "MANIFEST.json", manifest)
    return manifest


def main(root: Path = DATA) -> None:
    for sub in ("incidents", "ground_truth"):
        target = root / sub
        if target.exists():
            for child in target.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.suffix == ".json":
                    child.unlink()
        target.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        generate(spec, root)
    manifest = write_manifest(root)
    print(f"dataset {manifest['dataset_version']}: {len(manifest['files'])} files hashed into MANIFEST.json")


if __name__ == "__main__":
    main()