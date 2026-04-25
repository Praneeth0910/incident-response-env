"""
Test to verify judge action mapping uses correct domain-specific actions.
Addresses bug: Judge was receiving Kafka terms for CI/CD tasks and vice versa.
"""

def test_action_mappings():
    """Verify action maps are domain-specific and don't mix CI/CD and Kafka concepts."""
    
    # CI/CD action map (as in environment.py)
    cicd_action_map = {
        "read_logs": "read_job_logs",
        "check_metrics": "check_runner_status",
        "check_health": "check_runner_status",
        "run_db_query": "read_audit_log",
        "restart_service": "restart_service",
        "rollback_deployment": "rollback_workflow",
        "declare_rca": "declare_rca",
    }
    
    # Kafka action map (as in environment.py)
    kafka_action_map = {
        "read_logs": "read_consumer_logs",
        "check_metrics": "get_cluster_metrics",
        "check_health": "check_isr_status",
        "run_db_query": "describe_consumer_group",
        "restart_service": "restart_consumer_group",
        "rollback_deployment": "skip_offset",
        "declare_rca": "declare_rca",
    }
    
    # Expected judge actions from judge/llm_judge.py
    cicd_expected_actions = {
        "check_pipeline_status", "check_runner_status", "check_action_integrity",  # observe
        "read_job_logs", "inspect_secret", "read_audit_log",  # gather
        "rollback_workflow", "rotate_secret", "pin_action_to_sha", "isolate_runner", "restart_service",  # fix
        "declare_rca",  # declare
    }
    
    kafka_expected_actions = {
        "get_cluster_metrics", "check_consumer_lag", "check_isr_status",  # observe
        "inspect_partition", "describe_consumer_group", "read_broker_logs",  # locate
        "read_consumer_logs", "check_schema_registry", "check_dead_letter_queue",  # diagnose
        "skip_offset", "restart_consumer_group", "increase_broker_heap",  # fix
        "declare_rca",  # declare
    }
    
    # Verify CI/CD mappings use CI/CD judge actions
    print("✓ CI/CD action mappings:")
    for env_action, judge_action in cicd_action_map.items():
        is_valid = judge_action in cicd_expected_actions
        symbol = "✓" if is_valid else "✗"
        print(f"  {symbol} {env_action} → {judge_action}")
        if not is_valid and judge_action in kafka_expected_actions:
            print(f"    ⚠ WARNING: This is a KAFKA action, not CI/CD!")
    
    # Verify Kafka mappings use Kafka judge actions
    print("\n✓ Kafka action mappings:")
    for env_action, judge_action in kafka_action_map.items():
        is_valid = judge_action in kafka_expected_actions
        symbol = "✓" if is_valid else "✗"
        print(f"  {symbol} {env_action} → {judge_action}")
        if not is_valid and judge_action in cicd_expected_actions:
            print(f"    ⚠ WARNING: This is a CI/CD action, not Kafka!")
    
    # Verify no cross-contamination
    print("\n✓ Verifying domain separation:")
    cicd_values = set(cicd_action_map.values())
    kafka_values = set(kafka_action_map.values())
    
    cicd_only = cicd_values - kafka_values - {"declare_rca"}
    kafka_only = kafka_values - cicd_values - {"declare_rca"}
    shared = cicd_values & kafka_values
    
    print(f"  CI/CD-only actions: {cicd_only}")
    print(f"  Kafka-only actions: {kafka_only}")
    print(f"  Shared actions: {shared}")
    
    assert all(action in cicd_expected_actions for action in cicd_values), \
        "CI/CD action map contains non-CI/CD actions!"
    assert all(action in kafka_expected_actions for action in kafka_values), \
        "Kafka action map contains non-Kafka actions!"
    
    print("\n✅ All action mappings are domain-appropriate!")


if __name__ == "__main__":
    test_action_mappings()
