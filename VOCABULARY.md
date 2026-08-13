# Vocabulary

Companion to [DESIGN-solver.md](DESIGN-solver.md). Working document.

Most of these terms already exist in the code under inconsistent names, or exist as
behavior with no name at all. This is mostly a **renaming and a reconciliation**, not an
invention — which is the argument for doing it: where two names mean one thing, they drift,
and §2.2 of the design doc is a measured instance of exactly that.

Two independent axes. Keeping them independent is the whole point; the current code
conflates them into a single `confidence: int`.

---

## Axis 1 — Modality: what did the evidence touch?

### `direct physical`
A person or instrument in contact with the plant, **addressed by being there**. A
photograph of a fuse panel, a tape measure on a cable span, a technician's eyeball.

Cannot be misaddressed. If you are standing at the rack, you are observing *that rack*,
whatever the record thinks it is called. This is the only evidence class immune to
topology error, which is why `trust.lp:51` is right to let `field_check` override any
`claim` unconditionally.

Expensive to refresh. That is its defining operational property, not its cost per se.

### `mediated physical`
An instrument in contact with the physical world, but **addressed through a record**. An
SNMP read of "the uplink port," an optical power poll, a telemetry query.

The reading is of something real. *Which* real thing it is of depends on a logical fact
being correct. **Mediated evidence is only as trustworthy as the fact that addressed it** —
and this is the failure mode that produces confident wrong answers, because the reading
itself looks impeccable.

> ▸ Not currently modeled. `requires_fact/2` exists in `samsung_router.lp:44` and applies
> only to *hypotheses*. No test declares what record row addressed it. This is the
> single largest gap the vocabulary exposes — see §4.1.

### `logical`
Reads a representation only. A config diff, a record query, a fuse book review, a
cross-reference against a standard.

Never touches the plant, so it can be wrong about the world in a way physical evidence
cannot. But **cheap to refresh** — which is what actually matters operationally, because
staleness only matters in proportion to refresh cost. A logical fact that is cheap to
re-check does not need a decay model; it needs re-checking.

### Why the split earns its place

The ticket knowledge base already encodes this — badly, as an integer:

| test | cost | actual modality |
|---|---:|---|
| `diff_running_config` | 2 | logical |
| `ping_node` | 1 | logical |
| `read_optical_power` | 1 | **mediated physical** |
| `otdr_trace` | 8 | mediated physical |
| `site_visit` | 40 | direct physical |

The cost scale is a **proxy for modality**, and a lossy one. Naming modality directly makes
the most defensible rule in the whole cost model expressible without inventing numbers:

> **Exhaust logical evidence before mediated, and mediated before direct.**

That is a preference ordering (§4 of the design doc), not a cost ratio. It needs no claim
that a truck roll is worth exactly 40 pings.

---

## Axis 2 — Provenance: who asserted it, and what has happened since?

Your phrase was *"AI captured, human reviewed, data stored."* Those are three different
things and they do not form a ladder. Pulling them apart:

### `artifact` — the thing that can be re-examined
The photograph. The OTDR trace file. The raw API response. The recording.

**Distinct from the assertion made about it.** This is the distinction that makes AI capture
tractable, and the repo currently has no place to put it (`evidence_uri` was removed as
decoration, per README — correctly at the time, since nothing consumed it).

### `assertion` — the claim
`cell_number_legible = true`. `read_optical_power = no_light`. What the reasoner consumes.

### `agent` — what produced the assertion

| | |
|---|---|
| `instrument` | a meter, an OTDR, an SNMP counter |
| `model` | a vision model reading an artifact, an LLM reading a clause |
| `human` | a technician, a reviewer |
| `record` | a system of record asserting on its own authority |

### `review` — what has happened to the assertion since

| | |
|---|---|
| `raw` | asserted, nothing checked it |
| `machine_checked` | passed an acceptance criterion (`Observable.accepts`) |
| `human_reviewed` | a person looked at the artifact and agreed |
| `adjudicated` | a conflict was raised and someone with authority settled it |

### `custody` — can it be re-examined?

| | |
|---|---|
| `ephemeral` | exists only during the session; nothing was written |
| `stored` | the artifact is retrievable |
| `attested` | stored with an integrity guarantee |

> ▸ The inspection walk is deliberately `ephemeral` — README argues for this well, and the
> argument is sound *for a half-finished walk*. But `ephemeral` and AI capture are
> incompatible, for the reason in §3 below. This tension needs resolving before stage 4.

### The key move: **AI capture is a derivation, not a tier**

A vision model reading a fuse panel photograph is **two links**, not one:

```
camera  ──physical capture──▶  artifact  ──model inference──▶  assertion
        agent: instrument                  agent: model
        modality: direct physical          modality: logical (over an artifact)
```

