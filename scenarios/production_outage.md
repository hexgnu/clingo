# Production Outage Scenario — Denver Colocation

## Situation

**Time:** 03:47 MT, Saturday  
**Status:** You're on-call. Your phone just went off.

```
🚨 PagerDuty Alert
Priority: P1
Service: Denver colo — customer connectivity  
Count: 23 alarms in last 2 minutes
```

You SSH into the NOC dashboard. The alarm console is scrolling:

```
03:47:03 [CRITICAL] rtr_den_252: LOS-A2 (uplink loss of signal)
03:47:03 [MAJOR]    rtr_den_252: NODE-UNREACH
03:47:04 [CRITICAL] rtr_den_114: LOS-A2  
03:47:04 [MAJOR]    rtr_den_114: NODE-UNREACH
03:47:05 [CRITICAL] rtr_den_088: NODE-UNREACH
03:47:05 [WARNING]  ups_den_dc2: BATTERY-MODE
03:47:06 [MAJOR]    pdu_den_r12: AC-INPUT-FAIL
...
```

**Your problem:**
- 23 routers offline across Denver
- Some report `LOS-A2` (fiber), some just unreachable
- UPS battery warning suggests power event
- Customer SLA clock is running — every minute costs $$
- You've never been to this site
- It's 4am, the senior engineer is unreachable

**Records available:**
- OneVizion (network inventory) — last sync 3 weeks ago
- Samsung NMS (alarm source) — live
- HyperLink (facility mgmt) — spotty updates, contractor-maintained
- Old migration spreadsheet — 6 months stale

## Your Mission

**Figure out:**
1. What broke?
2. Is it one thing or multiple failures?
3. What's the cheapest way to confirm without flying blind?
4. Do you dispatch a truck, or can you fix it remotely?

## What You DON'T Know

