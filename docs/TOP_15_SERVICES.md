# Top 15 Services to Add — incident-response-env
> Ranked by hackathon impact: domain novelty + fault diversity + judge impressiveness

---

## How to use this file

For each service, the entry includes:
- **Why it matters** — the real-world incident pattern it models
- **Fault types** — 2–3 distinct failure modes to implement
- **Red herring pairings** — which existing service to use as misdirection
- **Key log/metric signals** — exact strings to put in `_make_logs()` and `_make_metrics()`
- **Correct fix** — which action resolves it
- **Sample task definitions** — drop-in TASKS dict entries

---

## Tier 1 — High Impact, Implement First

### 1. `kafka-broker`
**Why it matters:** Kafka is in every serious microservices stack. Consumer lag, partition rebalancing, and poison-pill events are the most common causes of silent data loss incidents. No other OpenEnv submission will have this. It forces the agent to understand event-driven architectures, not just synchronous HTTP.

**Fault types:**
- `consumer_lag` — notification-service falls 2M messages behind; queue grows unbounded
- `poison_pill_event` — a malformed event crashes every consumer that reads it, causing crash-loop pattern
- `partition_rebalance_storm` — frequent rebalancing every 30s prevents any consumer from completing work

**Red herring pairing:** `order-service` (shows high error rate because notifications are delayed, but is not the cause)

**Key signals for `_make_logs()`:**
```
[ERROR] kafka-broker: consumer group lag=2,147,832 on topic order-events
[ERROR] kafka-broker: poison pill at offset 8847293 — consumer crashed (3rd attempt)
[WARN]  kafka-broker: partition rebalance triggered — all consumers paused
```

**Key signals for `_make_metrics()`:**
```python
"consumer_lag": 2147832,
"messages_per_sec": 0,
"active_consumers": 0,
"rebalance_count_last_hour": 47,
"partition_count": 12,
"error_rate": 0.99
```

**Correct fix:** `rollback_deployment` → `kafka-broker` (for poison_pill/bad config), `declare_rca`

**Sample task definition:**
```python
"task_kafka_consumer_lag": {
    "name": "Kafka consumer group 2M messages behind",
    "difficulty": "medium",
    "max_steps": 15,
    "description": "notification-service consumer group is 2M messages behind on order-events topic.",
    "alert": "ALERT: Email notifications delayed 4+ hours. Kafka consumer lag 2,147,832. Revenue impact.",
    "fault_service": "kafka-broker",
    "fault_type": "consumer_lag",
    "red_herrings": ["notification-service"],
    "ideal_steps": 6,
    "cascade_step": 9,
    "cascade_service": "order-service",
    "cascade_fault": "notification_queue_overflow",
},
"task_kafka_poison_pill": {
    "name": "Kafka poison pill crashes all consumers",
    "difficulty": "hard",
    "max_steps": 20,
    "description": "A malformed event at offset 8847293 crashes every consumer that reads it.",
    "alert": "ALERT: All Kafka consumers dead. order-events topic processing stopped. No notifications sending.",
    "fault_service": "kafka-broker",
    "fault_type": "poison_pill_event",
    "red_herrings": ["notification-service", "order-service"],
    "ideal_steps": 8,
    "cascade_step": 7,
    "cascade_service": "api-gateway",
    "cascade_fault": "event_processing_halted",
},
```

---

### 2. `elasticsearch`
**Why it matters:** Search infrastructure failing is immediately visible to users (empty search results) but the root cause — shard failure, GC pressure, or index corruption — is non-obvious. This is a fan favourite in SRE war stories.

**Fault types:**
- `shard_failure` — one of 5 shards is RED, causing 20% of search queries to fail
- `gc_pressure` — JVM heap at 95%, stop-the-world GC pauses causing 10s timeouts
- `index_corruption` — a bad bulk indexing job corrupted the products index

**Red herring pairing:** `order-service` (slow search makes checkout seem broken, but order-service itself is fine)

**Key signals for `_make_logs()`:**
```
[ERROR] elasticsearch: shard [products][2] failed — primary shard unavailable
[ERROR] elasticsearch: [GC overhead] stop-the-world pause 12,440ms — heap 95%
[ERROR] elasticsearch: failed to merge segment — index corruption detected
```

**Key signals for `_make_metrics()`:**
```python
"cluster_status": "RED",
"active_shards": 4,
"unassigned_shards": 1,
"heap_used_pct": 95,
"gc_pause_ms": 12440,
"search_latency_p99_ms": 15000,
"indexing_rate": 0
```

**Correct fix:** `rollback_deployment` → `elasticsearch` (for index corruption/bad indexing job), `restart_service` for GC