Treating "AI captured" as a single provenance level loses this, and the loss is expensive:
it makes the two failure modes indistinguishable. A blurry photo and a hallucinating model
are different problems with different remedies, and only one of them requires going back
to the site.

**The payoff:** if the artifact is stored, a human can re-review the *same* photograph and
overturn the model's reading without a truck. That is the operational case for `custody:
stored`, and it is strong enough to reopen the `evidence_uri` decision — this time earning
its place rather than decorating.

---

## Axis 3 — Effect: what does the evidence do to a hypothesis?

Named here because §0 of the design doc is a measured case of one of these being missing.

| | |
|---|---|
| `excluding` | rules the hypothesis out — `rules_out/3` |
| `confirming` | positively supports it — `confirms/3` ▸ **currently inert** |
| `inert` | responds to the hypothesis but no outcome moves it |

▸ `inert` is not a design category, it is a bug detector. `observes(ping_node, config_drift)`
is inert and nothing catches it. See design doc §2.2.

---

## Reconciliation with existing code

| current name | where | means | rename / status |
|---|---|---|---|
| `claim/4` | `trust.lp:23` | a record asserts | logical assertion, agent `record` |
| `field_check/2` | `trust.lp:24` | someone confirmed on site | direct physical assertion, agent `human` |
| `obs/3` | `core.lp:15` | compliance observation | physical assertion; modality unstated |
| `test_result/2` | `diagnose.lp:28` | ticket evidence | assertion; **modality unstated — defect** |
| `confidence: int` | `ticket.py:62` | 0–100, any source | ▸ **collapses both axes — see §4.2** |
| `Verifiability` | `models.py:24` | observable/measurable/documentary/process_only | ✅ already the modality axis |
| `ObsKind.document` | `models.py:33` | a capture kind | ▸ **unreachable — see §4.3** |
| `process_only` | `models.py:30` | obligation on workflow | not evidence at all; correctly excluded |
| `Rule.reviewed` | `models.py:134` | human signed off | `review: human_reviewed`, rules only |
| `Observable.accepts` | `models.py:104` | acceptance criterion | the `machine_checked` predicate |

---

## Defects the vocabulary exposes

### 4.1 Mediated evidence does not declare what addressed it
`requires_fact/2` guards hypotheses but not tests. So `read_optical_power` returning
`no_light` is trusted identically whether `uplink_span_known` is fresh or 130 days stale —
even though a stale span record means the poll may have read **the wrong port**.

The rule the vocabulary implies:

```prolog
% A mediated reading inherits the trust state of the fact that addressed it.
addressed_by(read_optical_power, uplink_span_known).
provisional_evidence(E) :- evidence(E,T,_,_,_,_), addressed_by(T,F), unverified(F).
```

This connects `trust.lp` to the evidence layer for the first time, and it is very likely the
real explanation for the SAMS-5120 conflict case: two sources disagree about
`uplink_span_known`, which should make every mediated reading on that span provisional —
and currently makes none of them so.

### 4.2 `confidence: int` collapses both axes
`min_confidence(80)` at `trust.lp:34` compares OneVizion's 85, a vision model's 0.85, and a
technician's "pretty sure" on one scale. They are not commensurable. Replace the scalar with
`(agent, review, modality)` and let `trust.lp` decide — which is what it was written to do.

### 4.3 The logical capture channel is welded shut
▸ `ObsKind` includes `document` and `reason.py:135` has a working instruction for it
(*"Obtain the record covering …"*), but `field_verifiable` at `models.py:141` excludes
`documentary`, so `compile.py:77` emits no observables for those rules. Zero rules in
`data/golden/` use it.

Consequence: the fuse record book (D.6.4, D.6.5) is reported as *"cannot be settled by
capture"* when it plainly can — by a logical capture that the pipeline already knows how to
instruct. README frames this as a principled limit ("non-field-verifiable obligations"), but
it is an artifact of conflating *not physically observable* with *not capturable*.

The fix is one term: `field_verifiable` → `capturable`, admitting `documentary`.
`process_only` stays excluded, because it genuinely is.

---

## Open

1. **Is `mediated physical` one class or a spectrum?** An SNMP counter and an OTDR fired
   down a span addressed by a record differ in how much the addressing can hurt you.
2. **Does `adjudicated` need an authority model** — who is allowed to settle a conflict —
   or is "a human looked and decided" enough to start?
3. **Ephemeral vs. stored.** The inspection walk's read-only guarantee is a real property,
   argued for well in the README. AI capture needs stored artifacts. Are these two modes of
   one system, or is the compliance walk simply not the thing that gets AI capture first?
