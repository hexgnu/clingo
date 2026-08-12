# eiguide

Turns a paginated engineering standard into a declarative ruleset, then **inverts it** to
drive an evidence-capture walkthrough.

The question this answers is not "here are the rules, go read them." It is:

> Given this site, and given what I have already observed, **what is the smallest set of
> things I can go and capture that would settle whether it is compliant?**

Source document: *Level 3 Communications — Engineering & Installation Guidelines 6.0,
DC Power & Infrastructure* (121 pages, 556 clauses, 385 of them binding).

---

## The idea

A requirement under partial observation has **three** states, not two:

| | meaning |
|---|---|
| `satisfied` | evidence shows it is met |
| `violated` | evidence shows it is not |
| `undetermined` | **nobody has looked yet** |

Collapsing `undetermined` into "not violated" is what makes an ordinary rules engine
useless for inspection: it reports a site clean because nothing has been checked. Answer
Set Programming keeps the third state, and that set of undetermined requirements *is* the
work list.

From there the capture plan is an optimization: one pass down a battery string settles the
same observable for all 24 cells, so choosing the cheapest set of physical actions that
closes every gap is a weighted set-cover problem. `clingo`'s `#minimize` solves it.
Datalog and OPA/Rego can evaluate rules; neither does this part.

**Result on the example site: 8 capture actions close 71 evidence gaps across 9 requirements.**

## Pipeline

```
EIGuide-61[1].pdf
  │  extract    pymupdf + inferred layout      →  data/clauses.jsonl   (verbatim + provenance)
  │  (author)   structured interpretation      →  data/rules.jsonl     (reviewed by a human)
  │  compile    mechanical, no judgement       →  rules/chapter_d.lp
  ↓  reason     clingo  ← ontology/ + sites/   →  manifest / verdicts
```

Three layers on purpose. Re-extracting from a new revision of the PDF regenerates
`clauses.jsonl` and `chapter_*.lp` but never touches the hand-written `ontology/`, and
every ASP atom traces back to a page and a clause number.

## Quickstart

```bash
uv sync
uv run eiguide extract                 # PDF  -> 556 clauses, 59 figures, 40 tables
uv run eiguide compile --chapter D     # rules -> rules/chapter_d.lp
uv run eiguide plan                    # what to capture, cheapest first (read-only)
uv run eiguide inspect                 # walk it and get the verdict (single session)
uv run eiguide prove                   # test whether the solver earns its place
```

`plan` and `inspect` are both **read-only**. An inspection is one session start to finish:
answers live in memory, the verdict prints at the end, nothing is written. A half-finished
walk left on disk is worse than none, because the next run silently inherits it and reports
a site as inspected when it was not. Use `plan --out manifest.json` if you want the plan as
a file for something else to consume.

### `plan` — the inversion

```
╭──────────────────── Evidence plan — den01 ─────────────────────╮
│ 8 capture actions close 71 evidence gaps across 9 requirements │
╰────────────────────────────────────────────────────────────────╯
1. [video] Record a continuous pass over bs1. Must clearly establish:
   numbering starts at positive end.
   settles D.6.6b · cost 5 · capture(bs1,numbering_starts_at_positive_end)
3. [photo] Photograph bs1. Must clearly establish: cell number legible,
   cell polarity symbol visible.
   settles D.6.6a · cost 10 · sweep(bs1,photo)          ← replaces 48 individual shots
5. [photo] Photograph fp2. Must clearly establish: fuse assignment card present,
   fuse capacity identified, row designation present, voltage designation present.
   settles D.6.1, D.6.2, D.6.3 · cost 6 · survey(fp2,photo)
```

### `inspect` — the walkthrough

Re-solves after every action, so the plan adapts as you answer. A failure surfaces its
violation immediately; a sweep that passes closes two dozen requirements at once. Each
clause is quoted once and referenced by page label thereafter.

```
0 satisfied ·  0 violated · 37 open · 8 actions left
1 satisfied ·  0 violated · 36 open · 6 actions left
23 satisfied · 2 violated · 12 open · 5 actions left   ← the 24-cell sweep landed
...
33 satisfied · 2 violated ·  2 open · 0 actions left
```

Answer `f` on a group and it asks *which* members failed, so two bad cells out of 24
produce two violations, not 24. It ends with the verdict, rolled up per requirement and
worst first:

```
Rule     Requirement                     n   Outcome
D.6.6a   Designate all batteries w…     24   2/24 violated cell(bs1,7), cell(bs1,9)
D.6.4    Stamp or type added circu…      1   1/1 unchecked frb1
D.6.1    Designate fuse panels wit…      2   2/2 ok

2 violated · 2 undetermined · 33 satisfied
Undetermined is not compliant -- it means nobody looked.
```

## Does the solver actually earn its place?

`uv run eiguide prove` tests that claim against controls instead of asserting it. Each
experiment reports numbers either way, and the results are pinned in `tests/test_prove.py`
so the argument cannot silently invert.

