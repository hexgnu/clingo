# Evidence Layer Implementation - COMPLETE ✅

## What Was Built

Implemented the "largest structural change outstanding" (DESIGN.md §1) - a unified evidence layer with:

### 1. **Identity** 
- Each piece of evidence has unique ID (`evidence_1`, `evidence_2`,...)
- Can track and correlate evidence across systems
- Reference specific evidence in queries

### 2. **Provenance**
- `EvidenceSource` model captures who/what produced evidence
- Types: human (inspector), system (NMS), sensor (PDU)
- Includes system name for automated sources
- Full audit trail of where evidence came from

### 3. **Temporal Ordering**
- Every evidence includes timestamp (Unix epoch or sequence number)
- ASP ontology derives `before(E1, E2)` predicate
- Enables "A happened BEFORE B" queries
- Supports root cause analysis (e.g., "power failed before node down")

### 4. **Confidence**
- 0.0-1.0 scale for evidence reliability
- Enables confidence-based reasoning
- Distinguishes high-confidence automation from low-confidence readings
- Humans implicitly trusted (confidence=1.0)

### 5. **Backward Compatibility**
- Generates BOTH old `obs/3` and new `evidence/8` facts
- Existing rules continue working unchanged
- New rules can use rich evidence queries
- Gradual migration path - no big-bang cutover

## Files Created/Modified

### New Files
- `ontology/evidence.lp` - ASP rules for temporal reasoning, conflict detection, provenance
- `tests/test_evidence.py` - 10 tests covering evidence model
- `EVIDENCE_DESIGN.md` - Full design document with examples
- `docs/SCHEMA_MIGRATIONS.md` - Migration guide (task #10)

### Modified Files
- `src/eiguide/models.py` - Added Evidence, EvidenceSource models
- `src/eiguide/reason.py` - Generate both evidence formats
- All models now include `schema_version` field

## Evidence Model Structure

```python
Evidence(
    id="evidence_1",                    # Identity
    kind="observation",                 # observation | test_result | claim | alarm
    subject="cell(bs1,7)",             # What was observed
    property="cell_number_legible",    # What about it
    value=True,                        # Result
    source=EvidenceSource(             # Provenance
        type="human",
        id="inspector_alice"
    ),
    timestamp=1723567890,              # Temporal
    confidence=1.0,                    # Quality
    method="photo",                    # How obtained
    incident_id="incident_5120"        # Correlation
)
```

## ASP Capabilities Unlocked

### Temporal Reasoning
```prolog
% Power failed BEFORE node went down
power_caused_outage :-
    evidence(E1, _, pdu(p1), power_state, absent, _, T1, _),
    evidence(E2, _, node(n1), reachable, false, _, T2, _),
    T1 < T2,
    feeds(p1, n1).
```

### Conflict Detection
```prolog
% Multiple sources disagree about same fact
conflicting_evidence(E1, E2) :-
    evidence(E1, _, S, P, V1, _, _, _),
    evidence(E2, _, S, P, V2, _, _, _),
    E1 != E2, V1 != V2.
```

### Provenance Queries
```prolog
% Count findings by inspector
inspector_findings(Inspector, Count) :-
    Count = #count{E : evidence(E, observation, cell(_,_), _, fail,
                                source(human, Inspector), _, _)}.
```

### Confidence Filtering
```prolog
% Only trust high-confidence OR human evidence for critical decisions
reliable(E) :- high_confidence(E).
reliable(E) :- human_evidence(E).
```

## Test Coverage

**120 tests passing** (10 new evidence tests):

1. `test_evidence_source_model` - Provenance capture
2. `test_evidence_model_basic` - Core model
3. `test_evidence_to_asp_boolean_value` - ASP generation
4. `test_evidence_to_asp_string_value` - Quoted values
5. `test_evidence_to_asp_numeric_value` - Numbers
6. `test_observation_to_evidence_conversion` - Migration
7. `test_observation_to_evidence_default_timestamp` - Timestamp defaults
8. `test_evidence_confidence_validation` - Bounds checking
9. `test_evidence_with_incident_correlation` - Grouping
10. `test_multiple_observations_to_facts` - Batch generation

## Migration Strategy

### Phase 1: ✅ COMPLETE
- [x] Add Evidence/EvidenceSource models
- [x] Add to_evidence() to Observation
- [x] Create ontology/evidence.lp
- [x] Generate both obs/3 and evidence/8 facts
- [x] All tests passing

### Phase 2: Next Steps
- [ ] Update one chapter to use evidence/8 queries
- [ ] Demonstrate temporal reasoning use case
- [ ] Update triage.py for test_result → evidence
- [ ] Write correlation examples

### Phase 3: Adoption
- [ ] New rules use evidence/8
- [ ] Document patterns in VOCABULARY.md
- [ ] Training examples for common queries

### Phase 4: Unification (Task #2)
- [ ] Ticket system adopts evidence/8
- [ ] Remove duplicate predicates
- [ ] Shared ontology for both systems

## Technical Details

### ASP Fraction Notation
Confidence values use fraction notation to avoid ASP decimal parsing issues:
- `1.0` → `1`
- `0.0` → `0`  
- `0.95` → `95/100`

### Backward Compatibility Mapping
```prolog
% Old predicates map to new evidence layer
obs(Subject, Property, Value) :-
    evidence(_, observation, Subject, Property, Value, _, _, _).

test_result(Test, Value) :-
    evidence(_, test_result, _, Test, Value, _, _, _).
```

### Source Flexibility
Supports both simple and system-qualified sources:
- `source(human, "alice")` - Human inspector
- `source(system, "nms", "samsung")` - System with name
- `source(sensor, "pdu_01")` - Sensor

## Impact

This completes DESIGN.md §1 "largest structural change" and enables:

✅ Evidence correlation across systems
✅ Temporal reasoning for root cause analysis  
✅ Provenance tracking for audit trails
✅ Confidence-based filtering for reliability
✅ Incident grouping for alarm storms
✅ Bridge between compliance and ticket systems (toward task #2)

**Next:** Use this foundation to unify compliance and ticket pipelines (task #2)

## Usage Example

```python
# Create evidence from inspection
from eiguide.models import Evidence, EvidenceSource

source = EvidenceSource(type="human", id="inspector_alice")

ev = Evidence(
    id="ev_1",
    kind="observation",
    subject="cell(bs1,7)",
    property="cell_number_legible",
    value=True,
    source=source,
    timestamp=int(time.time()),
    confidence=1.0,
    method="photo"
)

# Generate ASP fact
print(ev.to_asp())
# evidence(ev_1, observation, cell(bs1,7), cell_number_legible, true, source(human, "inspector_alice"), 1723567890, 1).
```

## References

- DESIGN.md §1: Original gap identification
- DESIGN.md §6: Temporal ordering requirements
- UNIFICATION.md: Unified vocabulary
- EVIDENCE_DESIGN.md: Full design doc
