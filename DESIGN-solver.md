# Scope: the ticket solver as an expert system

Working document, written to be argued with. Revised after two decisions:

- evidence arrives **interactively, step by step** — a person or instrument answers one
  question at a time and the solver re-reasons
- time granularity is **not yet known**, so evidence carries a timestamp and decay
  semantics are deferred

Every claim below marked ▸ was produced by running the current code, not inferred.

---

## 0. The root defect: the reasoner cannot be persuaded, only cornered

`ontology/diagnose.lp` is a **purely eliminative** reasoner. It narrows exclusively via
`rules_out/3`. The knowledge base is full of `confirms/3` facts, `confirmed/1` is derived
from them — and then nothing consumes it except the final `recommended/1`:

```prolog
open_candidates(N) :- N = #count { H : candidate(H) }.
solved :- open_candidates(1), candidate(H), not provisional(H), not blind_spot.
```

`confirmed(H)` appears nowhere in that. **Positive evidence cannot narrow the candidate
set.** The only path to an answer is eliminating every rival one at a time.

▸ Measured on SAMS-4471, with the stale `uplink_span_known` record verified up front:

| approach | questions | cost | result |
|---|---:|---:|---|
| the `#minimize` "minimum discriminating set" | 4 | 5 | ❌ **4 candidates still open** |
| interactive, one at a time, current logic | 6 | 7 | ✅ fiber_cut |
| one reading, if confirmation counted | **1** | **1** | ✅ fiber_cut |

That third row is one call to `read_optical_power`. It comes back `no_light`, which
`confirms(read_optical_power, no_light, fiber_cut)` and `rules_out(...optic_degraded)`. The
system derives `confirmed(fiber_cut)`, reports **`"several explanations remain"`**, and
schedules five more tests.

This matters far more for interactive step-by-step than for batch planning, because
instruments overwhelmingly return **positive findings** — `no_light`, `crc_errors`,
`ac_absent`. An expert system that can only act on negative findings throws away most of
what its evidence layer will hand it.

### What the fix is *not*

`eliminated(H2) :- confirmed(H1), H1 != H2` is wrong. Two things can be true at once — a
fiber cut *and* a drifted config — and collapsing on first confirmation is how expert
systems get a reputation for confident wrong answers.

### What it should be

Keep the three-valued honesty and add a rank on top of it. A hypothesis is:

| | |
|---|---|
| `excluded` | evidence rules it out |
| `confirmed` | evidence positively supports it |
| `open` | neither — still possible, nobody has looked |

and the ticket has a **best explanation** when exactly one candidate is confirmed and
uncontested. Rivals stay visible as *open, not excluded*, exactly as `undetermined` stays
visible on the compliance side. That preserves the property the whole repo rests on:
`solved` never means "we stopped looking."

This is abduction — inference to the best explanation — and it is the thing that makes
something an expert system rather than a constraint checker.

---

## 1. The objective is wrong for interactive use — and the fix is an inversion

`diagnose.lp:109` demands a **minimum discriminating set**: every separable pair must be
separated by some chosen test.

▸ Two problems, both measured:

**It does not resolve the ticket.** Separation means a test *responds differently* to H1 and
H2 — not that its actual outcome eliminates either. The 4-test plan ran to completion with
4 candidates still open. The plan's implicit promise ("run these and you'll know") is false.

**It is the wrong question for step-by-step.** A committed set assumes nobody answers until
the whole batch is done. When you re-solve after each answer, most of the set evaporates.
▸ `ping_node` was in the optimal set, was asked, and moved the candidate count 5 → 5.

### The inversion

The compliance side's whole thesis is turning *"here are the rules"* into *"here is the
smallest thing to go capture."* The ticket side should invert the same way — and the
counterfactual belongs **in the logic**, not in a Python loop that calls clingo once per
hypothetical outcome:

```prolog
% What would still stand if test T came back V? Reasoning about an outcome that has
% not happened yet, inside the model.
survives(H,T,V)  :- candidate(H), pending(T), outcome(T,V), not rules_out(T,V,H).
remaining(T,V,N) :- pending(T), outcome(T,V), N = #count { H : survives(H,T,V) }.
worst(T,M)       :- pending(T), M = #max { N : remaining(T,V,N) }.

1 { ask(T) : pending(T), not useless(T) } 1.       % exactly one question
#minimize { M@2, T : ask(T), worst(T,M) }.         % resolve the most...
#minimize { C@1, T : ask(T), test_cost(T,C) }.     % ...then break ties on cost
```