| experiment | control | result |
|---|---|---|
| **Open vs closed world** | what Datalog/Rego report on the same facts | closed-world certifies **40/40** requirements compliant on an uninspected site; correct answer is **0** |
| **Optimization** | the two strategies an engineer writes without a solver | 79 captures (cost 395) → 32 visits (cost 192) → **10 actions (cost 63)**, 67% cheaper |
| **Applicability** | the same rules against edited site facts | **4 of 4** single-fact edits change what is in force, no rule changed |
| **Scaling** | plan shape as the plant grows | gaps 33 → **511**, plan stays **10 actions**; solve 20ms → 327ms |
| **Determinism** | 5 independent solves | 1 distinct plan |

The scaling row is the one worth staring at. The solver **switches strategy on its own**:

```
cells  subjects  gaps  actions  sweep/survey/capture  strategy
1      10        33    10       0/9/1                 survey
2      11        35    10       1/8/1                 sweep
240    249       511   10       1/8/1                 sweep
```

At one cell a per-subject visit is cheapest; at two or more a single sweep wins. Nobody
codes that threshold — it falls out of the cost model. And gaps grow 15× while the work
list stays flat, which is what makes an inspection of a real plant tractable at all.

### What this does *not* prove

- **The cost model (5/6/10) is invented.** The solver picks the right *mix* per site
  without anyone coding the rule; the specific savings percentage is an artifact of three
  numbers with no empirical basis.
- **Rule coverage is 10 of 455 binding clauses (2.2%)** — Chapter D §6 only. The reasoning
  machinery is proven; the ruleset is a pilot.
- **Evidence is self-reported.** `satisfied` means an inspector typed `p`. There is no
  verification layer, and the `evidence_uri` field that implied one has been removed rather
  than left as decoration.
- Only battery strings form sweep groups, so the flat-plan result generalizes to one
  entity type so far.

## Layout recovery is inferred, not hardcoded

`layout.py` knows nothing about this document. It derives structure from signals any
paginated standard carries:

- **running headers/footers** — found geometrically (text in stable margin bands) plus by
  repetition with digits masked, so `... D-4` and `... D-5` compare equal
- **numbering scheme** — candidate families (`6.6`, `A.1`, `(3)`, `a)`, roman) scored
  against real paragraph starts; this document resolves to `dotted`
- **paragraphs** — the PDF's own text blocks
- **tables** — `page.find_tables()`, with their cells excluded from clause prose
- **chapter titles** — read from the running header, by majority vote across the chapter

Chapter G puts clause numbers on their own line while every other chapter puts them
inline. Both forms are normalized rather than special-cased.

`entities.py` pulls out the machine-usable pieces with genre-level patterns: numeric
thresholds with their comparators, verbatim label text, conductor gauges, designators,
cross-references, and — critically — **carve-outs and negations**, because a rule that
drops "except with written permission" demands evidence the standard waives.

Thresholds are written three different ways in this document and all three are caught:

| source text | extracted |
|---|---|
| `no more than two (2) feet` | `2 feet`, comparator `no more than` |
| `18 inches` | `18 inches` |
| `no less than two inches` | `2 inches`, comparator `no less than` |

## Modelling notes

Two things the compiler treats as first-class, because getting them wrong is the most
dangerous failure mode:

**Exemptions.** `D.6.8` says leads internal to the relay rack *do not require* 145C tags.
It imposes no duty; it narrows `D.6.7`. It is recorded as `kind: exemption` and realized
as a `not internal_to_rack(L)` guard on the rule it modifies. Dropping it would send an
inspector to photograph tags the standard explicitly waives.

**Non-field-verifiable obligations.** `D.6.4` and `D.6.5` govern the fuse record book. No
photo settles them, so they emit no observables and stay permanently `undetermined`,
reported under "cannot be settled by capture" — visible rather than silently absent.

## Layout

```
src/eiguide/
  layout.py     document-agnostic structure recovery
  entities.py   generic threshold / literal / carve-out extraction
  extract.py    assembly and naming (thin)
  compile.py    rules.jsonl -> clingo, mechanical
  reason.py     solve, and read the answer set as a plan or a verdict
  prove.py      experiments testing the solver against controls
  cli.py        the commands
ontology/
  core.lp       three-valued verdict, gaps, the #minimize plan
  domain.lp     site vocabulary + the three tiers of capture action
rules/          generated
sites/den01.lp  example site facts
data/golden/    hand-authored, reviewed rules for Chapter D §6
```

## Tests

```bash
uv run pytest        # 46 tests, ~37s (parses the real PDF once)
```

They pin the claims rather than the implementation: that an unobserved site is never
reported compliant, that carve-outs suppress the requirements they waive, that one sweep
beats 24 photos, that a single bad cell violates only that cell, and that no evidence gap
is ever silently dropped from a plan.

## Status / next

- `data/rules.jsonl` is currently hand-authored for **Chapter D §6** (12 rules). Everything
  downstream is chapter-agnostic — scaling is a matter of authoring more rules.
- Generating a first draft of those rules with an LLM is the obvious next step. Nothing
  downstream depends on how they were produced; the schema, the verbatim-`citation_span`
  check, and `eiguide review` are the guardrails that stage would plug into.
- `Observable.accepts` holds a machine-checkable acceptance criterion for every capture
  request. Nothing evaluates it yet — that is the seam where vision-based verification
  attaches without reshaping the schema.

> The source PDF is marked confidential and proprietary to Level 3 Communications. All
> processing here is local.
