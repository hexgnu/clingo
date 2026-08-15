# Vocabulary

Companion to [DESIGN.md](DESIGN.md) (how the ontology is built) and
[INCIDENT.md](INCIDENT.md) (what an incident is). Working document.

## The admission test

**A vocabulary term earns its place if some rule branches on it.** If no rule distinguishes two values, they are one value with two names — which is how `observes/2` drifted into chaos.

---

## Why a vocabulary matters

Evidence is stored as one thing: a value, plus an integer called `confidence`. So a vision model at 0.85, a records database at 85, and a technician who is "pretty sure" all arrive as the same number, and `min_confidence(80)` compares them as if they were commensurable. They are not.

They fail in **different ways**, and a reasoner that cannot tell the failures apart cannot respond to them.

A vocabulary means a small set of **independent questions** about evidence. Independent is key: knowing the answer to one should tell you nothing about the others.

---

## Four dimensions and two relations

Four dimensions. Most already exist in the code, unnamed or named inconsistently. Two relations are edges, not categories.

## 1. Modality — what did it touch?

| | |
|---|---|
| `logical` | read a representation: a config diff, a record query, a document |
| `physical` | touched the plant: a photograph, a meter, a site visit |

They fail differently. Logical evidence can be confidently wrong about the world, because
the representation and the world drift apart. Physical evidence cannot be wrong about
*what it touched* — if you are standing at the rack, you are looking at that rack whatever
the record calls it. This is why `trust.lp:51` is right to let `field_check` override any
`claim` unconditionally.

The operational difference is **refresh cost**. Logical evidence is cheap to re-run;
physical evidence is not. That matters more than it sounds: staleness only matters in
proportion to refresh cost. A logical fact that is cheap to re-check does not need a decay
model, it needs re-checking.

The ticket knowledge base already encodes modality — badly, as cost:

| test | cost | modality |
|---|---:|---|
| `ping_node`, `diff_running_config` | 1–2 | logical |
| `read_optical_power`, `otdr_trace` | 1–8 | physical |
| `site_visit` | 40 | physical |

Naming it directly makes the most defensible rule in the whole cost model expressible
without inventing numbers: **exhaust logical evidence before physical.** That is an
ordering, not a ratio — it needs no claim that a truck roll is worth 40 pings.

---

## 2. Provenance — who asserted it?

| | fails by |
|---|---|
| `instrument` | miscalibration, wrong port, dead sensor |
| `model` | hallucination, out-of-distribution input |
| `human` | fatigue, haste, inexperience |
| `record` | lag — the world moved and nobody updated the row |

Four distinct failure modes with four distinct remedies. That is the whole justification for
the dimension: recalibrate, re-review, re-ask, or re-survey.

Note what is **not** here: a review level. "Human reviewed" is not a rank an assertion
climbs — it is a second assertion, by a `human`, *about* the first one. That falls out of
the `about` relation below and needs no vocabulary of its own.

---

## 3. Standing — is it still good?

| | |
|---|---|
| `established` | good enough to reason from |
| `unverified` | asserted, but something is wrong with it — stale, contested, low confidence |
| `refuted` | someone checked and it is not so |

Already implemented in `trust.lp` for record facts, and it is the best-designed thing in the
ticket half. It applies unchanged to evidence, which is the point: **one trust mechanism,
not two.** Only `established` evidence should fire `confirms`/`rules_out`.

This is also where retraction lives. An assertion whose standing becomes `refuted` stops
supporting whatever rested on it — non-monotonically, which is what ASP is for.

---

## 4. Effect — what does it do to a hypothesis?

A hypothesis here means a **possible fault** (a member of the answer set).

| | |
|---|---|
| `confirms` | positively supports the hypothesis |
| `excludes` | rules out the hypothesis |

Both already exist as `confirms/3` and `rules_out/3`. Named here because the system
currently acts on only one of them. A reasoner that can only eliminate throws
away most of what instruments produce — they overwhelmingly return positive findings
(`no_light`, `crc_errors`, `ac_absent`). Positive evidence is inert until you model it.

---

## Two relations that are not dimensions

### `about` — what is this assertion about?

An assertion can be about **a thing in the world**, or about **an artifact**, or about
**another assertion**.

