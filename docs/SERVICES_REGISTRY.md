# Service Registry & Dependency Graph
## `services.py` Module Documentation

> **Purpose:** Structured representation of 21 microservices with dependency mapping, observability signals, and failure cascade analysis.

> **Used by:** `environment.py` (task selection), `inference.py` (agent reasoning), `server/dashboard_impl.py` (visualization), `benchmark_runner.py` (fault injection)

---

## Quick Start

### Basic Queries

```python
from services import (
    SERVICE_REGISTRY,
    get_dependencies,
    get_dependents,
    get_all_dependents_recursive,
    simulate_failure,
)

# What does order-service depend on?
deps = get_dependencies("order-service")
print(deps)  # {'postgres-db', 'payment-service', 'vault', ...}

# What depends on postgres-db?
dependents = get_dependents("postgres-db")
print(dependents)  # {'order-service', 'auth-service', ...}

# Full cascade if postgres-db fails
cascade = get_all_dependents_recursive("postgres-db")
print(cascade)  # 9 services affected

# Simulate failure
impact = simulate_failure("postgres-db")
print(impact["cascade_size"])  # 9
print(impact["critical_path_broken"])  # True
```

---

## Service Class

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Service identifier (e.g., `"auth-service"`) |
| `tier` | `ServiceTier` | Tier classification (FOUNDATIONAL, TIER_1, TIER_2, TIER_3) |
| `description` | `str` | What this service does in the system |
| `dependencies` | `List[str]` | Services this depends on |
| `critical_path` | `bool` | Is this on critical path to revenue? |
| `metrics` | `Dict[str, MetricSignal]` | Key health metrics |
| `logs` | `List[LogSignal]` | Log patterns indicating failures |
| `fault_types` | `List[str]` | Possible failure modes |
| `recovery_actions` | `List[str]` | Actions that can fix this service |
| `cascade_targets` | `List[str]` | Services affected if this fails |
| `red_herring_targets` | `List[str]` | Services that look suspect when this fails |

### Methods

```python
service = SERVICE_REGISTRY["postgres-db"]

# Check if on critical path
if service.critical_path:
    print("This service breaks revenue if it fails")

# Get metrics
metrics = service.metrics
for name, signal in metrics.items():
    print(f"{name}: critical at {signal.critical_threshold} {signal.unit}")

# Get logs
for log in service.logs:
    print(f"[{log.severity}] {log.pattern} → {log.indicates}")
```

---

## Service Tiers

### Foundational (6 services)
**Critical infrastructure.** Failing = cascades everywhere. Must be monitored constantly.

- `api-gateway` — Entry point for all traffic
- `auth-service` — Authentication/authorization
- `order-service` — Order processing
- `postgres-db` — Persistent state
- `redis-cache` — Session cache
- `notification-service` — Async notifications

### Tier 1: High-Impact Infrastructure (5 services)
**Event streaming, search, secrets, ingress, workers.** Failing = significant cascade.

- `kafka-broker` — Event streaming (order → notification decoupling)
- `elasticsearch` — Search engine (products, orders)
- `nginx-ingress` — Kubernetes ingress (TLS, routing)
- `vault` — Secrets management (DB creds, API keys)
- `celery-worker` — Async task processing (emails, notifications)

### Tier 2: Application-Layer Services (5 services)
**Domain reasoning required.** Failing = user-facing impact (but not system-wide).

- `payment-service` — Payment processing (Stripe integration)
- `inventory-service` — Stock tracking (race conditions, oversell)
- `search-service` — Product search (elasticsearch consumer)
- `email-service` — SMTP relay (transactional emails)
- `user-profile-service` — User data (cache invalidation, staleness)

### Tier 3: Observability & Infrastructure (5 services)
**Expert-level.** Failing = diagnostic blindspot (harder to detect).

- `prometheus` — Metrics collection (alerting backend)
- `jaeger` — Distributed tracing (span ingestion)
- `config-service` — Feature flags (LaunchDarkly-like)
- `cdn-edge` — Content delivery (static assets)
- `k8s-scheduler` — Pod scheduling (resource management, eviction)

---

## Helper Functions

### `get_dependencies(service_name: str) → Set[str]`

Get direct dependencies of a service.

```python
deps = get_dependencies("order-service")
# {'postgres-db', 'payment-service', 'inventory-service', 'notification-service', 'kafka-broker', 'vault'}
```

### `get_all_dependencies_recursive(service_name: str) → Set[str]`

Get all dependencies (direct and transitive).

