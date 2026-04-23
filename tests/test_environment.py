import pytest
from environment import IncidentResponseEnv
from models import Action

# ── reset ──────────────────────────────────────────────────────────────────

def test_reset_returns_observation(env):
    obs = env.reset("task_cpu_spike", seed=0)
    assert obs.step == 0
    assert obs.done is False
    assert len(obs.message) > 0

def test_reset_is_deterministic(env):
    obs1 = env.reset("task_canary_poison", seed=99)
    obs2 = env.reset("task_canary_poison", seed=99)
    assert obs1.message == obs2.message

def test_reset_clears_prior_state(env):
    env.reset("task_cpu_spike", seed=0)
    env.step(Action(action_type="read_logs", target="api-gateway"))
    env.reset("task_cpu_spike", seed=0)
    assert env._step_count == 0
    assert env._cumulative_reward == 0.0
    assert len(env._actions_taken) == 0


# ── step ───────────────────────────────────────────────────────────────────

def test_step_increments_count(easy_env):
    obs, rew, done, info = easy_env.step(
        Action(action_type="check_health", target="api-gateway")
    )
    assert info["step"] == 1

def test_step_before_reset_raises(env):
    with pytest.raises(RuntimeError):
        env.step(Action(action_type="check_health", target="api-gateway"))

def test_redundant_action_penalised(easy_env):
    a = Action(action_type="check_health", target="api-gateway")
    easy_env.step(a)
    _, rew, _, _ = easy_env.step(a)
    assert rew.value == 0.005

def test_correct_rca_gives_positive_reward(env):
    env.reset("task_cpu_spike", seed=0)
    _, rew, done, _ = env.step(
        Action(action_type="declare_rca", target="auth-service")
    )
    assert rew.value > 0.0
    assert done is True

def test_wrong_rca_gives_minimal_reward(env):
    env.reset("task_cpu_spike", seed=0)
    _, rew, done, _ = env.step(
        Action(action_type="declare_rca", target="api-gateway")
    )
    assert rew.value <= 0.01
    assert done is True

def test_grade_before_done_returns_low(env):
    env.reset("task_cpu_spike", seed=0)
    assert env.grade() == 0.001

def test_grade_after_correct_rca_is_reasonable(env):
    env.reset("task_cpu_spike", seed=0)
    env.step(Action(action_type="read_logs", target="auth-service"))
    env.step(Action(action_type="check_metrics", target="auth-service"))
    env.step(Action(action_type="declare_rca", target="auth-service"))
    score = env.grade()
    assert 0.5 < score < 1.0

def test_grade_clamped_to_range(env):
    env.reset("task_canary_poison", seed=0)
    env.step(Action(action_type="declare_rca", target="wrong-service"))
    score = env.grade()
    assert 0.001 <= score <= 0.999

def test_episode_ends_at_max_steps(env):
    env.reset("task_cpu_spike", seed=0)
    done = False
    for _ in range(15):
        services = ["api-gateway", "auth-service", "order-service",
                    "notification-service", "redis-cache", "postgres-db"]
        import itertools
        for svc in itertools.cycle(services):
            _, _, done, _ = env.step(
                Action(action_type="check_health", target=svc)
            )
            if done:
                break
        if done:
            break
    assert done is True
def test_models_literal_matches_tasks():
    from environment import TASKS
    from models import ResetRequest
    import inspect, typing
    hints = typing.get_type_hints(ResetRequest)
    literal_args = set(typing.get_args(hints["task_id"]))
    assert set(TASKS.keys()) == literal_args, \
        f"Mismatch: env has {set(TASKS.keys()) - literal_args}, models has {literal_args - set(TASKS.keys())}"
def test_models_literal_matches_tasks():
    from environment import TASKS
    from models import ResetRequest
    import inspect, typing
    hints = typing.get_type_hints(ResetRequest)
    literal_args = set(typing.get_args(hints['task_id']))
    assert set(TASKS.keys()) == literal_args, \
        f'Mismatch: env has {set(TASKS.keys()) - literal_args}, models has {literal_args - set(TASKS.keys())}'
def test_models_literal_matches_tasks():
    from environment import TASKS
    from models import ResetRequest
    import inspect, typing
    hints = typing.get_type_hints(ResetRequest)
    literal_args = set(typing.get_args(hints['task_id']))
    assert set(TASKS.keys()) == literal_args, \
        f'Mismatch: env has {set(TASKS.keys()) - literal_args}, models has {literal_args - set(TASKS.keys())}'