One solve, one question, no external simulation. ▸ Prototyped and working — it correctly
picks `read_optical_power` first.

▸ **But pure worst-case minimax stalls after one question**: with confirmation inert, no
remaining test guarantees elimination under its unluckiest outcome, so every test scores
`useless` and the choice goes unsatisfiable. This is §0 biting again from a second
direction, and it is good evidence that §0 is the real root: fix confirmation and the
objective has something to optimize.

The objective should therefore minimize **worst-case unresolved candidates**, where
resolution counts confirmation as well as elimination.

---

## 2. Three further defects

### 2.1 Non-deterministic triage
▸ SAMS-4471 has **4 distinct optimal plans at cost 6**. `triage.solve()`'s `on_model` just
overwrites `best`, so it returns whichever clingo reported last. `reason.solve()` solved
this properly and documented why; the ticket path did not inherit it.

**Fix it the better way:** `--enum-mode=cautious` over the optima gives what holds in
*every* optimal model — a conclusion the system can defend — and brave gives the live
possibility space. That distinction (defensible conclusion vs. mere preference) exists
nowhere in the codebase and matters more the moment something dispatches a truck. A stable
tie-break is still needed to pick one plan to show a human; the *verdict* must never depend
on it.

### 2.2 `observes/2` is an authored duplicate that has already drifted
▸ Two pairs claim discriminating power no outcome delivers:
`observes(ping_node, config_drift)` and `observes(read_error_counters, optic_degraded)` have
no `rules_out`/`confirms` backing them.

**Fix:** derive it — `observes(T,H) :- rules_out(T,_,H).` / `:- confirms(T,_,H).` — and add a
test asserting no knowledge file contains an `observes/2` fact. One authored relation, not
two that can disagree.

### 2.3 Contradictory evidence is swallowed
▸ `read_optical_power = no_light` plus `otdr_trace = continuous` yields
`confirmed(fiber_cut)` **and** `eliminated(fiber_cut)`, `fiber_cut` silently vanishes from
the candidate set, and the reported reason is `"several explanations remain"` — which is
false. The true reason is that the evidence disagrees with itself. Same for two results on
the same test: there is no key on `test_result/2` and no notion of which reading is newer.

Once evidence comes from instruments this is the **normal** case: a mis-scoped port, an OTDR
down the wrong fiber, a reading against stale topology. Apply the pattern already invented
for `blind_spot`:

```prolog
contested(H) :- confirmed(H), eliminated(H).
unsolved_reason("evidence for and against the same explanation") :- contested(_).
```

and `contested/1` must **block** `solved`, exactly as `blind_spot` does. The right next
action then isn't another test — it's *re-run the suspect one*, which requires knowing which,
which requires §3.

---

## 3. The evidence boundary

Evidence enters as `test_result(Test, Value)` — timeless, sourceless, unkeyed. Fine for a
fixture, wrong for anything real. `ticket.py` already argues, correctly, that provenance
must survive the door for *record* facts. Evidence deserves identical treatment.

```prolog
% evidence(Id, Test, Value, Source, Captured, Confidence)
evidence(e17, read_optical_power, no_light, nms_poll, 1738000000, 95).
```

| field | why it earns its place |
|---|---|
| `Id` | a result can be superseded, retracted, cited in an explanation |
| `Source` | an automated poll and a technician's eyeball are not equally reliable |
| `Captured` | timestamp now, decay semantics deferred (see §5) |
| `Confidence` | a vision model at 0.6 is not a meter reading |

**Run it through `trust.lp`, don't build a second mechanism.** Evidence becomes
`established` / `refuted` / `unverified` like any other fact, and only established evidence
fires `rules_out`/`confirms`. That makes §2.3 tractable: contradiction becomes a trust
question about a specific evidence item, not an unexplained hole.

Two things fall out:

- `Observable.accepts` finally has something to attach to — README calls it "the seam where
  vision-based verification attaches." This is that seam.
- `obs(Subject, Obs, Value)` and `test_result(Test, Value)` are the same relation wearing
  different names. **One evidence layer, two knowledge bases over it.**

---

## 4. Costs are invented; preferences are defensible

README is honest that 5/6/10 is made up. The ticket side added 1/2/8/40 with no more basis,
and interactive use makes the arithmetic worse — you are no longer summing a plan, you are
comparing single questions, where a fabricated ratio directly decides what gets asked.