```python
all_deps = get_all_dependencies_recursive("api-gateway")
# {'nginx-ingress', 'config-service', 'auth-service', 'postgres-db', 'vault', 'redis-cache', ...}
```

### `get_dependents(service_name: str) → Set[str]`

Get services that directly depend on this service.

```python
dependents = get_dependents("postgres-db")
# {'order-service', 'auth-service', 'inventory-service', 'config-service', 'user-profile-service', 'payment-service'}
```

### `get_all_dependents_recursive(service_name: str) → Set[str]`

Get all services (direct and transitive) that depend on this service.

```python
cascade = get_all_dependents_recursive("postgres-db")
# {'order-service', 'auth-service', 'api-gateway', 'inventory-service', 'config-service', ...}
# (9 services total)
```

### `simulate_failure(service_name: str) → Dict[str, Any]`

Simulate the impact of a service failure. Returns:

```python
impact = simulate_failure("postgres-db")
{
    "service": "postgres-db",
    "service_tier": "foundational",
    "direct_impact": {'order-service', 'auth-service', ...},
    "cascade_impact": {...},  # All affected services
    "cascade_size": 9,
    "critical_path_broken": True,
    "recommended_actions": ['run_db_query', 'restart_service'],
    "affected_critical_services": ['order-service', 'api-gateway', ...]
}
```

### `get_critical_path_services() → Set[str]`

Get all services on the critical path to user revenue.

```python
critical = get_critical_path_services()
# 12 services: api-gateway, auth-service, postgres-db, ...
```

### `get_services_by_tier(tier: ServiceTier) → List[Service]`

Get all services in a specific tier.

```python
from services import ServiceTier
foundational = get_services_by_tier(ServiceTier.FOUNDATIONAL)
# [api-gateway, auth-service, order-service, ...]
```

---

## Dependency Graph

### SERVICE_GRAPH

Dictionary mapping service name → set of dependencies.

```python
from services import SERVICE_GRAPH

SERVICE_GRAPH = {
    "api-gateway": {"nginx-ingress", "config-service", "jaeger", "prometheus"},
    "order-service": {"postgres-db", "payment-service", "inventory-service", ...},
    "postgres-db": {"vault", "k8s-scheduler"},
    ...
}
```

### SERVICE_REGISTRY

Dictionary mapping service name → Service object.

```python
from services import SERVICE_REGISTRY

# Access any service
postgres = SERVICE_REGISTRY["postgres-db"]
print(postgres.critical_path)  # True
print(postgres.metrics)  # Dict of MetricSignal objects
```

---

## Cascade Analysis Examples

### Example 1: PostgreSQL Failure

```python
impact = simulate_failure("postgres-db")
print(f"Cascades to {impact['cascade_size']} services")
# 9 services affected

# Critical path broken? YES
# Revenue impact? YES (order-service down)

# Recommended actions: ['run_db_query', 'restart_service']
```

### Example 2: Vault (Secrets) Failure

```python
impact = simulate_failure("vault")
print(f"Affects {len(impact['affected_critical_services'])} critical services")
# 12 critical services (everything that needs DB credentials)

# Why? All services need credentials from Vault
# If Vault is down, no one can renew credentials
```

### Example 3: Config Service (Feature Flags) Failure

```python
impact = simulate_failure("config-service")
# All feature flags default to OFF
# Checkout disabled, search disabled, etc.
# Users see blank pages (not errors)
```

### Example 4: Kafka Broker Failure

```python
impact = simulate_failure("kafka-broker")
# Direct impact: order-service, notification-service (queue backed up)
# Notifications won't send (emails, SMS, push all queued)
# Users don't know orders shipped (silently failing)
```

---

## Integration with environment.py

### Using services in task creation

```python
from services import SERVICE_REGISTRY, get_dependencies

# Get a service and its dependencies for task design
payment_svc = SERVICE_REGISTRY["payment-service"]
payment_deps = get_dependencies("payment-service")

# Create a payment timeout task
task = {
    "name": "Payment processor webhook timeout",
    "fault_service": "payment-service",
    "fault_type": "processor_webhook_timeout",
    "dependencies": list(payment_deps),
    "red_herrings": payment_svc.red_herring_targets,
}
```

### Using cascade analysis in inference

```python
from services import simulate_failure

# Agent reasons about impact
impact = simulate_failure(suspected_service)
if impact["critical_path_broken"]:
    # This is high-priority
    print("Critical path affected — escalate immediately")
```

---

## Metrics and Logs

### MetricSignal

