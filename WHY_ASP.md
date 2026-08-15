# Why Answer Set Programming for Ticket Diagnosis?

This isn't just "rules + optimization" — ASP does three things **no other approach can**.

## The Problem Other Systems Can't Solve

You get a ticket with alarms: `NODE-UNREACH`, `AC-INPUT-FAIL`, `BATTERY-MODE`.

**Question:** What broke, and what's the cheapest way to confirm?

### What a Rule Engine Does (Wrong)

```python
if alarm == "AC-INPUT-FAIL":
    return "utility_power_outage"  # ← assumes this is THE answer
```

**Problem:** It picks ONE explanation. But what if:
- Power AND HVAC both failed?
- The AC alarm is wrong and it's actually upstream?
- You have contradictory data about whether there's a backup generator?

A rule engine gives you an answer. It cannot tell you **what else could be true**.

### What Datalog Does (Also Wrong)

```prolog
fault(utility_power_outage) :- alarm(ac_input_fail), alarm(battery_mode).
fault(hvac_failure) :- alarm(high_temperature), alarm(node_unreachable).
```

Datalog derives **everything that COULD be true**. It's a monotonic engine:
- `utility_power_outage` is derived → TRUE
- `hvac_failure` is NOT derived → **FALSE** (closed-world assumption)

**Problem:** If you haven't observed `high_temperature` yet, Datalog says HVAC is fine.
That's not "unknown" — that's a **false negative**.

### What Probabilistic Reasoning Does (Expensive)

Bayesian networks or Markov logic would model uncertainty:

```
P(utility_power_outage | ac_fail, battery_mode, no_generator) = 0.87
P(hvac_failure | temp_high) = 0.72
```

**Problem:**
1. You need training data to learn the probabilities
2. It doesn't tell you what TEST to run next
3. It doesn't handle contradictory records (two sources disagree on generator status)
4. It's probabilistic — you get a score, not a minimal set of faults

## What ASP Does Differently

### 1. Enumerates POSSIBLE WORLDS

ASP doesn't derive one answer — it finds **every minimal explanation** consistent with the evidence.

From `NODE-UNREACH + AC-INPUT-FAIL + BATTERY-MODE`, clingo returns **multiple answer sets**:

```prolog
Answer Set 1: { fault(utility_power_outage) }
Answer Set 2: { fault(ups_battery_depleted) }
Answer Set 3: { fault(upstream_aggregation_down) }
```

Each answer set is ONE way things could be. The union is what's **POSSIBLE**. The intersection is what's **CERTAIN**.

```
POSSIBLE = {utility_power_outage, ups_battery_depleted, upstream_aggregation_down}
CERTAIN  = {} (nothing is in all three worlds)
```

**This is the "multiple hypotheses" state** a human oncall engineer holds in their head. No other system models it.

### 2. Three-Valued Logic (Not Two)

A fact has **three states**:

| State | Meaning | ASP Representation |
|---|---|---|
| `established` | Evidence confirms it | All answer sets agree |
| `refuted` | Evidence contradicts it | Appears in zero answer sets |
| `unverified` | Nobody checked yet | Appears in some, not all |

Example:

```prolog
% Two sources contradict each other on generator status
source_asserts(onevizion, site_has_generator, false, 60, 5).
source_asserts(hyperlink, site_has_generator, true, 85, 60).
```

ASP doesn't pick one — it marks `site_has_generator` as **CONTRADICTED** and tells you
"this record is not trustworthy, verify it before acting."

Datalog would close-world one source and drop the other.
A rule engine would pick the higher confidence and move on.
**ASP keeps the contradiction visible.**

### 3. Cost-Optimal Test Selection

Once you have multiple possible worlds, ASP can solve:

> **What is the cheapest set of tests that would tell these worlds apart?**

This is a **weighted set cover problem** — NP-complete in general, but clingo's `#minimize` solves it:

```prolog
test(query_power_telemetry).   test_cost(query_power_telemetry, 1).
test(site_visit).               test_cost(site_visit, 40).

rules_out(query_power_telemetry, ac_present, utility_power_outage).
confirms(query_power_telemetry, ac_absent, utility_power_outage).

#minimize { C,T : do_test(T), test_cost(T,C) }.
```

Clingo picks `query_power_telemetry` ($1) instead of `site_visit` ($40) because
it discriminates between the surviving hypotheses at 1/40th the cost.

**No rule engine or Datalog system can do this.** They evaluate rules; they don't optimize plans.

## The ASP Diagnostic Loop

```
1. Load ticket (alarms + contradictory records)
   ↓
2. Clingo finds ALL minimal fault sets (answer sets)
   ↓
3. Compare them:
   - What's POSSIBLE? (union)
   - What's CERTAIN? (intersection)
   - What's PROVISIONAL? (depends on contradicted records)
   ↓
4. Clingo picks cheapest tests to discriminate
   ↓
5. Run the test, get the result
   ↓
6. Add result as a fact, GOTO 2 (re-solve)
   ↓
7. Terminate when:
   - SOLVED: one hypothesis survives with all facts verified
   - IMPASSE: no test would change the answer (dispatch truck)
```

