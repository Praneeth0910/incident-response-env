import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from environment import IncidentResponseEnv

@pytest.fixture
def env():
    return IncidentResponseEnv()

@pytest.fixture
def easy_env(env):
    env.reset("task_cpu_spike", seed=42)
    return env

@pytest.fixture
def hard_env(env):
    env.reset("task_canary_poison", seed=42)
    return env
