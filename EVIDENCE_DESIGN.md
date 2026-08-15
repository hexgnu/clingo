# Evidence Layer Design: Identity, Provenance, Temporal Ordering

## Problem Statement

Current state (`obs/3`, `test_result/2`):
- No identity: can't correlate evidence across systems
- No provenance: don't know who/what/when produced evidence
- No temporal ordering: can't express "power failed BEFORE node down"
- No confidence: all evidence treated equally
- Two separate shapes: compliance uses `obs/3`, tickets use `test_result/2`

## Proposed Solution: Unified Evidence Model

### Core Evidence Predicate

```prolog
evidence(
    Id,           % Unique identifier: evidence_1, evidence_2, ...
    Kind,         % observation | test_result | claim | alarm
    Subject,      % What: cell(bs1,7) | node(core01) | link(uplink_3)
    Property,     % What about it: cell_number_legible | link_status | power_state
    Value,        % Result: pass | fail | up | down | 42
    Source,       % Who/what: inspector(alice) | system(nms) | sensor(pdu_01)
    Timestamp,    % When: seconds since epoch OR sequence number
    Confidence    % 0.0-1.0: certainty of this evidence
).
```

### Python Data Model

```python
# src/eiguide/models.py

class EvidenceSource(BaseModel):
    """Who or what produced this evidence."""
    type: Literal["human", "system", "sensor"]
    id: str  # "inspector_alice", "samsung_nms", "pdu_01"
    system: str | None = None  # System name for automated sources

class Evidence(BaseModel):
    """Unified evidence model for both compliance and ticket systems."""
    schema_version: int = Field(default=SCHEMA_VERSION)
    
    # Identity
    id: str  # "evidence_1", "evidence_2" - globally unique
    
    # Classification
    kind: Literal["observation", "test_result", "claim", "alarm", "measurement"]
    
    # What was observed
    subject: str  # ASP term: cell(bs1,7), node(core01)
    property: str  # cell_number_legible, link_status, power_state
    value: str | float | bool  # Result
    
    # Provenance
    source: EvidenceSource
    timestamp: int  # Unix epoch seconds OR sequence number
    
    # Quality
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    # Optional enrichment
    method: str | None = None  # How obtained: "photo", "ping_test", "snmp_poll"
    notes: str | None = None
    
    # Correlation (for multi-evidence events)
    incident_id: str | None = None  # Groups related evidence

# Backward compatibility wrappers
class Observation(BaseModel):
    """Legacy observation model - wraps Evidence."""
    subject: str
    observable: str
    value: bool
    action: str
    note: str = ""
    
    def to_evidence(self, evidence_id: str, source: EvidenceSource) -> Evidence:
        """Convert to new Evidence model."""
        import time
        return Evidence(
            id=evidence_id,
            kind="observation",
            subject=self.subject,
            property=self.observable,
            value=self.value,
            source=source,
            timestamp=int(time.time()),
            method=self.action,
            notes=self.note
        )
```

### ASP Representation

```prolog
% ontology/evidence.lp - New unified evidence layer

% Core evidence facts (generated from Python Evidence model)
evidence(Id, Kind, Subject, Property, Value, Source, Timestamp, Confidence).

% Temporal ordering derived from timestamps
before(E1, E2) :- evidence(E1, _, _, _, _, _, T1, _),
                  evidence(E2, _, _, _, _, _, T2, _),
                  T1 < T2.

% Same-subject evidence for correlation
concerns(E, S) :- evidence(E, _, S, _, _, _, _, _).

% Confidence thresholds
high_confidence(E) :- evidence(E, _, _, _, _, _, _, C), C >= 0.9.
low_confidence(E) :- evidence(E, _, _, _, _, _, _, C), C < 0.5.

% Source classification
human_evidence(E) :- evidence(E, _, _, _, _, source(human, _), _, _).
automated_evidence(E) :- evidence(E, _, _, _, _, source(system, _), _, _).

% Backward compatibility: map old predicates to new evidence
obs(Subject, Property, Value) :-
    evidence(_, observation, Subject, Property, Value, _, _, _).

test_result(Test, Value) :-
    evidence(_, test_result, _, Test, Value, _, _, _).
```

### Migration Path (Low Risk)

**Phase 1: Add Evidence Model (Non-Breaking)**
```python
# Add Evidence class to models.py
# Add to_evidence() method to Observation
# Keep existing obs/3 generation working
```

