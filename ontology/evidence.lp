% Evidence layer with identity, provenance, and temporal ordering
% Design: DESIGN.md §1 "The largest structural change outstanding"
% Unification: UNIFICATION.md - bridge between compliance and ticket systems

% Core evidence facts (generated from Python Evidence model)
% evidence(Id, Kind, Subject, Property, Value, Source, Timestamp, Confidence).
%
% Example:
%   evidence(evidence_1, observation, cell(bs1,7), cell_number_legible, true, 
%            source(human, "alice"), 1723567890, 1.0).

% === Temporal Ordering ===

% Derive temporal ordering from timestamps
before(E1, E2) :- 
    evidence(E1, _, _, _, _, _, T1, _),
    evidence(E2, _, _, _, _, _, T2, _),
    E1 != E2,
    T1 < T2.

% Concurrent evidence (same timestamp - may be from same batch/event)
concurrent(E1, E2) :-
    evidence(E1, _, _, _, _, _, T, _),
    evidence(E2, _, _, _, _, _, T, _),
    E1 != E2.

% === Subject Correlation ===

% Evidence about the same subject
concerns(E, S) :- evidence(E, _, S, _, _, _, _, _).

same_subject(E1, E2) :-
    concerns(E1, S),
    concerns(E2, S),
    E1 != E2.

% === Source Classification ===

% Evidence by source type
human_evidence(E) :- evidence(E, _, _, _, _, source(human, _), _, _).
human_evidence(E) :- evidence(E, _, _, _, _, source(human, _, _), _, _).

automated_evidence(E) :- evidence(E, _, _, _, _, source(system, _), _, _).
automated_evidence(E) :- evidence(E, _, _, _, _, source(system, _, _), _, _).

sensor_evidence(E) :- evidence(E, _, _, _, _, source(sensor, _), _, _).
sensor_evidence(E) :- evidence(E, _, _, _, _, source(sensor, _, _), _, _).

% === Confidence Levels ===

high_confidence(E) :- evidence(E, _, _, _, _, _, _, C), C >= 0.9.
medium_confidence(E) :- evidence(E, _, _, _, _, _, _, C), C >= 0.5, C < 0.9.
low_confidence(E) :- evidence(E, _, _, _, _, _, _, C), C < 0.5.

% Reliable evidence: high confidence OR human source
reliable(E) :- high_confidence(E).
reliable(E) :- human_evidence(E).

% === Conflict Detection ===

% Contradictory evidence: same subject/property, different values, neither subsumed
conflicting_evidence(E1, E2) :-
    evidence(E1, _, S, P, V1, _, _, _),
    evidence(E2, _, S, P, V2, _, _, _),
    E1 != E2,
    V1 != V2.

% Evidence from different sources about same thing
multi_source(S, P) :-
    evidence(E1, _, S, P, _, Src1, _, _),
    evidence(E2, _, S, P, _, Src2, _, _),
    E1 != E2,
    Src1 != Src2.

% === Incident Correlation ===

% Group evidence by incident ID
incident_evidence(I, E) :- evidence(E, _, _, _, _, _, _, _), incident(E, I).

% Define which evidence belongs to which incident (external fact or derived)
% incident(EvidenceId, IncidentId) - must be provided as input

% === Backward Compatibility ===

% Map old predicates to new evidence layer
% This allows existing rules to keep working while new rules use evidence/8

% obs(Subject, Property, Value) from compliance side
obs(Subject, Property, Value) :-
    evidence(_, observation, Subject, Property, Value, _, _, _).

% test_result(Test, Value) from ticket side
test_result(Test, Value) :-
    evidence(_, test_result, _, Test, Value, _, _, _).

% claim(Source, Fact, Value, Confidence) from ticket side
claim(SourceId, Fact, Value, Confidence) :-
    evidence(_, claim, _, Fact, Value, source(_, SourceId), _, Confidence).
claim(SourceId, Fact, Value, Confidence) :-
    evidence(_, claim, _, Fact, Value, source(_, SourceId, _), _, Confidence).

% === Temporal Reasoning Helpers ===

% Evidence about Subject before evidence about Other
earlier_evidence(Subject, Other) :-
    evidence(E1, _, Subject, _, _, _, _, _),
    evidence(E2, _, Other, _, _, _, _, _),
    before(E1, E2).

% Property P1 observed before P2 on same subject
property_sequence(S, P1, P2) :-
    evidence(E1, _, S, P1, _, _, _, _),
    evidence(E2, _, S, P2, _, _, _, _),
    before(E1, E2).

% === Quality Filters ===

% Evidence meeting quality bar for critical decisions
critical_quality(E) :-
    high_confidence(E),
    human_evidence(E).

critical_quality(E) :-
    high_confidence(E),
    automated_evidence(E),
    evidence(E, _, _, _, _, source(system, System), _, _),
    trusted_system(System).

% Define trusted systems (must be provided as input)
% trusted_system("samsung_nms").
% trusted_system("snmp_collector").
