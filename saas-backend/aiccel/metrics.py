# aiccel/metrics.py
"""
Enterprise Observability & Metrics
==================================

Production-grade metrics and tracing with:
- Prometheus metrics export
- OpenTelemetry integration
- Custom metrics collectors
- Health check endpoints

Usage:
    from aiccel.metrics import MetricsCollector, get_metrics

    # Initialize metrics
    metrics = MetricsCollector()

    # Record metrics
    metrics.record_request(agent="MyAgent", duration_ms=150, success=True)
    metrics.record_tokens(input_tokens=100, output_tokens=200)

    # Export for Prometheus
    print(metrics.export_prometheus())

    # As middleware
    from aiccel.metrics import MetricsMiddleware
    pipeline.use(MetricsMiddleware(metrics))
"""

import threading
import time
from collections import defaultdict
from collections.abc import Awaitable
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from .logging_config import get_logger


logger = get_logger("metrics")


# ============================================================================
# METRIC TYPES
# ============================================================================

@dataclass
class Counter:
    """Monotonically increasing counter."""
    name: str
    description: str
    labels: dict[str, str] = field(default_factory=dict)
    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, value: float = 1.0) -> None:
        """Increment counter."""
        with self._lock:
            self._value += value

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Gauge:
    """Value that can go up and down."""
    name: str
    description: str
    labels: dict[str, str] = field(default_factory=dict)
    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float) -> None:
        """Set gauge value."""
        with self._lock:
            self._value = value

    def inc(self, value: float = 1.0) -> None:
        """Increment gauge."""
        with self._lock:
            self._value += value

    def dec(self, value: float = 1.0) -> None:
        """Decrement gauge."""
        with self._lock:
            self._value -= value

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Histogram:
    """Distribution of values with configurable buckets."""
    name: str
    description: str
    buckets: list[float] = field(default_factory=lambda: [
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
    ])
    labels: dict[str, str] = field(default_factory=dict)
    _counts: dict[float, int] = field(default_factory=dict)
    _sum: float = 0.0
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self._counts = dict.fromkeys(self.buckets, 0)
        self._counts[float('inf')] = 0

    def observe(self, value: float) -> None:
        """Record a value."""
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1
            self._counts[float('inf')] += 1

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def count(self) -> int:
        return self._count

    def get_bucket_counts(self) -> dict[float, int]:
        return dict(self._counts)


@dataclass
class Summary:
    """Summary statistics with quantiles."""
    name: str
    description: str
    labels: dict[str, str] = field(default_factory=dict)
    _values: list[float] = field(default_factory=list)
    _max_samples: int = 1000
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float) -> None:
        """Record a value."""
        with self._lock:
            self._values.append(value)
            if len(self._values) > self._max_samples:
                self._values = self._values[-self._max_samples:]

    def quantile(self, q: float) -> float:
        """Get quantile value."""
        with self._lock:
            if not self._values:
                return 0.0
            sorted_values = sorted(self._values)
            idx = int(len(sorted_values) * q)
            return sorted_values[min(idx, len(sorted_values) - 1)]

    @property
    def count(self) -> int:
        return len(self._values)

    @property
    def sum(self) -> float:
        return sum(self._values)


# ============================================================================
# METRICS COLLECTOR
# ============================================================================

