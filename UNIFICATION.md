# Unification: Terminology toward a unified model

Posture: keep the two pipelines separate, but use language that makes them interchangeable. This means both ticket and compliance reasoning speak the same vocabulary. It does not mean merging solvers — just clarifying that they solve the same kind of problem.

---

## Core concepts (rename for both)

### Possibility (what we're reasoning about)

| ticket | compliance | unified |
|---|---|---|
| `fault(H)` | `obligation(R, X)` | `possibility(P)` |
| | | a hypothesis about what *is* or what *remains* |

The ticket `fault` is a hypothesis about system state. The compliance `obligation` is a hypothesis about what work remains. Both are things we enumerate and constrain.

**Action:** Rename both to use `possibility/1` — or keep the names but add a type tag: `possibility(fault, H)` and `possibility(obligation, R, X)`.

---

### Evidence (what we know)

| ticket | compliance | unified |
|---|---|---|
| `test_result(T, V)` | `obs/3` (from domain) | `evidence(E, V)` |
| `claim/4` | `obs/3` | `evidence(E, V)` |
| — | — | carries: modality, provenance, standing, effect |

Both sides have inputs that constrain the possibility set. The ticket has tests and records; compliance has observations. All are `evidence`.

**Action:** Unify as `evidence(E, V)` with dimensions from [VOCABULARY.md](VOCABULARY.md). Map:
- `test_result(T, V)` → `evidence(test(T), V, effect: effect(T))`
- `claim(S, F, V, C)` → `evidence(claim(S, F), V, effect: effect(F))`
- `obs(S, O, V)` → `evidence(obs(S, O), V, effect: effect(O))`

---

### Effect (how evidence bears on possibilities)

| ticket | compliance | unified |
|---|---|---|
| `confirms/3` | — | `supports(E, P)` |
| `rules_out/3` | — | `refutes(E, P)` |
| — | `satisfied/2` | `holds(P)` or derived from effect |
| — | `violated/2` | `contradicts(E, P)` or refutes |

**Action:** Use `supports(E, P)` and `refutes(E, P)` for both. Derive `holds(P)` from the absence of refutation under three-valued logic.

---

### Action (what we can do)

| ticket | compliance | unified |
|---|---|---|
| `do_test(T)` | `do(A)` | `action(A)` and `do(A)` |
| `action_cost/2` | `action_cost/2` | keep as-is |

Already almost unified. Just normalize to `action(A)` and always use `do(A)` for the choice rule.

---

### Settlement (what an action establishes or closes)

| ticket | compliance | unified |
|---|---|---|
| — | `closes(R, X, A)` | `settles(A, P)` |
| derived plan | — | action → plan (which possibilities it addresses) |

The compliance side explicitly tracks what each action closes. The ticket side derives a plan implicitly from minimizing tests. For unification, both should use `settles/2`:

```prolog
settles(A, P) :- action(A), test_resolves(A, P).           % ticket: a test settles a possibility
settles(A, P) :- action(A), closes(R, X, A), possibility(obligation, R, X).  % compliance
```

**Action:** Add `settles(A, P)` as a derived predicate on both sides, mapping test resolutions and closures.

---

## Domain-specific (keep)

These stay as-is because they carry domain-specific meaning:

| ticket | compliance |
|---|---|
| `load_bearing(F)` | `applies(R, X)` |
| `uncertain(H)`, `provisional(H)` | — |
| `indistinguishable/2` | `unreachable/3` |
| `needs_verification/1` | — |

---

## The unified frame

Once renamed, both solvers answer the same question:

```
Given:
  - a set of possibilities (faults, obligations, unknowns)
  - evidence that supports or refutes each
  - actions that settle possibilities
  - a cost for each action

Find:
  - the minimal set of possibilities that survive all constraints
  - the cheapest sequence of actions that would distinguish survivors
```

Then:
- Ticket solver: possibilities are faults; evidence is test results; actions are tests.
- Compliance solver: possibilities are obligations; evidence is observations; actions are remediation.

Same question, different domains.

---

## Migration strategy (low-risk)

1. Add unified predicates alongside domain-specific ones (no removal).
   ```prolog
   possibility(fault, H) :- fault(H).
   possibility(obligation, R, X) :- obligation(R, X).
   
   evidence(test(T), V) :- test_result(T, V).
   evidence(claim(F), V) :- claim(_, F, V, _).
   
   supports(test(T), fault(H)) :- confirms(T, _, H).
   refutes(test(T), fault(H)) :- rules_out(T, _, H).
   ```

2. Update documentation and new code to use unified names.

3. Keep old predicates working until old code is gone (no rush).

4. Once both sides are stable and using unified names consistently, consider merging solvers (separate work).