That third case is what makes AI capture tractable, because AI capture is a chain, not a
tier:

```
camera ──▶ artifact ──▶ assertion ──▶ assertion
           (photo)      by a model     by a human, about the model's
```

A blurry photo and a hallucinating model are different problems, and only one of them
requires going back to the site. Collapsing them into a single "AI captured" label makes
them indistinguishable — and loses the payoff, which is that **if the artifact is kept, a
human can overturn the model's reading without a truck.**

That is the operational case for storing artifacts, and it is what makes task #9
(ephemeral vs. stored) a real decision rather than a preference.

### `addressed_by` — how did the evidence find its subject?

Physical evidence reached *through a record* inherits that record's standing. An optical
power poll of "the uplink port" is a real reading of something real — but which thing
depends on `uplink_span_known` being right.

```prolog
addressed_by(read_optical_power, uplink_span_known).
```

This is not a third modality. It is an edge, and it produces the most dangerous failure in
the system, because the reading itself looks impeccable.

▸ Not currently modeled anywhere. `requires_fact/2` (`samsung_router.lp:44`) guards
*hypotheses* only; no test declares what addressed it. A hypothesis knows what it assumes;
a measurement does not.

▸ This is the real story of the SAMS-5120 conflict case, now measured: `onevizion` and
`migration_app` disagree about `uplink_span_known`, neither claim is stale or low
confidence, so `contradicted/1` is the only rule that fires — and the system reports it as
`"LOW CONFIDENCE"` (`cli.py:627`), which is false. Every reading on that span should be
provisional; none of them are. See [INCIDENT.md §3](INCIDENT.md), which argues the stronger
form: a contradicted addressing fact does not weaken one row, it **forks the world**.

---

## Reconciliation — what needs to change

| predicate | location | carries | missing | action |
|---|---|---|---|---|
| `claim/4` | `trust.lp:23` | modality, provenance | standing | already works, reuse as template |
| `field_check/2` | `trust.lp:24` | modality, provenance | standing | same as claim/4 |
| `obs/3` | `core.lp:15` | modality | provenance, standing | add provenance (physical from where?), add standing flag |
| `test_result/2` | `diagnose.lp:28` | nothing | all four + `addressed_by` link | add all four dimensions, link to the facts it aimed at |
| `confidence: int` | `ticket.py:62` | — | split into provenance + standing | replace with two separate fields |

**The critical missing edge:** `addressed_by/2` — which facts does each test assume? See [§2](INCIDENT.md#2-the-world-is-an-extent-not-a-candidate-set) and [INCIDENT.md §3](INCIDENT.md#3-a-contradicted-addressing-fact-forks-the-world).

---

## Note on modality in the codebase

`Verifiability` in `models.py:24` is actually modality — raw / photo / video / document. But the code treats `documentary` as "cannot be stored and re-examined," which is wrong. A document can be stored as an artifact just like a photo. The modality-to-storage link got tangled. They should separate: modality says *how* you found it (logical or physical); storage policy says whether you keep it (ephemeral or persistent). Those are independent.

---

## What this cuts

Earlier draft had three axes and about fifteen terms. Removed for failing the branching
test:

- **`custody`** (ephemeral / stored / attested) — storage policy, not reasoning. No rule
  branches on it; it decides whether `about` can point at an artifact, and that is all.
- **the `review` ladder** (raw / machine_checked / human_reviewed / adjudicated) — collapses
  into `about` plus provenance.
- **`direct` vs `mediated` physical** — that is `addressed_by`, a relation, not a category.
- **`inert`** as an effect — a bug detector, not a state. It belongs in a test.

---

## Open

1. **Opportunity:** Preserve the three reasons (stale / contested / low-confidence) instead of collapsing them into `unverified`. `trust.lp:40-44` derives all three; `trust.lp:48` discards the distinction. The result: SAMS-5120 reports a *contradicted* record as "LOW CONFIDENCE" (false). Keeping the reasons would fix [INCIDENT.md §3](INCIDENT.md#3-a-contradicted-addressing-fact-forks-the-world).

2. Is `model` one provenance or two — a model reading an artifact vs. a model reading text?
   They fail differently enough that it may matter for rule extraction.
