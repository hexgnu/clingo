# Production Outage Demo — Actually Run It

## The Scenario

It's 3:47 AM Saturday. You're on call. Denver colocation just lit up with 23 alarms. You need to figure out what's wrong — fast.

## Run the Interactive Diagnosis

```bash
# From the repo root
uv run compli work tickets/den_outage_live.json \
  --knowledge knowledge/vendor_codes.lp \
  --knowledge knowledge/datacenter_faults.lp
```

This drops you into an **interactive diagnostic session**. The system will:

1. Show you what records exist and how trustworthy they are
2. Enumerate the possible causes (minimal answer sets)
3. Ask you to run the cheapest test that discriminates
4. Re-solve after each result, narrowing the field
5. Converge on the root cause

## What You'll See

```
╭──────────── ticket ────────────────╮
│ DEN-OUTAGE-001 · samsung_nms       │
│ asset den_dc2                      │
│                                    │
│ alarm NODE-UNREACH (critical)      │
│ alarm AC-INPUT-FAIL (major)        │
│ alarm BATTERY-MODE (warning)       │
╰────────────────────────────────────╯

┌─────────── what we know ───────────┐
│ record               │ source │ conf│
│ site_has_generator   │ one... │  60%│ CONTRADICTED
│ site_has_generator   │ hyp... │  85%│
│ utility_power_stable │ one... │  95%│ established
│ ...
└─────────────────────────────────────┘

3 explanation(s) live · 1 provisional
┌──────────────────────────────────────┐
│ explanation              │ status    │
│ utility_power_outage     │ live      │
│ ups_battery_depleted     │ provision…│
│ upstream_aggregation_down│ live      │
└──────────────────────────────────────┘

Recommended tests:
  1. query_power_telemetry (cost $1)
  2. check_upstream_alarms (cost $1)

Run test [or 'q' to quit]: query_power_telemetry
Result [ac_present / ac_absent]: ac_absent

... (system re-solves) ...

1 explanation(s) live
┌──────────────────────────────────────┐
│ explanation          │ status        │
│ utility_power_outage │ live          │
└──────────────────────────────────────┘

SOLVED → dispatch generator rental
requires dispatch
```

## The Key Moments

### 1. Contradicted Records Surface Immediately

```
site_has_generator:
  • OneVizion says NO (60% conf, 5 days old)
  • HyperLink says YES (85% conf, 60 days old)
  → Status: needs verification
```

The system tells you **this matters** — if the site has no generator, you have 90 minutes before total outage.

### 2. Cheap Tests First

The solver never suggests a $1200 truck roll when $2 of telemetry would settle it:

```
Recommended: query_power_telemetry ($1)
NOT recommended (yet): site_visit ($40)
```

Only if telemetry is ambiguous does it escalate to physical dispatch.

### 3. Provisional vs. Certain

```
ups_battery_depleted — PROVISIONAL
  (depends on site_has_generator, which is contradicted)

utility_power_outage — LIVE  
  (no record dependencies)
```

The system distinguishes "we know this" from "we think this IF the record is right".

## Try Different Scenarios

### Modify the ticket to add complications:

**1. Simultaneous failures** — add `"TEMP-HIGH"` alarm:

```json
"alarms": [
  {"code": "NODE-UNREACH", "severity": "critical"},
  {"code": "AC-INPUT-FAIL", "severity": "major"},
  {"code": "TEMP-HIGH", "severity": "warning"}
]
```

Now both `utility_power_outage` and `hvac_failure_thermal` are live. The system keeps both hypotheses until tests discriminate.

**2. Ambiguous telemetry** — say `query_power_telemetry` returns `ac_present` but UPS says `battery_mode`:

The solver reports **contradictory evidence** and asks for physical verification.

**3. Missing knowledge** — remove a symptom from `datacenter_faults.lp`:

The ticket becomes `unsolved_reason: no world accounts for symptoms` — exactly correct when the knowledge base is incomplete.

## What This Demonstrates

### vs. Traditional Monitoring

| Traditional | This System |
|---|---|
| Alarm storm → panic | Minimal answer sets → structured hypotheses |
| Guess based on experience | Cost-optimal test sequence |
| "Probably power" | "Certain: power. Provisional: generator status" |
| Dispatch blind or wait | $2 confirms, then dispatch with confidence |

### The Architecture Win

This uses **Answer Set Programming** (clingo) because:

1. **Multiple answer sets = uncertainty** — Each model is one consistent explanation
2. **Agreement across models = certainty** — If all survivors agree, you know
3. **Optimization** — `#minimize` finds cheapest discriminating tests
4. **Three-valued logic** — `established / unverified / refuted` not `true / false`

Datalog can't enumerate models. Rule engines can't do set-cover optimization. This is why the tool exists.

## Next: Create Your Own

See `tickets/samsung_5120.json` for another example (router diagnosis).

Knowledge bases follow the pattern in `knowledge/datacenter_faults.lp`:
- `hypothesis(X)` — what could be wrong
- `explains(H, S)` — which symptoms each hypothesis produces
- `test(T)` + `test_cost(T, C)` — diagnostics and their cost
- `rules_out(T, V, H)` / `confirms(T, V, H)` — how results move the diagnosis

The solver does the rest.