**Phase 2: Generate Both Forms**
```python
# reason.py: observations_to_facts()
def observations_to_facts_v2(observations: list[Observation], source: EvidenceSource) -> str:
    """Generate both old obs/3 and new evidence/8 facts."""
    lines = []
    for i, obs in enumerate(observations):
        # New evidence form
        ev = obs.to_evidence(f"evidence_{i}", source)
        lines.append(ev.to_asp())
        
        # Old form for compatibility
        lines.append(f"obs({obs.subject}, {obs.observable}, {obs.value}).")
    return "\n".join(lines)
```

**Phase 3: Update Ontology**
```prolog
% ontology/core.lp - Keep working with both
% Old rules still work via backward-compat mappings
% New rules can use richer evidence/8 queries

% Example: temporal discrimination
power_failed_before_node_down :-
    evidence(E1, _, pdu(_), power_state, absent, _, _, _),
    evidence(E2, _, node(_), reachable, false, _, _, _),
    before(E1, E2).
```

**Phase 4: Gradual Adoption**
- New chapters use evidence/8
- Old chapters keep obs/3 (mapped to evidence/8 internally)
- Ticket system adopts evidence/8 for test_result/claim unification

## Benefits

### 1. Temporal Reasoning
```prolog
% "Power went down BEFORE the node became unreachable"
power_caused_outage :-
    evidence(E1, _, Pdu, power_state, absent, _, T1, _),
    evidence(E2, _, Node, reachable, false, _, T2, _),
    feeds(Pdu, Node),
    T1 < T2.
```

### 2. Evidence Correlation
```prolog
% "Multiple low-confidence claims about same subject → investigate"
conflicting_evidence(Subject) :-
    evidence(E1, _, Subject, Prop, V1, _, _, _),
    evidence(E2, _, Subject, Prop, V2, _, _, _),
    E1 != E2, V1 != V2.
```

### 3. Provenance Tracking
```prolog
% "Inspector Alice marked 3 cells failed"
inspector_findings(Inspector, Count) :-
    Count = #count{E : evidence(E, observation, cell(_,_), _, fail, 
                                source(human, Inspector), _, _)}.
```

### 4. Confidence-Based Reasoning
```prolog
% "Ignore low-confidence automated readings for critical decisions"
reliable_evidence(E) :-
    evidence(E, _, _, _, _, source(human, _), _, _).  % Trust humans

reliable_evidence(E) :-
    evidence(E, _, _, _, _, source(system, _), _, C),
    C >= 0.9.  % Only trust high-confidence automation
```

## Implementation Plan

**Week 1: Data Model**
- [ ] Add `Evidence`, `EvidenceSource` to models.py
- [ ] Add `to_evidence()` method to `Observation`
- [ ] Create ontology/evidence.lp with backward-compat mappings
- [ ] Write tests for Evidence model

**Week 2: Generation**
- [ ] Update reason.py to generate both obs/3 and evidence/8
- [ ] Update triage.py for test_result/2 → evidence/8
- [ ] Ensure all existing tests pass (backward compat)

**Week 3: Adoption**
- [ ] Write temporal reasoning examples in DESIGN.md
- [ ] Update one chapter to use evidence/8 in rules
- [ ] Demonstrate correlation use case

**Week 4: Documentation**
- [ ] Update UNIFICATION.md with evidence/8 as the bridge
- [ ] Document evidence/8 schema in VOCABULARY.md
- [ ] Add migration guide for future chapters

## Risks & Mitigations

**Risk:** ASP program gets too large with metadata
**Mitigation:** Filter evidence by relevance before grounding (only include evidence about subjects in scope)

**Risk:** Backward compatibility breaks existing chapters
**Mitigation:** Generate both forms; old predicates map to new via rules

**Risk:** Timestamp precision issues (clock skew between systems)
**Mitigation:** Use sequence numbers for relative ordering when absolute time unavailable

## Success Criteria

- [ ] Can express "A happened before B" queries
- [ ] Evidence traces back to source (inspector, system, sensor)
- [ ] Confidence values affect reasoning (low-confidence → needs verification)
- [ ] All 110+ existing tests still pass
- [ ] Ticket and compliance systems share evidence/8 predicate
- [ ] New correlation queries work (conflicting evidence detection)