- Which routers share power (records conflict)
- Which fiber runs share a conduit (not documented)
- Whether the UPS warning is cause or symptom
- If this is malicious (last week's "routine" outage was a fiber cut by construction crew)

## The Catch

- **Truck roll:** $1200 + 90min ETA (Saturday night, remote site)
- **Wrong diagnosis:** Customer impact extends, potential penalty
- **Defensive testing:** Running every diagnostic wastes 30-45 minutes

**You need high confidence before you act.**

## Using The Diagnostic System

This scenario is captured in `tickets/den_outage_live.json`. The system doesn't know the answer either — it will help you **reason through the uncertainty**.

### Step 1: Load the ticket

```bash
uv run eiguide triage tickets/den_outage_live.json
```

The system enumerates **possible explanations** consistent with the alarms, accounting for:
- Contradictory records (OneVizion vs HyperLink vs old migration data)
- Multi-source correlation (23 routers = cascading failure, not 23 independent faults)
- Partial observability (you haven't looked at anything yet)

### Step 2: Review the diagnostic plan

The solver proposes **the cheapest sequence of checks** that would discriminate between hypotheses:

```
Possible causes (4 minimal worlds):
  1. Facility power failure (UPS depleted)
  2. Fiber bundle cut (shared conduit)
  3. Upstream aggregation router down
  4. Site HVAC failure → equipment thermal shutdown

Recommended tests (cost-ordered):
  ├─ query_power_telemetry ($0 — remote API)
  │  → settles: facility power vs equipment fault
  │
  ├─ check_upstream_alarms ($0 — NMS query)
  │  → settles: upstream outage vs local fault
  │
  ├─ read_optical_power ($1/port — remote)
  │  → tells apart: fiber cut vs upstream down
  │
  └─ site_visit ($1200 — truck + tech)
     → ONLY if telemetry contradicts or is unavailable
```

### Step 3: Run the diagnosis interactively

```bash
uv run eiguide work tickets/den_outage_live.json
```

You're walked through the cheapest tests first. After each result, the system **re-solves** — narrowing or eliminating hypotheses based on what you just learned.

```
┌─ Round 1: query_power_telemetry ──────────────────┐
│ Querying PDU and UPS SNMP...                      │
│                                                    │
│ Result: AC-ABSENT (utility power down)            │
│         Battery: 40% (est. 90min remaining)       │
└────────────────────────────────────────────────────┘

Ruled out: upstream outage, fiber bundle cut, HVAC failure
Confirmed: facility power failure

Live explanations: 1 (certain)
  • Utility power outage (site running on UPS)

Contradictory evidence: NONE
Unverified assumptions: site_has_generator (claimed by HyperLink 85% confidence, 
                                            denied by OneVizion 60% confidence)

┌─ Follow-up question ──────────────────────────────┐
│ Does the Denver site have a backup generator?    │
│ This determines whether to:                       │
│   • Wait for UPS (if generator coming online)    │
│   • Immediate truck roll (if no generator)       │
│                                                    │
│ Verify via: site visit OR HyperLink work orders  │
└────────────────────────────────────────────────────┘
```

You check HyperLink. A work order from 8 months ago: **"Generator decommissioned — end of service contract."** The OneVizion record was right.

```
┌─ Round 2: Updated facts ──────────────────────────┐
│ field_check(site_has_generator, false)            │
└────────────────────────────────────────────────────┘

╭────────── DIAGNOSIS COMPLETE ─────────────╮
│ Root cause: Utility power outage          │
│ Secondary: No backup generator            │
│ Impact: UPS depleted in ~90 minutes       │
│                                            │
│ Recommended action:                       │
│   IMMEDIATE: Controlled shutdown of       │
│   non-critical systems to extend UPS      │
│                                            │
│   DISPATCH: Truck roll to site for        │
│   generator rental + fuel                 │
│                                            │
│ Diagnosis cost: $0 (telemetry only)       │
│ Time to answer: 4 minutes                 │
╰───────────────────────────────────────────╯
```

## What Just Happened

### The System Provided

1. **Hypothesis enumeration** — didn't assume a single cause, considered multi-fault scenarios
2. **Evidence triage** — cheapest tests first, expensive tests only if needed
3. **Provenance tracking** — surfaced the contradictory generator records, asked you to verify
4. **Certainty vs. provisional** — told you when the diagnosis rested on unverified facts

### What You Avoided

- Guessing "probably fiber" and dispatching a crew to fix the wrong thing
- Running an OTDR trace ($800 test) on every fiber unnecessarily
- Waiting for "more data" while UPS depleted and SLA clock ran

### The Outcome

- **$0 diagnostic cost** (telemetry only)
- **4 minutes to confident answer** (vs 30-45min defensive testing)
- **Correct action taken** (controlled shutdown + generator rental, not fiber repair crew)

## The Realistic Twist

This scenario is based on a **real outage pattern**:

- Facility power events correlate with construction (someone hit a utility line)
- UPS battery warnings look like symptoms but are the critical timer
- Contradictory asset records (generator decommissioned but not updated everywhere)
- Multi-alarm cascade (23 routers) tempts you to overthink complexity when root cause is simple

The solver **doesn't know this is a power event** — it enumerates all possibilities, then eliminates them by cost-optimal testing. You'd reach the same answer manually, but slower and with less confidence.

## Challenge Mode: Make It Harder

Edit `tickets/den_outage_live.json` to add:

1. **Simultaneous fiber cut** — some routers show `LOS-A2` even after power confirmed OK
2. **Contradictory power telemetry** — PDU says AC present, UPS says running on battery
3. **Missing upstream node** — aggregation router not in inventory, can't check its status

The solver handles these — it keeps multiple hypotheses alive when evidence is ambiguous, and tells you **which question would settle it**.

## Try It

```bash
# The Saturday 3am scenario
uv run eiguide triage tickets/den_outage_live.json

# Interactive diagnostic walk
uv run eiguide work tickets/den_outage_live.json

# See what it's reasoning over
cat knowledge/datacenter_faults.lp
```

**Your turn.** You're on call, the alarms are real, the clock is running. What do you do?
