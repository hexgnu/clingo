% Evidence that arrives from a machine.
%
% A person answering "yes, the label is legible" is making one kind of claim. A vision
% model returning `legible: true, 0.62` is making a different one, and flattening the
% second into the first is how a marginal read becomes a compliance record.
%
% This is the same three-state discipline already applied to OneVizion rows, moved one
% level over to observations: an observation is decisive, refuting, or **inconclusive**.
% An inconclusive read is not a failure and not a pass -- it means the question is still
% open and should go to a source with more authority.
%
% Deliberately additive. A plain `obs(X, O, V)` from a technician still works exactly as
% before, so nothing that already relies on human capture has to change.

#program base.

#defined observed/5.
#defined confidence_required/2.
#defined default_confidence/1.
#defined source_tier/2.
#defined can_observe/2.

% observed(Subject, Observable, Value, Source, Confidence)   0-100
% confidence_required(Observable, Pct)   per-observable bar
% default_confidence(Pct)                the bar when nothing more specific is set
% source_tier(Source, Tier)              1 automated, 2 assisted, 3 human on site

% ---------------------------------------------------------------------------
% How sure is sure enough
% ---------------------------------------------------------------------------
% Set per observable, because the bar is not uniform. Reading a printed cell number is a
% different problem from judging whether a cable flows over a rack edge, and a torque
% value should not be accepted from a model at all.

required_confidence(O, C) :- confidence_required(O, C).
required_confidence(O, D) :- observed(_, O, _, _, _), default_confidence(D),
                             not confidence_required(O, _).

% ---------------------------------------------------------------------------
% Three states
% ---------------------------------------------------------------------------

% Clears the bar: it counts, and feeds the ordinary verdict machinery unchanged.
obs(X, O, V) :- observed(X, O, V, _, C), required_confidence(O, R), C >= R.

% Below the bar: recorded, attributed, and explicitly NOT settling anything. The gap
% survives, so the plan keeps asking -- which is the whole point.
inconclusive(X, O, S, C) :- observed(X, O, _, S, C), required_confidence(O, R), C < R.

% A source that has already looked and come back unsure should not be asked again. This is
% what turns "the model is not certain" into "escalate", rather than into a retry loop.
exhausted(X, O, S) :- inconclusive(X, O, S, _).

% What the next attempt should come from: any source that can observe this and has not
% already failed to.
escalate_to(X, O, S) :- inconclusive(X, O, Failed, _), can_observe(S, O), S != Failed,
                        not exhausted(X, O, S).

% Nothing left to escalate to. Worth reporting plainly: it means the observable cannot be
% settled by any source configured, which is a coverage problem rather than a field problem.
no_source_left(X, O) :- inconclusive(X, O, _, _), not escalate_to(X, O, _).

% ---------------------------------------------------------------------------
% Disagreement between sources
% ---------------------------------------------------------------------------
% Two confident sources returning opposite answers is a stronger signal than either alone,
% and must never be resolved by whichever happened to be recorded last.

conflicting(X, O) :- observed(X, O, true, S1, C1), observed(X, O, false, S2, C2),
                     S1 != S2, required_confidence(O, R), C1 >= R, C2 >= R.

% A contested observation settles nothing until a human breaks the tie.
:- conflicting(X, O), obs(X, O, _), not adjudicated(X, O).
#defined adjudicated/2.

#show inconclusive/4.
#show escalate_to/3.
#show no_source_left/2.
#show conflicting/2.