**Sample task definition:**
```python
"task_elasticsearch_shard_failure": {
    "name": "Elasticsearch shard failure — cluster RED",
    "difficulty": "medium",
    "max_steps": 15,
    "description": "Primary shard [2] on products index is unavailable. 20% of search queries failing.",
    "alert": "ALERT: elasticsearch cluster status RED. 20% of search queries returning 503. Product search down.",
    "fault_service": "elasticsearch",
    "fault_type": "shard_failure",
    "red_herrings": ["order-service"],
    "ideal_steps": 5,
    "cascade_step": 9,
    "cascade_service": "api-gateway",
    "cascade_fault": "search_timeout_victim",
},
```

---

### 3. `nginx-ingress`
**Why it matters:** Nginx/ingress misconfiguration is the #1 cause of "the whole site is down but everything looks healthy" incidents. Rate limiting, upstream timeout misconfiguration, and worker process crashes each present differently and require different fixes.

**Fault types:**
- `worker_process_crash` — nginx worker processes dying due to OOM, only master is running
- `upstream_timeout_misconfiguration` — `proxy_read_timeout` set to 5s, but upstream services need 30s
- `rate_limit_too_aggressive` — rate limit at 10 req/s per IP is blocking legitimate API clients

**Red herring pairing:** `auth-service` (all auth requests failing because nginx isn't forwarding them, looks like auth is down)

**Key signals for `_make_logs()`:**
```
[ERROR] nginx-ingress: worker process killed (signal 9) — OOM
[ERROR] nginx-ingress: upstream timed out (10060: Connection timed out) reading response header
[WARN]  nginx-ingress: limiting requests, excess: 847.200 by zone "api_limit"
```

**Key signals for `_make_metrics()`:**
```python
"worker_processes_active": 1,
"worker_processes_expected": 4,
"upstream_timeout_rate": 0.45,
"rate_limited_requests_per_sec": 847,
"connections_active": 12000,
"connections_max": 1024
```

**Correct fix:** `rollback_deployment` for misconfiguration faults, `restart_service` for worker crash

**Sample task definition:**
```python
"task_nginx_worker_crash": {
    "name": "Nginx worker process OOM crash",
    "difficulty": "easy",
    "max_steps": 10,
    "description": "Nginx worker processes dying due to OOM. Only master process running. 75% of requests failing.",
    "alert": "ALERT: nginx-ingress error rate 75%. Worker processes 1/4 active. OOM errors in system logs.",
    "fault_service": "nginx-ingress",
    "fault_type": "worker_process_crash",
    "red_herrings": [],
    "ideal_steps": 3,
    "cascade_step": None,
    "cascade_service": None,
    "cascade_fault": None,
},
```

---

### 4. `vault` (HashiCorp Vault)
**Why it matters:** Secret management failures are the most catastrophic and least obvious failure mode in modern infrastructure. When Vault's token expires, every service that needs a database password or API key silently fails — and the symptoms look like network failures or authentication errors, not secret rotation.

**Fault types:**
- `token_lease_expired` — the Vault token used by all services expired, secrets can no longer be renewed
- `seal_status` — Vault was restarted and is still sealed; no secrets can be read
- `policy_misconfiguration` — a policy change removed read access to the `database/creds` path

**Red herring pairing:** `postgres-db` (connection failures because credentials are expired, but postgres itself is healthy)

**Key signals for `_make_logs()`:**
```
[ERROR] vault: token lease expired — last renewal 6h ago, TTL was 4h
[ERROR] vault: Vault is sealed — requests to secret/database/creds failing
[ERROR] vault: permission denied — policy 'app-policy' missing capability 'read' on path 'database/creds'
```

**Correct fix:** `rollback_deployment` → `vault` (policy change rollback) or `declare_rca` for seal/expiry

**Sample task definition:**
```python
"task_vault_token_expired": {
    "name": "Vault token lease expired — all secrets inaccessible",
    "difficulty": "hard",
    "max_steps": 20,
    "description": "Vault token TTL expired 2 hours ago. All services attempting secret renewal are failing silently.",
    "alert": "ALERT: Database connection failures across 4 services. Vault token expired. Credentials cannot be renewed.",
    "fault_service": "vault",
    "fault_type": "token_lease_expired",
    "red_herrings": ["postgres-db", "auth-service"],
    "ideal_steps": 7,
    "cascade_step": 6,
    "cascade_service": "order-service",
    "cascade_fault": "db_credential_victim",
},
```

---

### 5. `celery-worker`
**Why it matters:** Async task queue workers failing is extremely common in Python/Django/FastAPI stacks. Stuck tasks, task routing misconfiguration, and worker memory bloat are all real-world patterns. This adds async/queue reasoning to the benchmark.

**Fault types:**
- `task_queue_drain` — workers processing 0 tasks/sec; queue depth growing unbounded
- `stuck_tasks` — tasks stuck in STARTED state for 45+ minutes (deadlock in task logic)
- `worker_memory_bloat` — celery workers leaking memory, RSS growing to 4GB, OOM kills

**Red herring pairing:** `notification-service` (email jobs not sending because celery workers are dead, but service itself is fine)

**Key signals for `_make_logs()`:**
```
[ERROR] celery-worker: task stuck in STARTED state for 2,847s — possible deadlock
[ERROR] celery-worker: worker[3] killed by OOM killer — RSS 4.1GB exceeded limit
[WARN]  celery-worker: queue depth 15,847 — workers processing 0 tasks/sec
```

**Correct fix:** `restart_service` for memory bloat/stuck workers, `rollback_deployment` for routing misconfiguration

---

## Tier 2 — Application-Layer Services (High Hackathon Score)

### 6. `payment-service`
**Why it matters:** Nothing gets executives paged faster than payment failures. 3rd-party payment processor timeouts vs internal DB deadlocks present almost identically — this is the hardest classification problem in production SRE.

**Fault types:**
- `processor_webhook_timeout` — Stripe webhooks taking 30s to respond, causing synchronous checkout to hang
- `idempotency_key_collision` — duplicate charge attempts due to retry logic creating DB deadlocks
- `currency_conversion_service_down` — all international transactions failing (domestic fine)

**Red herring pairing:** `postgres-db` (transaction deadlocks appear to be DB issue but root cause is upstream Stripe timeout forcing retries)

**Sample task definition:**
```python
"task_payment_processor_timeout": {
    "name": "Payment processor webhook timeout cascade",
    "difficulty": "hard",
    "max_steps": 20,
    "description": "Stripe webhook processing taking 30s. Checkout threads exhausted. Revenue impact critical.",
    "alert": "ALERT: Checkout completion rate 8%. payment-service p99 latency 34s. Stripe webhook timeouts detected.",
    "fault_service": "payment-service",
    "fault_type": "processor_webhook_timeout",
    "red_herrings": ["postgres-db", "order-service"],
    "ideal_steps": 8,
    "cascade_step": 7,
    "cascade_service": "api-gateway",
    "cascade_fault": "checkout_thread_exhaustion",
},
```

---

### 7. `inventory-service`
**Why it matters:** Race conditions on stock updates causing oversell are the nightmare scenario for e-commerce. The failure is intermittent, hard to reproduce, and the signal is in DB query results — not logs or metrics. Forces agents to use `run_db_query` correctly.

**Fault types:**
- `race_condition_oversell` — concurrent stock decrement without locking causes negative inventory
- `stale_cache_oversell` — Redis cache returning stale stock levels, products showing available when sold out
- `bulk_import_lock` — a nightly bulk stock import holding table lock, blocking all reads for 20 minutes

**Red herring pairing:** `redis-cache` (stale metrics make it look like cache is failing, but it's the inventory logic)

---

### 8. `search-service`
**Why it matters:** Adding a dedicated search service that depends on `elasticsearch` creates multi-hop cascade tasks. The agent must trace: `api-gateway` → `search-service` → `elasticsearch` — testing 3-level cascade reasoning.

**Fault types:**
- `index_staleness` — search results 4 hours out of date because indexing pipeline paused
- `query_explosion` — a wildcard query pattern causing full-index scans, timing out all search requests
- `relevancy_model_corruption` — a bad ML model update returning completely irrelevant results (subtle, hard to detect without metrics)

---

### 9. `email-service`
**Why it matters:** Simple, well-understood service — great for easy-difficulty tasks. SMTP relay failures, rate limiting by email provider, and bounce rate spikes are all real and common.

**Fault types:**
- `smtp_relay_down` — the outbound SMTP relay is unreachable; all emails queuing
- `provider_rate_limited` — SendGrid rate limit hit; 429 responses, emails failing silently
- `bounce_rate_spike` — high bounce rate causing provider to suspend account

**Sample task definition:**
```python
"task_email_smtp_relay_down": {
    "name": "SMTP relay unreachable — email queue backing up",
    "difficulty": "easy",
    "max_steps": 10,
    "description": "Outbound SMTP relay at mail.internal:587 is unreachable. All transactional emails queuing.",
    "alert": "ALERT: email-service queue depth 47,832. SMTP relay connection refused. Password reset emails not sending.",
    "fault_service": "email-service",
    "fault_type": "smtp_relay_down",
    "red_herrings": [],
    "ideal_steps": 3,
    "cascade_step": None,
    "cascade_service": None,
    "cascade_fault": None,
},
```

---

### 10. `user-profile-service`
**Why it matters:** Cache invalidation failures are notoriously hard to debug because the service appears healthy. Users see stale data but no errors appear in logs. This tests agents' ability to reason about data consistency, not just uptime.

**Fault types:**
- `cache_invalidation_failure` — profile updates not propagating to cache; users seeing 6-hour-old data
- `data_migration_corruption` — a schema migration silently truncated the `preferences` JSON column
- `read_replica_lag` — read replica 15 minutes behind primary; read-your-writes consistency broken

---

## Tier 3 — Observability & Infrastructure (Expert-Level Tasks)

### 11. `prometheus` (metrics-collector)
**Why it matters:** The meta-twist: monitoring itself fails. When Prometheus scrape targets are down, the agent has no metrics to reason about — it must diagnose using only logs and health checks. This is genuinely expert-level and unprecedented in benchmarks.

**Fault types:**
- `scrape_failure` — Prometheus scrape interval missed for 30 minutes; all metrics stale
- `cardinality_explosion` — a high-cardinality label (request_id) causing 10M time series, OOM
- `remote_write_backpressure` — Thanos remote_write queue full; metrics being dropped

**Red herring pairing:** Everything looks fine (no alerts firing because alerting depends on Prometheus!) — agent must notice the absence of metrics as the signal itself.

**Key diagnostic insight:** `check_metrics` on any service returns stale data from 30 minutes ago. Agent must infer this and run `read_logs` on prometheus directly.

---

### 12. `jaeger` (tracing-service)
**Why it matters:** Distributed tracing infrastructure failure creates a monitoring blindspot that masquerades as application slowness. The agent must distinguish "traces are slow" from "trace ingestion is slow."

**Fault types:**
- `trace_ingestion_lag` — Jaeger collector 30-minute backlog; UI shows 30-min-old traces, misleading investigation
- `sampling_misconfiguration` — sampling rate set to 100% (was 1%) causing 100x traffic to Jaeger, OOM
- `storage_backend_full` — Cassandra backend full; new traces silently dropped

---

### 13. `config-service` (feature flag service)
**Why it matters:** Feature flag service outages are the most insidious because they silently disable product features. When LaunchDarkly/Flagsmith goes down, flags default to OFF — checkout, search, recommendations all stop working with no errors in logs.

**Fault types:**
- `flag_service_outage` — config-service down; all flags defaulting to OFF, disabling checkout flow
- `bad_flag_rollout` — a flag was rolled out to 100% when it should have been 5%; database queries 10x slower
- `stale_flag_cache` — config-service serving flags from 6-hour-old cache after restart

**Red herring pairing:** `order-service` (checkout disabled because flags are off, but order-service code is fine)

**Sample task definition:**
```python
"task_feature_flag_outage": {
    "name": "Feature flag service outage — checkout disabled",
    "difficulty": "medium",
    "max_steps": 15,
    "description": "config-service is down. All feature flags defaulting to OFF. Checkout flow disabled for all users.",
    "alert": "ALERT: Checkout conversion rate 0%. No 500 errors. order-service healthy. Feature flags suspect.",
    "fault_service": "config-service",
    "fault_type": "flag_service_outage",
    "red_herrings": ["order-service"],
    "ideal_steps": 5,
    "cascade_step": 9,
    "cascade_service": "notification-service",
    "cascade_fault": "order_complete_events_stopped",
},
```

---

### 14. `cdn-edge`
**Why it matters:** CDN failures affect 100% of users immediately but are invisible to internal monitoring — all internal services look healthy. The agent must reason about the boundary between internal and external infrastructure.

**Fault types:**
- `origin_pull_storm` — CDN cache purge triggered a thundering herd; origin getting 50x normal traffic
- `cache_poisoning` — a malformed response was cached; 30% of users seeing corrupted HTML
- `ssl_offload_failure` — CDN SSL termination failing; HTTPS requests returning 525 errors

**Red herring pairing:** `api-gateway` (origin traffic spike makes gateway look overloaded, but cdn-edge is the cause)

---

### 15. `k8s-scheduler` (simulated)
**Why it matters:** Kubernetes scheduling failures are the hardest class of infrastructure problem — pods evicted, nodes under pressure, resource quota exhaustion. This is the "expert tier" service that separates 70/100 submissions from 95/100.

**Fault types:**
- `pod_eviction_storm` — node memory pressure causing aggressive pod eviction; services restarting randomly every 2-5 minutes
- `resource_quota_exhausted` — namespace CPU/memory quota hit; new deployments failing silently (existing pods fine)
- `node_notready` — 1 of 3 nodes in NotReady state; pods on that node showing intermittent failures

**Red herring pairing:** `notification-service` (evicted pods look like crashloop, but it's the scheduler causing the evictions)

**Key signals for `_make_logs()`:**
```
[ERROR] k8s-scheduler: node k8s-worker-2 tainted (memory-pressure) — evicting pods
[ERROR] k8s-scheduler: namespace quota exceeded — CPU: 100/100 millicores, new pods pending
[WARN]  k8s-scheduler: pod notification-service-7d8f9 evicted (OOMKilled) — 3rd eviction in 10min
```

**Key signals for `_make_metrics()`:**
```python
"node_status": "NotReady",
"pods_evicted_last_hour": 47,
"node_memory_pressure": True,
"pending_pods": 8,
"namespace_cpu_used_millicores": 1000,
"namespace_cpu_limit_millicores": 1000,
"node_count_ready": 2,
"node_count_total": 3
```

**Sample task definition:**
```python
"task_k8s_node_pressure": {
    "name": "Kubernetes node memory pressure — pod eviction storm",
    "difficulty": "hard",
    "max_steps": 20,
    "description": "k8s-worker-2 in memory pressure. Pods being evicted every 2-5 minutes. Services restarting randomly.",
    "alert": "ALERT: Intermittent restarts across 3 services. k8s-worker-2 memory pressure. 47 pod evictions last hour.",
    "fault_service": "k8s-scheduler",
    "fault_type": "pod_eviction_storm",
    "red_herrings": ["notification-service", "order-service"],
    "ideal_steps": 9,
    "cascade_step": 6,
    "cascade_service": "api-gateway",
    "cascade_fault": "pod_restart_victim",
},
"task_k8s_quota_exceeded": {
    "name": "Kubernetes namespace quota exhausted",
    "difficulty": "medium",
    "max_steps": 15,
    "description": "CPU quota for the production namespace is 100% used. New deployments pending forever. Existing pods running fine.",
    "alert": "ALERT: New deployment of order-service stuck in Pending. CPU quota exhausted. No new pods can schedule.",
    "fault_service": "k8s-scheduler",
    "fault_type": "resource_quota_exhausted",
    "red_herrings": ["order-service"],
    "ideal_steps": 5,
    "cascade_step": None,
    "cascade_service": None,
    "cascade_fault": None,
},
```

---

## Priority Implementation Order

| Priority | Service | New Tasks | Effort | Judge Impact |
|---|---|---|---|---|
| 1 | `kafka-broker` | 2 tasks | Medium | Very High |
| 2 | `vault` | 2 tasks | Low | Very High |
| 3 | `k8s-scheduler` | 2 tasks | Medium | Very High |
| 4 | `nginx-ingress` | 2 tasks | Low | High |
| 5 | `payment-service` | 2 tasks | Medium | High |
| 6 | `celery-worker` | 2 tasks | Low | High |
| 7 | `config-service` | 2 tasks | Low | High |
| 8 | `elasticsearch` | 2 tasks | Medium | High |
| 9 | `email-service` | 1 task | Very Low | Medium |
| 10 | `cdn-edge` | 2 tasks | Low | Medium |
| 11 | `prometheus` | 2 tasks | High | Very High |
| 12 | `inventory-service` | 2 tasks | Medium | Medium |
| 13 | `search-service` | 2 tasks | Medium | Medium |
| 14 | `jaeger` | 1 task | Medium | High |
| 15 | `user-profile-service` | 1 task | Low | Medium |

**With all 15 services added:** 6 existing + 15 new = **21 services**, **14 existing + ~27 new = 41 tasks** across easy/medium/hard/expert tiers.

---

## Updated SERVICES list for `environment.py`

```python
SERVICES = [
    # Existing
    "api-gateway",
    "auth-service",
    "order-service",
    "notification-service",
    "redis-cache",
    "postgres-db",
    # New Tier 1
    "kafka-broker",
    "elasticsearch",
    "nginx-ingress",
    "vault",
    "celery-worker",
    # New Tier 2
    "payment-service",
    "inventory-service",
    "search-service",
    "email-service",
    "user-profile-service",
    # New Tier 3
    "prometheus",
    "jaeger",
    "config-service",
    "cdn-edge",
    "k8s-scheduler",
]
```

---

*Built for OpenEnv × Scaler × Meta Hackathon 2026. Based on real incidents at Netflix, Stripe, Cloudflare, AWS, GitHub, Discord, and Shopify.*