What is defensible is *ordering*: remote before on-site, reversible before destructive,
never dispatch while a free remote test would change the answer.
[asprin](https://potassco.org/asprin/) expresses these as preference relations instead of
forcing them through one integer scale. Keep the compliance-side costs — capture effort
genuinely is commensurable, and `prove.py` measures the result.

---

## 5. TEL and MEL — demoted, honestly

Given "granularity not yet known," I am arguing **against** my own earlier enthusiasm.

**MEL: defer.** `trust.lp:36` already implements a metric temporal operator by hand — day
granularity, one global threshold, integer subtraction. It is the right idea at possibly the
wrong resolution, but until there is real capture data showing evidence *validity windows*
matter, `valid_for(Test, Seconds)` arithmetic does everything MEL would and costs two lines.
Adopting [MEL](https://arxiv.org/pdf/2304.14778) to formalize something we cannot yet
measure is engineering ahead of evidence — which is precisely what this repo's `prove.py`
discipline exists to prevent. **Test first:** same ticket, same evidence, 5 minutes vs 5
hours old. If the verdict does not change, MEL is not worth building.

**TEL: partially survives, and for a reason independent of granularity.** Ordering is not a
resolution question. `symptom(T, S)` has no time in it at all, so the model cannot express:

> power telemetry went `ac_absent` **before** the node went unreachable → `site_power_loss`
> `ac_absent` **after** → the power alarm is a *consequence*, not a cause

or distinguish "down once, hard" from "flapped 40× in ten minutes." That ordering is the
single most useful discriminator a NOC engineer has, it needs only sequence rather than
seconds, and it is currently inexpressible. It also feeds §1 for free: a temporal signature
is just another thing `confirms/3` can key on, so the planner consumes it unchanged.

Still **after** §0–§3, because a temporal discriminator is worthless while confirmation is
inert.

**Meta-programming: one use, not the general case.** Reification exists to build new logics
on clingo — it is how asprin, telingo, clingcon and
[metasp](https://arxiv.org/html/2605.29965) are built. We should not build a logic. The one
application that pays is **derivation trees**: a meta-encoding over the reified program can
answer *why* an atom is in the answer set. `closes/4` is already that instinct applied to
one predicate — deriving provenance inside the logic rather than reconstructing it after.
A system that authorizes a truck roll has to justify it. Last, and only if §0–§3 prove the
reasoning is worth explaining.

---

## 6. Sequence

| # | stage | closes | size |
|---|---|---|---|
| 1 | **Abduction**: confirmation narrows; best-explanation rank; `contested/1` blocks `solved` | §0, §2.3 | small |
| 2 | **Next-question inversion**: counterfactual in ASP, one question per solve | §1 | small |
| 3 | Cautious/brave verdicts; derive `observes/2` | §2.1, §2.2 | small |
| 4 | `evidence/6` through `trust.lp`; superseding | §3 | medium |
| 5 | Preference program replacing ticket `#minimize` | §4 | small |
| 6 | Temporal signatures (telingo) | §5 | large |
| 7 | Metric validity windows / derivation trees | §5 | large |

1–3 are small, close measured defects, and are prerequisites for everything else. Stage 1
alone takes SAMS-4471 from 6 questions to 1.

New `prove.py` experiments, in its existing style — a claim, a control, numbers either way:

- **abduction**: questions-to-resolution with confirmation inert (control: 6) vs. active.
- **contradiction**: control is current behavior — silently reports "several explanations
  remain." Expected: names the conflict, refuses to solve.
- **robustness**: how many conclusions survive cautious enumeration vs. appear in only one
  optimal model. If the answer is "all of them," §2.1 was cosmetic and we should say so.
- **decay**: the §5 test above, gating whether MEL is ever built.

---

## 7. Still open

1. **Can two hypotheses be true at once?** A fiber cut *and* a drifted config. §0's
   best-explanation rank assumes usually-one; multi-fault diagnosis is a different and
   harder objective. What does the real ticket population look like?
2. **Who authors knowledge bases?** `samsung_router.lp` needs someone fluent in both routers
   and ASP, and that intersection is small. If the answer is "an LLM drafts, an engineer
   reviews" — as README proposes for rules — then §2.2 is not a cleanup, it is a *guardrail*,
   and there should be more like it.
3. **Is compliance still a product, or is it now the proving ground for the ticket solver?**
   They share the evidence layer and diverge above it.
