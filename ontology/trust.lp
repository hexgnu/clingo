% Facts of uncertain provenance.
%
% A system of record like OneVizion is authoritative about what was *intended* and only
% approximately right about what is *there*. A circuit gets re-groomed and the record lags;
% a router is swapped and the asset tag is not updated; a span is spliced and the topology
% row is never touched. Treating those rows as ground truth is how a diagnosis confidently
% blames the wrong span.
%
% So the same discipline used for observations is applied one level down, to the facts
% themselves. A fact is established, refuted, or *asserted but unverified* -- and anything
% derived from an unverified fact inherits that status. The reasoner is then able to say
% "I can tell you the answer, but only if the record is right about X", and to schedule
% checking X when that matters.

#program base.

#defined claim/4.
#defined field_check/2.
#defined today/1.
#defined stale_after/1.
#defined min_confidence/1.

% claim(Source, Fact, Confidence, AsOfDay)   what a system of record asserts, and when
% field_check(Fact, true|false)              what someone actually confirmed on site
% today(Day), stale_after(Days), min_confidence(Pct)

fact(F) :- claim(_, F, _, _).
fact(F) :- field_check(F, _).

% ---------------------------------------------------------------------------
% Why a claim might not be good enough
% ---------------------------------------------------------------------------

low_confidence(F) :- claim(S, F, C, _), min_confidence(M), C < M.

% Where a provenance chain exists, the number that counts is the derived one, not the one
% the holding system states. A row imported at 90% from a 60% inference is a 40% row.
#defined effective_confidence/2.
#defined never_grounded/1.
low_confidence(F) :- effective_confidence(F, C), min_confidence(M), C < M.

% And a value nobody ever grounded is suspect at any confidence.
suspect(F) :- never_grounded(F).

stale(F) :- claim(S, F, _, As), today(D), stale_after(Age), D - As > Age.

% Two sources disagreeing about the same fact is worth more than either claim alone: it is
% positive evidence that the record is unreliable here.
contradicted(F) :- claim(S1, F, _, _), claim(S2, neg(F), _, _), S1 != S2.
contradicted(F) :- claim(S1, neg(F), _, _), claim(S2, F, _, _), S1 != S2.

suspect(F) :- low_confidence(F).
suspect(F) :- stale(F).
suspect(F) :- contradicted(F).

% ---------------------------------------------------------------------------
% Three states, again
% ---------------------------------------------------------------------------

established(F) :- field_check(F, true).
refuted(F) :- field_check(F, false).

% A clean, current, uncontradicted claim is good enough to act on without a site visit.
% Anything else needs someone to look.
established(F) :- claim(_, F, _, _), not suspect(F), not refuted(F), not field_check(F, false).

unverified(F) :- fact(F), suspect(F), not established(F), not refuted(F).

% What the reasoner is willing to use.
holds(F) :- established(F).

% Facts worth confirming: an unverified fact that something actually depends on. Verifying
% record rows nobody is relying on is busywork.
needs_verification(F) :- unverified(F), load_bearing(F).

#show established/1.
#show refuted/1.
#show unverified/1.
#show needs_verification/1.
#show suspect/1.
