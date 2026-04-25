from copy import deepcopy

from services import (
    SERVICE_REGISTRY,
    ServiceStatus,
    propagate_failure,
    update_metrics,
)


def test_propagate_failure_accepts_task_fault_strings():
    registry = deepcopy(SERVICE_REGISTRY)

    impact = propagate_failure(
        "auth-service",
        fault_type="cpu_spike",
        registry=registry,
    )

    assert registry["auth-service"].status == ServiceStatus.DOWN
    assert registry["auth-service"].root_cause_fault == "cpu_spike"
    assert impact["root_fault_type"] == "cpu_spike"


def test_update_metrics_mutates_isolated_registry_only():
    registry = deepcopy(SERVICE_REGISTRY)

    updated = update_metrics(
        "auth-service",
        {"cpu_pct": 99, "thread_pool_active": 200},
        registry=registry,
    )

    assert updated["cpu_pct"] == 99
    assert registry["auth-service"].status == ServiceStatus.DOWN
    assert SERVICE_REGISTRY["auth-service"].current_metrics == {}
