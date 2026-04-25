"""
Observation generation and formatting.
Keeps observation logic centralized and testable.
"""

from typing import Any, Dict, Optional

from models import Observation


def format_observation(
    message: str,
    step: int,
    done: bool,
    alert: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> Observation:
    """
    Format an observation.
    
    Args:
        message: Main observation message
        step: Current step number
        done: Whether episode is done
        alert: Alert message
        metrics: Optional metrics dict
        
    Returns:
        Observation object
    """
    return Observation(
        message=message,
        step=step,
        done=done,
        alert=alert,
        metrics=metrics,
    )


def format_logs_observation(service: str, logs: str, step: int) -> Observation:
    """Format logs as observation."""
    return format_observation(
        message=f"Logs from {service}:\n{logs}",
        step=step,
        done=False,
        alert="",
        metrics=None,
    )


def format_metrics_observation(service: str, metrics_dict: Dict[str, Any], step: int) -> Observation:
    """Format metrics as observation."""
    return format_observation(
        message=f"Metrics for {service}: {metrics_dict}",
        step=step,
        done=False,
        alert="",
        metrics={service: metrics_dict},
    )


def format_health_observation(service: str, status: str, step: int) -> Observation:
    """Format health check as observation."""
    return format_observation(
        message=f"Health check {service}: {status}",
        step=step,
        done=False,
        alert="",
        metrics=None,
    )


def format_db_query_observation(query_result: str, step: int) -> Observation:
    """Format DB query result as observation."""
    return format_observation(
        message=f"DB query result:\n{query_result}",
        step=step,
        done=False,
        alert="",
        metrics=None,
    )