class MetricsCollector:
    """
    Central metrics collector for AICCEL.

    Collects and exports metrics in Prometheus and OpenTelemetry formats.
    """

    def __init__(self, prefix: str = "aiccel"):
        """
        Initialize metrics collector.

        Args:
            prefix: Prefix for all metric names
        """
        self.prefix = prefix
        self._lock = threading.Lock()

        # Request metrics
        self.requests_total = Counter(
            f"{prefix}_requests_total",
            "Total number of requests processed"
        )
        self.requests_success = Counter(
            f"{prefix}_requests_success_total",
            "Total successful requests"
        )
        self.requests_failed = Counter(
            f"{prefix}_requests_failed_total",
            "Total failed requests"
        )

        # Latency metrics
        self.request_duration = Histogram(
            f"{prefix}_request_duration_seconds",
            "Request duration in seconds",
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
        )

        # Token metrics
        self.tokens_input = Counter(
            f"{prefix}_tokens_input_total",
            "Total input tokens processed"
        )
        self.tokens_output = Counter(
            f"{prefix}_tokens_output_total",
            "Total output tokens generated"
        )

        # Tool metrics
        self.tool_calls = Counter(
            f"{prefix}_tool_calls_total",
            "Total tool invocations"
        )
        self.tool_errors = Counter(
            f"{prefix}_tool_errors_total",
            "Total tool execution errors"
        )
        self.tool_duration = Histogram(
            f"{prefix}_tool_duration_seconds",
            "Tool execution duration in seconds"
        )

        # Memory metrics
        self.memory_turns = Gauge(
            f"{prefix}_memory_turns",
            "Current conversation turns in memory"
        )
        self.memory_tokens = Gauge(
            f"{prefix}_memory_tokens",
            "Current tokens in memory"
        )

        # Agent metrics
        self.active_agents = Gauge(
            f"{prefix}_active_agents",
            "Number of active agent instances"
        )

        # Provider metrics
        self.provider_requests = defaultdict(lambda: Counter(
            f"{prefix}_provider_requests_total",
            "Requests per provider"
        ))
        self.provider_errors = defaultdict(lambda: Counter(
            f"{prefix}_provider_errors_total",
            "Errors per provider"
        ))
        self.provider_latency = defaultdict(lambda: Histogram(
            f"{prefix}_provider_latency_seconds",
            "Provider latency in seconds"
        ))

        # Rate limit metrics
        self.rate_limit_hits = Counter(
            f"{prefix}_rate_limit_hits_total",
            "Total rate limit hits"
        )

        # Custom metrics storage
        self._custom_counters: dict[str, Counter] = {}
        self._custom_gauges: dict[str, Gauge] = {}
        self._custom_histograms: dict[str, Histogram] = {}

        # Per-agent metrics
        self._agent_metrics: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "requests": 0,
            "successes": 0,
            "failures": 0,
            "total_duration_ms": 0.0,
            "tool_calls": 0
        })

    # ========================================================================
    # RECORDING METHODS
    # ========================================================================

    def record_request(
        self,
        agent: str = "default",
        duration_ms: float = 0.0,
        success: bool = True,
        tool_calls: int = 0
    ) -> None:
        """Record a request."""
        self.requests_total.inc()

        if success:
            self.requests_success.inc()
        else:
            self.requests_failed.inc()

        self.request_duration.observe(duration_ms / 1000.0)

        if tool_calls > 0:
            self.tool_calls.inc(tool_calls)

        # Per-agent tracking
        with self._lock:
            self._agent_metrics[agent]["requests"] += 1
            if success:
                self._agent_metrics[agent]["successes"] += 1
            else:
                self._agent_metrics[agent]["failures"] += 1
            self._agent_metrics[agent]["total_duration_ms"] += duration_ms
            self._agent_metrics[agent]["tool_calls"] += tool_calls

    def record_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        """Record token usage."""
        if input_tokens > 0:
            self.tokens_input.inc(input_tokens)
        if output_tokens > 0:
            self.tokens_output.inc(output_tokens)

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool = True
    ) -> None:
        """Record tool execution."""
        self.tool_calls.inc()
        self.tool_duration.observe(duration_ms / 1000.0)

        if not success:
            self.tool_errors.inc()

    def record_provider_call(
        self,
        provider: str,
        duration_ms: float,
        success: bool = True
    ) -> None:
        """Record provider API call."""
        self.provider_requests[provider].inc()
        self.provider_latency[provider].observe(duration_ms / 1000.0)

        if not success:
            self.provider_errors[provider].inc()

    def record_rate_limit_hit(self) -> None:
        """Record rate limit hit."""
        self.rate_limit_hits.inc()

    def set_memory_stats(self, turns: int, tokens: int) -> None:
        """Update memory statistics."""
        self.memory_turns.set(turns)
        self.memory_tokens.set(tokens)

    def set_active_agents(self, count: int) -> None:
        """Update active agent count."""
        self.active_agents.set(count)

    # ========================================================================
    # CUSTOM METRICS
    # ========================================================================

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a custom counter."""
        full_name = f"{self.prefix}_{name}"
        if full_name not in self._custom_counters:
            self._custom_counters[full_name] = Counter(full_name, description)
        return self._custom_counters[full_name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a custom gauge."""
        full_name = f"{self.prefix}_{name}"
        if full_name not in self._custom_gauges:
            self._custom_gauges[full_name] = Gauge(full_name, description)
        return self._custom_gauges[full_name]

    def histogram(
        self,
        name: str,
        description: str = "",
        buckets: Optional[list[float]] = None
    ) -> Histogram:
        """Get or create a custom histogram."""
        full_name = f"{self.prefix}_{name}"
        if full_name not in self._custom_histograms:
            self._custom_histograms[full_name] = Histogram(
                full_name, description,
                buckets=buckets or [0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
            )
        return self._custom_histograms[full_name]

    # ========================================================================
    # TIMING CONTEXT MANAGER
    # ========================================================================

    @contextmanager
    def timer(self, metric_name: str = "operation"):
        """Context manager for timing operations."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            hist = self.histogram(f"{metric_name}_duration_seconds")
            hist.observe(duration)

    # ========================================================================
    # EXPORT METHODS
    # ========================================================================

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        def format_metric(metric, metric_type: str):
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {metric_type}")

            labels_str = ""
            if metric.labels:
                labels_str = "{" + ",".join(f'{k}="{v}"' for k, v in metric.labels.items()) + "}"

            if isinstance(metric, (Counter, Gauge)):
                lines.append(f"{metric.name}{labels_str} {metric.value}")
            elif isinstance(metric, Histogram):
                for bucket, count in metric.get_bucket_counts().items():
                    bucket_label = f'le="{bucket}"' if bucket != float('inf') else 'le="+Inf"'
                    if labels_str:
                        full_labels = labels_str[:-1] + "," + bucket_label + "}"
                    else:
                        full_labels = "{" + bucket_label + "}"
                    lines.append(f"{metric.name}_bucket{full_labels} {count}")
                lines.append(f"{metric.name}_sum{labels_str} {metric.sum}")
                lines.append(f"{metric.name}_count{labels_str} {metric.count}")

        # Core metrics
        format_metric(self.requests_total, "counter")
        format_metric(self.requests_success, "counter")
        format_metric(self.requests_failed, "counter")
        format_metric(self.request_duration, "histogram")
        format_metric(self.tokens_input, "counter")
        format_metric(self.tokens_output, "counter")
        format_metric(self.tool_calls, "counter")
        format_metric(self.tool_errors, "counter")
        format_metric(self.tool_duration, "histogram")
        format_metric(self.memory_turns, "gauge")
        format_metric(self.memory_tokens, "gauge")
        format_metric(self.active_agents, "gauge")
        format_metric(self.rate_limit_hits, "counter")

        # Provider metrics
        for provider, counter in self.provider_requests.items():
            counter.labels = {"provider": provider}
            format_metric(counter, "counter")

        # Custom metrics
        for counter in self._custom_counters.values():
            format_metric(counter, "counter")
        for gauge in self._custom_gauges.values():
            format_metric(gauge, "gauge")
        for histogram in self._custom_histograms.values():
            format_metric(histogram, "histogram")

        return "\n".join(lines)

    def export_json(self) -> dict[str, Any]:
        """Export metrics as JSON."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "requests": {
                "total": self.requests_total.value,
                "success": self.requests_success.value,
                "failed": self.requests_failed.value,
                "success_rate": (
                    self.requests_success.value / self.requests_total.value
                    if self.requests_total.value > 0 else 0
                )
            },
            "latency": {
                "count": self.request_duration.count,
                "sum_seconds": self.request_duration.sum,
                "avg_seconds": (
                    self.request_duration.sum / self.request_duration.count
                    if self.request_duration.count > 0 else 0
                )
            },
            "tokens": {
                "input_total": self.tokens_input.value,
                "output_total": self.tokens_output.value,
                "total": self.tokens_input.value + self.tokens_output.value
            },
            "tools": {
                "calls": self.tool_calls.value,
                "errors": self.tool_errors.value,
                "error_rate": (
                    self.tool_errors.value / self.tool_calls.value
                    if self.tool_calls.value > 0 else 0
                )
            },
            "memory": {
                "turns": self.memory_turns.value,
                "tokens": self.memory_tokens.value
            },
            "agents": {
                "active": self.active_agents.value,
                "per_agent": dict(self._agent_metrics)
            },
            "rate_limits": {
                "hits": self.rate_limit_hits.value
            }
        }

    def export_opentelemetry(self) -> dict[str, Any]:
        """Export in OpenTelemetry-compatible format."""
        return {
            "resource_metrics": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "aiccel"}},
                        {"key": "service.version", "value": {"stringValue": "3.5.0"}}
                    ]
                },
                "scope_metrics": [{
                    "scope": {"name": "aiccel.metrics"},
                    "metrics": [
                        {
                            "name": self.requests_total.name,
                            "description": self.requests_total.description,
                            "sum": {
                                "dataPoints": [{
                                    "asDouble": self.requests_total.value,
                                    "timeUnixNano": int(time.time() * 1e9)
                                }],
                                "isMonotonic": True
                            }
                        },
                        {
                            "name": self.request_duration.name,
                            "description": self.request_duration.description,
                            "histogram": {
                                "dataPoints": [{
                                    "count": self.request_duration.count,
                                    "sum": self.request_duration.sum,
                                    "bucketCounts": list(self.request_duration.get_bucket_counts().values()),
                                    "explicitBounds": self.request_duration.buckets,
                                    "timeUnixNano": int(time.time() * 1e9)
                                }]
                            }
                        }
                    ]
                }]
            }]
        }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        self.requests_total._value = 0
        self.requests_success._value = 0
        self.requests_failed._value = 0
        self.tokens_input._value = 0
        self.tokens_output._value = 0
        self.tool_calls._value = 0
        self.tool_errors._value = 0
        self.rate_limit_hits._value = 0
        self._agent_metrics.clear()


