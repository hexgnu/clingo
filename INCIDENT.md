# The incident world

Companion to [DESIGN.md](DESIGN.md) and [VOCABULARY.md](VOCABULARY.md). Working document.

Those two ask *how the ontology is built* and *what evidence is*. This one asks: **what is the thing being reasoned about?** Every claim marked ▸ was produced by running the code, not inferred.

**Frame under examination:**
> An alarm creates an incident world. The initial alarm gives you a few facts, but the actual
> cause, impact, and remediation are unresolved. Every subsequent telemetry point, technician
> observation, or action collapses possibilities until the incident is solved.

This frame is already half-embedded in the code — `diagnose.lp:1` opens with *"Ticket resolution: unsolved world -> solved world."* The question here is which structural commitments this frame requires, and which gaps prevent it from being fully real.

---

## 1. Collapse — what the frame requires

When evidence arrives, possibilities collapse. But what collapses?

**Not the explanation inside a world.** That was a dead end in earlier designs — maintaining a
`candidate/1` list and narrowing it with `eliminated/1`. That approach has two fatal flaws:
(1) only elimination narrows the list, so positive evidence is inert; (2) patching it leads to
"confirm H1 → eliminate all others," which is how expert systems become confidently wrong about
multi-fault scenarios.

**The set of worlds collapses.** That is what `diagnose.lp` does. A world is a set of faults.
The answer sets ARE the possible worlds. Evidence enters as integrity constraints:

```prolog
:- fault(H), test_result(T, V), rules_out(T, V, H).     % rules out a world
:- symptom(_, S), not explained(S).                      % rules out a world
```

Nothing maintains a list. Positive and negative findings both bite, because both constrain which
worlds can exist. This dissolves the asymmetry without collapsing two simultaneous faults into one.

**Caveat:** Collapse is monotone only within a fixed evidence set. Across solves, the space re-opens
— a refuted field check retracts what rested on it, new evidence arrives, and the world set rebuilds.
Each solve is fresh, so this costs nothing here.

---

## 2. The world is an extent, not a candidate set

An incident world is not just a set of possible faults. It is those faults **plus the record facts that address the evidence**. Call this set the extent.

Currently, the extent would be:
```prolog
in_extent(I, subject(A))    :- incident(I), ticket_asset(I, A).
in_extent(I, hypothesis(H)) :- incident(I), candidate(H).
in_extent(I, fact(F))       :- incident(I), candidate(H), requires_fact(H, F).
```

But something is missing: which *readings* had to be true for their evidence to matter?
```prolog
in_extent(I, fact(F))       :- incident(I), pending(T), addressed_by(T, F).   % ← MISSING
```

**The gap:** `requires_fact/2` says which *hypotheses* assume a record. Nothing says which *tests* are aimed through one. A hypothesis knows what it depends on; a measurement does not. See [VOCABULARY.md](VOCABULARY.md) on `addressed_by`.

---

## 3. A contradicted addressing fact forks the world

**Example: SAMS-5120.** A real incident from a solar install (a router on a rooftop, with two
alarm codes and a fiber uplink). Two systems of record disagree about the same fact:

▸ SAMS-5120 carries two conflicting claims about the same row:

| source | fact | conf | as of | age at receipt |
|---|---|---:|---:|---:|
| `onevizion` | `uplink_span_known` | 90% | day 295 | 5d |
| `migration_app` | `neg(uplink_span_known)` | 88% | day 298 | 2d |

▸ With `min_confidence(80)` and `stale_after(90)`, neither claim is stale and neither is low
confidence. `contradicted/1` (`trust.lp:40`) is the only rule that can fire — two systems of
record assert opposite things about the same span.

▸ The system reports this as *"LOW CONFIDENCE"* (`cli.py:627`) and prompts *"The record is stale
or low confidence, and a live explanation depends on it"* (`cli.py:718`). Both statements are
false for this row. `trust.lp` derives the three reasons and then discards them — VOCABULARY.md
Open #1, with a measured instance.

But the mis-labelling is the smaller loss. The larger one is structural: this is not one world
containing a shaky row. It is **two worlds**, and they disagree about what the plant *is*:

```
world A: span 17 feeds rtr_phx_118      world B: span 17 does not
  read_optical_power reads span 17        read_optical_power reads something else
  no_light ⇒ confirms fiber_cut           no_light ⇒ confirms nothing about this router
```

Every optical reading on that span means a different thing in each. ▸ The current planner
schedules `read_optical_power` at cost 1 and will act on its result identically either way,
because no edge connects the reading to the row that aimed it.

