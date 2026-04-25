from environment import IncidentResponseEnv
from models import Action

env = IncidentResponseEnv()
obs = env.reset('task_cpu_spike')
a = Action(action_type='read_logs', target='auth-service')
obs, rew, done, info = env.step(a)
print('obs.message[:200] =', obs.message[:200])
print('reward =', rew.value, 'reason =', rew.reason)
print('done =', done)
print('info keys =', list(info.keys()))
print('judge_score =', info.get('judge_score'))
print('judge_feedback =', info.get('judge_feedback'))
