"""Central Prometheus metrics registry for WriteAgent."""
from prometheus_client import Counter, Gauge, Histogram

# --- Alert-driven metrics (prometheus-alerts.yml) ---
health_status = Gauge(
    "writeagent_health_status",
    "Application health: 1=healthy, 0=degraded",
)
scene_generation_failures = Counter(
    "writeagent_scene_generation_failures_total",
    "Total scene generation pipeline failures",
)
audit_log_failures = Counter(
    "writeagent_audit_log_failures_total",
    "Total audit log write failures",
)
contradictions_total = Counter(
    "writeagent_contradictions_total",
    "Total contradictions detected by ConsistencyChecker",
    ["severity"],
)

# --- LLM observability ---
llm_call_duration = Histogram(
    "writeagent_llm_call_duration_seconds",
    "End-to-end LLM call duration including tool turns",
    ["agent_id"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
llm_tokens_total = Counter(
    "writeagent_llm_tokens_total",
    "LLM tokens consumed",
    ["agent_id", "direction"],  # direction: prompt | completion
)