```prolog
forked(F)          :- contradicted(F).
unaddressed(T)     :- pending(T), addressed_by(T, F), forked(F).
```

A test whose aim is forked is not a cheap test. It is a test that cannot mean anything yet, and
it should sort below the cost-1 tier it currently sits in. This is what VOCABULARY.md calls
"the most dangerous failure in the system, because the reading itself looks impeccable."

▸ For the record, the current answer on SAMS-5120: 6 explanations live, 2 provisional, four
tests and two verifications scheduled, open because *"an explanation rests on an unverified
record"* and *"the remaining explanations call for different actions."* The second reason is
new and better — it names what is actually undecided rather than counting survivors — but
neither says the thing that matters here, which is that two records disagree and every optical
reading is aimed through one of them.

---

## 4. Answer sets are worlds

Clingo's semantics are possible-world semantics: `brave` = true in *some* answer set, `cautious` = true in *all* of them. So enumerating models is not machinery bolted onto a reasoner — it is the native operation of the thing being reasoned about.

In the current code (`diagnose.lp` and `triage.py`):

**Pass 1** enumerates minimal answer sets with no `candidate/1` supplied. The answer sets ARE the possible worlds.

**Pass 2** takes:
- **union** across all answer sets → `candidate/1` (possible faults, brave)
- **intersection** across all answer sets → `certain/1` (established faults, cautious)

Both are re-injected as facts via `#defined`:
```prolog
#defined candidate/1.     % in at least one world
#defined certain/1.       % in every world
```

**Why two passes:** Agreement is a property of the *collection* of worlds, not any single world. "The survivors all agree on the cause" is not a fact you can derive inside one answer set — it is a fact about how the answer sets relate to each other.

That distinction matters when something is about to dispatch a truck.

---

## 5. An alarm opens a claim on an incident world; claims merge when extents overlap

One site power loss produces forty alarms. If each alarm *creates* a world independently, then merging becomes invisible — two separate answer sets that happen to be about the same event, with no rule to say so.

**Current state:** SAMS-5120 carries two alarm codes (`LOS-A2`, `NODE-UNREACH`) into one ticket only because they arrived in one JSON file. No rule correlates them.

**Better:** An alarm is a claim on an incident. Two claims belong to the same incident if their extents overlap — the subjects they touch, the records they depend on, the tests they require.

This makes correlation a derivable fact rather than a preprocessing step in Python. It also answers the question: whether two faults coexist is not a design decision, it is a consequence of whether one fault alone explains all the alarms.

---

## 6. Does the term "incident world" earn its place?

Test from [VOCABULARY.md](VOCABULARY.md): **some rule branches on it, or it is two names for one thing.**

Three rules would have to be written for "incident world" to be a real term:

| rule | current status |
|---|---|
| extent includes facts that *addressed* the evidence | unmodelled: `addressed_by` does not exist |
| contradicted addressing facts fork the world | §3 above: not yet structural |
| overlapping extents are one incident | unmodelled: no correlation rule |

**Verdict:** The term is aspirational, not real. It describes the system as it should be, not as it is. Until all three rules exist, `incident_world` is narration.

However, `blind_spot` (`diagnose.lp:61`) already fires on unmapped alarm codes, which is *something* in the extent has never been examined. Its general form is the fourth rule: uninterpreted alarm, unexamined subject, unaimed reading. Same predicate, wider trigger. That one is ready.

---

## 7. The tell

`diagnose.lp:143` already reads:

```prolog
solved :- open_candidates(1), candidate(H),
          not provisional(H), not blind_spot, not any_contested.
```

One explanation standing, extent established, nothing self-contradictory. That is the frame's
terminal condition, written before the frame had a name — which is the argument that this
describes the system truthfully rather than decorating it.

It is also the reason to be careful with *"until the incident is solved."* The property the
whole repo rests on is that `solved` never means "we stopped looking." A frame whose verb is
collapse quietly makes solved mean *exhausted*, and those are not the same thing.

---

## Open

1. **Is `incident` a first-class term or an implicit singleton?** Every rule sketched above
   carries an `I` that the current program does not have — it reasons about one ticket per
   solve. Correlation (§5) is what forces the parameter, and nothing else does. Adding it
   before §5 is speculative generality.
2. **Does forking need to be enumerated, or only flagged?** §3 flags. Actually solving both
   branches — two answer sets, one per record state — is the stronger version and may be free
   under §4's cautious enumeration. Untested.
3. **What is an extent's boundary?** "Facts a candidate requires" is closed and finite.
   "Subjects an incident touches" is not obviously either, once correlation lets extents grow
   by merging.