Each re-solve is a fresh grounding over the accumulated evidence. **The diagnosis converges**:

```
Round 1: 4 hypotheses live
Round 2 (after $1 telemetry): 2 hypotheses live
Round 3 (after field check): 1 hypothesis confirmed → SOLVED
```

## What This Looks Like in Code

### The Knowledge Base (Pure Logic)

```prolog
hypothesis(utility_power_outage).
hypothesis(hvac_failure_thermal).
hypothesis(upstream_aggregation_down).

explains(utility_power_outage,      ac_input_fail).
explains(utility_power_outage,      battery_mode).
explains(utility_power_outage,      node_unreachable).

explains(hvac_failure_thermal,      node_unreachable).
explains(hvac_failure_thermal,      high_temperature).

explains(upstream_aggregation_down, node_unreachable).

% A fault is live if all its symptoms are observed
{ fault(H) } :- hypothesis(H).
:- fault(H), explains(H,S), not observed(S).

% Minimize the fault set (Occam's razor)
#minimize { 1,H : fault(H) }.
```

### The Test Planning Layer

```prolog
test(query_power_telemetry).     test_cost(query_power_telemetry, 1).
test(check_hvac_status).          test_cost(check_hvac_status, 2).
test(site_visit).                 test_cost(site_visit, 40).

rules_out(query_power_telemetry, ac_present, utility_power_outage).
confirms(query_power_telemetry,  ac_absent,  utility_power_outage).

rules_out(check_hvac_status, operational, hvac_failure_thermal).
confirms(check_hvac_status,  failed,      hvac_failure_thermal).

% A test is useful if it discriminates between possible faults
useful(T) :- test(T), confirms(T,_,H), possible(H).
useful(T) :- test(T), rules_out(T,_,H), possible(H).

% Pick the cheapest useful tests
{ do_test(T) } :- useful(T).

% You must be able to tell faults apart
:- possible(H1), possible(H2), H1 != H2, 
   not discriminated(H1, H2).

discriminated(H1, H2) :- do_test(T), confirms(T,_,H1), rules_out(T,_,H2).
discriminated(H1, H2) :- do_test(T), confirms(T,_,H2), rules_out(T,_,H1).

#minimize { C,T : do_test(T), test_cost(T,C) }.
```

**This is declarative.** You describe:
- What symptoms each fault produces
- What tests exist and their costs
- What outcomes tell faults apart

Clingo **figures out** what tests to run and in what order.

## The Three Things Only ASP Can Do

| Capability | Rule Engine | Datalog | Bayes Net | ASP |
|---|---|---|---|---|
| **Enumerate all minimal explanations** | ❌ picks one | ❌ derives all (not minimal) | ✅ but probabilistic | ✅ deterministic minimal sets |
| **Three-valued logic (unverified ≠ false)** | ❌ | ❌ closed-world | ❌ | ✅ open-world via answer sets |
| **Cost-optimal test selection** | ❌ | ❌ | ❌ | ✅ #minimize |

## Why Not Just Write This in Python?

You could. But:

1. **Enumerating minimal fault sets** is backtracking search over a constraint space.
   You'd write a SAT solver.

2. **Three-valued logic** means modeling what's true in EVERY possible world vs SOME vs NONE.
   You'd write a model checker.

3. **Optimization** means finding the cheapest plan subject to "must discriminate all pairs."
   You'd write an ILP solver.

**Or you write 150 lines of ASP and clingo does all three.**

## The Demo

Run this:

```bash
uv run python demo_diagnosis.py
```

You'll see:
- 4 hypotheses enumerated from alarms
- Contradicted records surfaced (generator status)
- Cheapest test recommended ($1 vs $1200 truck roll)
- Diagnosis converges to root cause in 3 rounds

**That's ASP.** It's not "smarter rules" — it's a different computational model.

## Compare to the Compliance Inspection Use Case

The README shows using ASP for **compliance inspection**:
- Rules from a 121-page engineering standard
- "What evidence would close all gaps?" → set cover optimization
- Three-valued logic: satisfied / violated / **undetermined**

**Same solver, different domain.** ASP is good at:
- Problems where "unknown" ≠ "false"
- Multiple explanations need to be considered simultaneously
- You need the cheapest plan to disambiguate

Both compliance (what to capture) and diagnosis (what broke) fit that shape.

---

**TL;DR:** ASP is the only system that enumerates minimal explanations, keeps "unverified" distinct from "false", and optimizes test selection — all in one pass. That's why it works for diagnostic tickets.