```python
@dataclass
class MetricSignal:
    name: str                  # "latency_p99_ms"
    critical_threshold: float  # 5000 (milliseconds)
    unit: str                  # "ms"
    example_critical_value: float  # 8000 (what you see in a failure)
```

### LogSignal

```python
@dataclass
class LogSignal:
    pattern: str         # "[ERROR] auth-service: thread saturation"
    severity: str        # "ERROR", "WARN", "FATAL"
    indicates: str       # "thread pool exhausted"
```

### Accessing signals

```python
from services import get_service_metrics, get_service_logs

# Get all metrics
metrics = get_service_metrics("api-gateway")
for name, signal in metrics.items():
    print(f"{name}: threshold={signal.critical_threshold}")

# Get all logs
logs = get_service_logs("auth-service")
for log in logs:
    print(f"[{log.severity}] {log.pattern}")
```

---

## Real-World Service Relationships

### Critical Path Chain

```
User Request
    ↓
cdn-edge (cache/static)
    ↓
nginx-ingress (TLS, routing)
    ↓
api-gateway (request routing)
    ↓
auth-service (token validation) → vault (credentials)
    ↓
order-service (business logic)
    ↓
postgres-db (persistent state) ← vault (DB credentials)
    ↓
payment-service (charge processing)
    ↓
kafka-broker (event stream)
    ↓
celery-worker + notification-service (async notifications)
    ↓
email-service (SMTP relay)
```

### Observability Chain (Meta-dependency)

```
All Services → prometheus (metrics collection)
All Services → jaeger (trace ingestion)
All Services → config-service (feature flags)
All Services → k8s-scheduler (pod management)
```

---

## Performance Characteristics

| Operation | Complexity | Time |
|-----------|-----------|------|
| `get_dependencies(service)` | O(1) | <1ms |
| `get_all_dependencies_recursive(service)` | O(n) where n=services | <5ms |
| `get_dependents(service)` | O(n) | <5ms |
| `simulate_failure(service)` | O(n) | <5ms |
| Load entire registry | O(1) | ~1ms |

---

## Best Practices

### 1. Always Check Critical Path
```python
if SERVICE_REGISTRY[service_name].critical_path:
    # This service breaks revenue if down
    priority = "P0"
```

### 2. Use Cascade Analysis for Root Cause
```python
# If search-service is slow, check:
es_impact = simulate_failure("elasticsearch")
if "search-service" in es_impact["cascade_impact"]:
    # elasticsearch might be the root cause
```

### 3. Red Herrings Point to Root Cause
```python
service = SERVICE_REGISTRY["postgres-db"]
# When postgres-db fails, these look suspicious:
print(service.red_herring_targets)  # ['api-gateway']

# So if you see api-gateway errors + postgres-db metrics,
# it's likely postgres-db → api-gateway cascade
```

### 4. Log Patterns Indicate Specific Faults
```python
for log in SERVICE_REGISTRY["vault"].logs:
    if "token lease expired" in log.pattern:
        # This specific fault pattern indicates token TTL exceeded
        recovery = "Renew Vault token lease"
```

---

## Statistics

| Metric | Count |
|--------|-------|
| Total services | 21 |
| Critical path services | 12 |
| Foundational services | 6 |
| Tier 1 services | 5 |
| Tier 2 services | 5 |
| Tier 3 services | 5 |
| Total metrics defined | 78+ |
| Total log patterns | 60+ |
| Max cascade size | 12 (vault failure) |
| Avg cascade size | ~5 services |
| DAG acyclic? | ✓ Yes (no cycles) |

---

## Extending the Registry

### Add a New Service

```python
from services import Service, ServiceTier, MetricSignal, LogSignal

new_service = Service(
    name="my-service",
    tier=ServiceTier.TIER_2,
    description="What this service does",
    dependencies=["postgres-db", "redis-cache"],
    critical_path=False,
    metrics={
        "latency_p99_ms": MetricSignal("latency_p99_ms", 2000, "ms", 5000),
    },
    logs=[
        LogSignal("[ERROR] my-service: timeout", "ERROR", "upstream slow"),
    ],
    fault_types=["cascading_timeout"],
    recovery_actions=["restart_service"],
    cascade_targets=["api-gateway"],
    red_herring_targets=[],
)

# Add to registry
SERVICE_REGISTRY["my-service"] = new_service
SERVICE_GRAPH["my-service"] = set(new_service.dependencies)
```

---

*Built for OpenEnv × Scaler × Meta Scalar X Hackathon 2026. Based on real incidents and microservice patterns from Netflix, Stripe, Cloudflare, AWS, GitHub, Discord, and Shopify.*
