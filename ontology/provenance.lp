% How far a value is from something anyone actually looked at.
%
% A system of record states a confidence, and that number is usually fiction. OneVizion
% says 90% because the row was imported cleanly -- not because anyone stood in front of the
% plant. Trace the row back and it came from a migration tool, which took it from a design
% document, which recorded intent rather than as-built. Three transcriptions from anything
% physical, each one confident, none of them grounded.
%
% So confidence is not asserted here. It is *derived* from the chain, under two rules that
% are hard to argue with:
%
%   1. A chain is no better than its weakest link. Copying a guess does not improve it.
%   2. Every hop away from an observation costs something, because transcription, schema
%      mapping and staleness all get a chance to bite.
%
% The second axis is orthogonal and just as important. A **physical** claim -- this span
% feeds that router -- can only be grounded by someone looking. A **logical** claim -- this
% circuit is provisioned on that VLAN -- is grounded by the design authority, and sending a
% technician to check it is a category error. They need different escalation paths.

#program base.

#defined stated_confidence/2.
#defined derived_from/2.
#defined layer/2.
#defined origin/2.
#defined degree_penalty/1.
#defined max_degrees/1.

% stated_confidence(Assertion, Pct)   what the holding system claims
% derived_from(Assertion, Source)     this value was taken from that one
% layer(Assertion, physical|logical)  what kind of thing it describes
% origin(Assertion, Kind)             grounded | human_reviewed | inferred | copied | assumed

assertion(F) :- stated_confidence(F, _).
assertion(F) :- derived_from(F, _).
assertion(F) :- derived_from(_, F).

degree_penalty(10).
max_degrees(6).

% ---------------------------------------------------------------------------
% The chain
% ---------------------------------------------------------------------------

ancestor(F, F) :- assertion(F).
ancestor(F, G) :- derived_from(F, H), ancestor(H, G).

% Distance from whatever the value was originally taken from.
degrees(F, D) :- assertion(F), D = #count { G : ancestor(F, G), G != F }.

% A value nobody ever grounded in an observation. Its whole chain is records about records.
grounded(F) :- origin(F, grounded).
grounded(F) :- origin(F, human_reviewed).
ungrounded(F) :- assertion(F), not grounded(F) : ancestor(F, G), grounded(G).
ungrounded(F) :- assertion(F), not any_grounded_ancestor(F).
any_grounded_ancestor(F) :- ancestor(F, G), grounded(G).

% ---------------------------------------------------------------------------
% Effective confidence
% ---------------------------------------------------------------------------

weakest_link(F, C) :- assertion(F),
                      C = #min { X : ancestor(F, G), stated_confidence(G, X) }.

effective_confidence(F, C) :- weakest_link(F, W), degrees(F, D), degree_penalty(P),
                              C = W - D * P, C >= 0.
effective_confidence(F, 0) :- weakest_link(F, W), degrees(F, D), degree_penalty(P),
                              W - D * P < 0.

% A holding system claiming more certainty than the value it copied. Worth reporting on its
% own: it is the signature of confidence being manufactured by an import job.
inflated(F, Held, Source) :- derived_from(F, G),
                             stated_confidence(F, Held), stated_confidence(G, Source),
                             Held > Source.

% Chains long enough that the number at the end means nothing.
too_far(F) :- degrees(F, D), max_degrees(M), D >= M.

% Groundedness is a separate axis from confidence, and collapsing them is how design intent
% gets treated as as-built. A value nobody ever confirmed against the world is unverified
% however certain the holding system is about it -- "we are 95% sure this is what we
% specified" is not a claim about what is installed.
never_grounded(F) :- ungrounded(F).
never_grounded(F) :- origin(F, assumed).

% ---------------------------------------------------------------------------
% Where to go to settle it
% ---------------------------------------------------------------------------
% This is why the logical/physical split has to be explicit. Rolling a truck to confirm a
% VLAN assignment wastes a day and settles nothing; asking engineering whether a fibre is
% actually spliced through settles nothing either.

settle_by(F, field_observation) :- layer(F, physical).
settle_by(F, design_authority) :- layer(F, logical).
settle_by(F, unknown_route) :- assertion(F), not layer(F, physical), not layer(F, logical).

#show effective_confidence/2.
#show degrees/2.
#show inflated/3.
#show too_far/1.
#show ungrounded/1.
#show never_grounded/1.
#show settle_by/2.