# ============================================================================
# METRICS MIDDLEWARE
# ============================================================================

class MetricsMiddleware:
    """
    Middleware for automatic metrics collection.

    Integrates with the pipeline system to collect metrics
    on every request.
    """

    def __init__(
        self,
        collector: Optional[MetricsCollector] = None,
        include_tokens: bool = True,
        include_tools: bool = True
    ):
        """
        Initialize metrics middleware.

        Args:
            collector: MetricsCollector instance (creates default if None)
            include_tokens: Track token usage
            include_tools: Track tool calls
        """
        self.collector = collector or MetricsCollector()
        self.include_tokens = include_tokens
        self.include_tools = include_tools
        self._logger = get_logger("middleware.metrics")

    async def __call__(
        self,
        context: Any,
        next_middleware: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Execute with metrics collection."""
        start = time.perf_counter()
        agent_name = getattr(context, 'agent_name', 'default')
        success = True
        tool_calls = 0

        try:
            result = await next_middleware(context)

            # Count tool calls from response
            if self.include_tools and hasattr(context, 'response'):
                if hasattr(context.response, 'tool_calls'):
                    tool_calls = len(context.response.tool_calls)

            return result

        except Exception:
            success = False
            raise

        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            self.collector.record_request(
                agent=agent_name,
                duration_ms=duration_ms,
                success=success,
                tool_calls=tool_calls
            )

            # Token tracking (if available in context)
            if self.include_tokens and hasattr(context, 'metadata'):
                input_tokens = context.metadata.get('input_tokens', 0)
                output_tokens = context.metadata.get('output_tokens', 0)
                if input_tokens or output_tokens:
                    self.collector.record_tokens(input_tokens, output_tokens)


# ============================================================================
# OPENTELEMETRY INTEGRATION
# ============================================================================

class OpenTelemetryIntegration:
    """
    OpenTelemetry integration for distributed tracing.

    Requires: opentelemetry-api, opentelemetry-sdk
    """

    _tracer = None
    _meter = None

    @classmethod
    def initialize(
        cls,
        service_name: str = "aiccel",
        otlp_endpoint: Optional[str] = None
    ) -> bool:
        """
        Initialize OpenTelemetry.

        Args:
            service_name: Service name for tracing
            otlp_endpoint: OTLP exporter endpoint (optional)

        Returns:
            True if initialized successfully
        """
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            resource = Resource.create({"service.name": service_name})

            # Tracer
            trace.set_tracer_provider(TracerProvider(resource=resource))
            cls._tracer = trace.get_tracer(__name__)

            # Meter
            metrics.set_meter_provider(MeterProvider(resource=resource))
            cls._meter = metrics.get_meter(__name__)

            # OTLP exporter (if endpoint provided)
            if otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                trace.get_tracer_provider().add_span_processor(
                    BatchSpanProcessor(exporter)
                )

            logger.info(f"OpenTelemetry initialized for {service_name}")
            return True

        except ImportError:
            logger.warning("OpenTelemetry not available (install opentelemetry-sdk)")
            return False

    @classmethod
    def get_tracer(cls):
        """Get OpenTelemetry tracer."""
        return cls._tracer

    @classmethod
    def get_meter(cls):
        """Get OpenTelemetry meter."""
        return cls._meter

    @classmethod
    @contextmanager
    def span(cls, name: str, attributes: Optional[dict[str, Any]] = None):
        """Create a tracing span."""
        if cls._tracer:
            with cls._tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, str(v))
                yield span
        else:
            yield None


# ============================================================================
# HEALTH CHECK
# ============================================================================

@dataclass
class HealthStatus:
    """Health check status."""
    healthy: bool
    checks: dict[str, bool]
    details: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class HealthChecker:
    """
    Health check system for production monitoring.
    """

    def __init__(self):
        self._checks: dict[str, Callable[[], bool]] = {}
        self._details: dict[str, Callable[[], Any]] = {}

    def register_check(
        self,
        name: str,
        check_fn: Callable[[], bool],
        details_fn: Optional[Callable[[], Any]] = None
    ) -> None:
        """Register a health check."""
        self._checks[name] = check_fn
        if details_fn:
            self._details[name] = details_fn

    def check(self) -> HealthStatus:
        """Run all health checks."""
        results = {}
        details = {}

        for name, check_fn in self._checks.items():
            try:
                results[name] = check_fn()
            except Exception as e:
                results[name] = False
                details[f"{name}_error"] = str(e)

            if name in self._details:
                with suppress(Exception):
                    details[name] = self._details[name]()

        return HealthStatus(
            healthy=all(results.values()),
            checks=results,
            details=details
        )

    def is_healthy(self) -> bool:
        """Quick health check."""
        return self.check().healthy


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

_global_metrics: Optional[MetricsCollector] = None
_global_health: Optional[HealthChecker] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = MetricsCollector()
    return _global_metrics


def get_health_checker() -> HealthChecker:
    """Get global health checker."""
    global _global_health
    if _global_health is None:
        _global_health = HealthChecker()

        # Register default checks
        _global_health.register_check(
            "metrics",
            lambda: get_metrics() is not None,
            lambda: {"requests": get_metrics().requests_total.value}
        )

    return _global_health


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Metric types
    'Counter',
    'Gauge',
    'HealthChecker',
    # Health
    'HealthStatus',
    'Histogram',
    # Collector
    'MetricsCollector',
    'MetricsMiddleware',
    # OpenTelemetry
    'OpenTelemetryIntegration',
    'Summary',
    'get_health_checker',
    # Global accessors
    'get_metrics',
]
