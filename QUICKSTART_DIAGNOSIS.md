# Diagnostic Demo — 60 Second Walkthrough

## The Scenario

Saturday 3:47 AM. You're on call. Denver colo: **23 devices unreachable**.

Your alarms:
```
NODE-UNREACH   (critical)
AC-INPUT-FAIL  (major)
BATTERY-MODE   (warning)
```

**Question:** What broke? And what's the cheapest way to confirm before dispatching a $1200 truck?

## Run the Demo

```bash
# The automated demo (shows ASP reasoning)
uv run python demo_diagnosis.py
```

## What You'll See

### 1. Multiple Hypotheses from One Alarm Pattern

A rule engine would guess "power outage" and stop.

ASP **enumerates every minimal explanation**:

```
Answer Set 1: { utility_power_outage }
Answer Set 2: { ups_battery_depleted }
Answer Set 3: { upstream_aggregation_down }
Answer Set 4: { hvac_failure_thermal }
```

**POSSIBLE** = what could be true (union of all worlds)  
**CERTAIN** = what must be true (intersection of all worlds)

### 2. Contradicted Records Surface as "Unverified"

Your inventory systems disagree:

```
site_has_generator:
  • OneVizion says NO (60% conf, 5 days old)
  • HyperLink says YES (85% conf, 60 days old)
```

A rule engine picks one. Datalog closes-world and drops the other.

**ASP marks it CONTRADICTED** and tells you:
> This hypothesis is PROVISIONAL — depends on a record you must verify.

### 3. Cost-Optimal Test Selection

The solver could dispatch a $1200 truck. Instead it recommends:

```bash
query_power_telemetry ($1) — SNMP to PDU/UPS
```

**Result:** `ac_absent` (utility power is down)

The solver **re-solves** with this new fact:

```
After Round 1:
  Ruled out: upstream_aggregation_down, hvac_failure
  Confirmed: utility_power_outage
```

### 4. The Critical Dependency

```
⚠️  Diagnosis depends on: site_has_generator

  No generator → UPS depletes in 90min → total outage
  Has generator → may auto-start → wait
```

You check HyperLink work orders:

```
WO-2847 (240 days ago):
  "Generator decommissioned — end of service contract"
```

OneVizion was right. HyperLink was stale.

### 5. Final Diagnosis

```
✓ DIAGNOSIS COMPLETE

Root Cause: Utility power outage
Critical Finding: No backup generator
Impact: UPS depleted in ~90 minutes

IMMEDIATE ACTION:
  1. Controlled shutdown of non-critical systems
  2. Dispatch truck for generator rental
  3. Notify customers

Diagnostic cost: $1 · Time: 4 minutes
Alternative (guess): $1200 · 90+ minutes
```

## Why This Can't Be Done Without ASP

| Capability | Rule Engine | Datalog | ASP |
|---|---|---|---|
| **Enumerate all minimal explanations** | ❌ picks one | ❌ derives all (not minimal) | ✅ answer sets |
| **Keep contradicted records visible** | ❌ picks higher confidence | ❌ closed-world | ✅ three-valued logic |
| **Optimize test sequence** | ❌ | ❌ | ✅ #minimize |

### What ASP Does

```prolog
hypothesis(utility_power_outage).
hypothesis(hvac_failure_thermal).

explains(utility_power_outage,      ac_input_fail).
explains(utility_power_outage,      battery_mode).
explains(hvac_failure_thermal,      high_temperature).

test(query_power_telemetry).   test_cost(query_power_telemetry, 1).
test(site_visit).              test_cost(site_visit, 40).

confirms(query_power_telemetry, ac_absent, utility_power_outage).

% Find all minimal fault sets
{ fault(H) } :- hypothesis(H).
:- fault(H), explains(H,S), not observed(S).
#minimize { 1,H : fault(H) }.

% Pick cheapest tests to discriminate
{ do_test(T) } :- useful(T).
:- possible(H1), possible(H2), H1 != H2, not discriminated(H1, H2).
#minimize { C,T : do_test(T), test_cost(T,C) }.
```

Clingo:
1. Enumerates every minimal fault set (answer sets)
2. Compares them to find POSSIBLE vs CERTAIN
3. Optimizes test selection to discriminate

**That's ~40 lines of logic.** In Python you'd write a backtracking SAT solver,
a three-valued model checker, and an ILP optimizer.

## Try It

```bash
# Simple power outage
uv run python demo_diagnosis.py

# Multi-fault scenario (power + HVAC)
uv run compli work tickets/den_multi_fault.json \
  --knowledge knowledge/vendor_codes.lp \
  --knowledge knowledge/datacenter_faults.lp
```

## Read More

- [WHY_ASP.md](WHY_ASP.md) — Full explanation of why ASP is uniquely suited
- [scenarios/production_outage.md](scenarios/production_outage.md) — The realistic scenario narrative
- [knowledge/datacenter_faults.lp](knowledge/datacenter_faults.lp) — The knowledge base

---

**TL;DR:** ASP enumerates minimal explanations, keeps "unverified" distinct from "false",
and optimizes test selection — all in one pass. That's why this demo works.
