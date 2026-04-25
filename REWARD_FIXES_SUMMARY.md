# Reward Design Fixes Summary

## Overview
Fixed 4 reward design issues that were hurting RL learning quality.

---

## Issue A: Time Pressure Penalized Correct Late Actions ❌ → ✅

**Problem**:
```python
scale = 0.99 - 0.4 * ((progress - 0.5) / 0.5)  # Dropped to 0.59x at step 14/15
reward_value = round(reward_value * scale, 4)
```
- Correct actions in second half of episode got heavily scaled down
- At step 14/15, correct restart_service gave only ~0.59 × 0.35 = 0.21 instead of 0.35
- This taught RL agents: "doing the right thing late is worse than doing nothing"
- Agents would learn to either solve fast or give up

**Fix**:
- **Removed positive reward scaling entirely** (environment.py line 936-947)
- Only negative rewards scale up under time pressure (encourage urgency for mistakes)
- Time bonus in declare_rca already incentivizes efficiency
- Late correct actions now get full reward

**Verification**:
```
Early restart (step 3/10): 0.1500
Late restart (step 8/10):  0.1500
Difference: 0.0000 ✓
```

---

## Issue C: Sequence Bonus Floor Too High ❌ → ✅

**Problem**:
```python
return 0.2  # blind action got 20% sequence bonus
```
- Blind restart with zero evidence got 0.35 × 0.2 = 0.07 positive reward
- Agent could spam blind restarts (6 services × 0.07 = 0.42) then declare correct RCA
- Blind actions should get NO reward

**Fix**:
1. **Changed sequence bonus floor from 0.2 to 0.0** (environment.py line 538)
2. **reward.py returns 0.0 directly for blind fix actions** (reward.py lines 96-104)

```python
if evidence_count == 0:
    return 0.0  # no reward for blind action
```

**Verification**:
```
Blind restart reward: 0.0 ✓
Restart with evidence: 0.15 ✓
```

---

## Issue D: Rollback Fixes List Mismatch ❌ → ✅

**Problem**:
```python
_rollback_fixes = ("bad_deployment", "canary_misconfiguration",
                   "cert_expired", "rate_limit_exceeded",
                   "slow_query", "clock_skew")
```
- `connection_pool_exhausted` is a runtime leak → needs **restart_service**, not rollback
- `cert_expired` needs cert rotation, not rollback
- `slow_query` needs index creation, not rollback
- `clock_skew` needs NTP sync/restart, not rollback

**Fix**:
```python
_rollback_fixes = ("bad_deployment", "canary_misconfiguration")
```
- **Reduced to only deployment-related faults** (environment.py line 799)
- test/test_reward_shaping.py explicitly verifies no invalid entries

**Verification**:
```
Required entries found: ['bad_deployment', 'canary_misconfiguration'] ✓
Invalid entries found: None ✓
```

---

## Issue B: Wrong RCA Evidence Credit

**Status**: ✅ **NO CHANGE NEEDED** - Working as intended

Wrong RCA caps score at min(0.15, evidence_count * 0.03):
- 3 evidence signals: 0.09
- 5 evidence signals: 0.15
- Barely above 0.001 floor

This is **correct** - wrong RCA should be heavily punished even with evidence gathering.

---

## Files Modified

### environment.py
- **Line 538**: Sequence bonus floor 0.2 → 0.0 for blind actions
- **Line 799-801**: rollback_fixes reduced to deployment-only faults
- **Line 936-947**: Removed positive reward time scaling

### reward.py
- **Line 96-104**: Return 0.0 directly for blind fix actions

### test/test_reward_shaping.py
- Updated test #3 expectation from 0.07 to 0.0 for blind rollback

---

## Test Results

### New comprehensive test: test_reward_design_fixes.py
```
[OK] PASS: Issue A: Time Pressure
[OK] PASS: Issue C: Blind Action  
[OK] PASS: Issue C: Evidence Rewards
[OK] PASS: Issue D: Rollback Fixes
[OK] PASS: Negative Scaling
[SUCCESS] ALL TESTS PASSED!
```

### Regression tests:
```
test/test_presubmit.py: 15 passed, 3 skipped ✓
test/test_reward_shaping.py: All tests PASS ✓
```

---

## Impact on RL Training

**Before fixes**:
- Late correct actions penalized → agents give up
- Blind restarts rewarded → agents spam random fixes
- Wrong fix types mapped → confusing learning signals

**After fixes**:
- Correct actions get full reward regardless of timing ✓
- Blind actions get zero reward → must gather evidence ✓
- Fix types correctly mapped to fault types ✓
- Efficiency still incentivized via declare_rca time bonus ✓

---

## Recommendations

1. ✅ **Issue A**: Fixed - positive rewards no longer scaled
2. ✅ **Issue C**: Fixed - blind actions get 0.0 reward
3. ✅ **Issue D**: Fixed - rollback_fixes cleaned up
4. ✅ **Issue B**: No change needed - correct as is

**Next steps**: Monitor SFT data generation to verify agents learn better investigation patterns.
