% Ticket resolution: unsolved world -> solved world.
%
% The compliance side asks "which obligations are undischarged?" and plans a minimum cover.
% A ticket asks a different question -- "which of the competing explanations is true?" --
% and the right plan is the cheapest set of tests that tells them apart. Same solver, same
% three-valued honesty, different objective.
%
% A ticket is SOLVED when exactly one candidate explanation survives, every record it rests
% on is established, no alarm went uninterpreted, and no evidence contradicts itself.
% Anything less is reported as open with the specific reason, never as a best guess.
%
% Laid out GENERATE / DEFINE / TEST / OPTIMIZE / DISPLAY. Rule order has no bearing on the
% answer sets; the sections are for the reader, so that what is *chosen* can be told apart
% from what is *derived* and what is *forbidden*.

#program base.

% ===========================================================================
% INPUT SIGNATURE
% ===========================================================================
% Supplied by a ticket instance, a knowledge base, or the trust layer.

#defined ticket/1.
#defined symptom/2.
#defined raw_alarm/2.
#defined maps_to/3.
#defined unmapped_code/2.
#defined asset/1.
#defined ticket_asset/2.
#defined hypothesis/1.
#defined explains/2.
#defined test/1.
#defined test_cost/2.
#defined rules_out/3.
#defined confirms/3.
#defined test_result/2.
#defined requires_fact/2.
#defined resolution/2.
#defined dispatch_required/1.

% ===========================================================================
% GENERATE
% ===========================================================================
% The only choices in the program: which tests to run, and which suspect records to go and
% confirm. Everything below is derived from these plus the evidence.

{ do_test(T) } :- test(T), not test_result(T, _).

{ verify(F) } :- needs_verification(F).

% ===========================================================================
% DEFINE
% ===========================================================================

% --- symptoms, translated from whatever the originating system called them ---

symptom(T, S) :- ticket(T), raw_alarm(Src, Code), maps_to(Src, Code, S).

% An alarm the knowledge base cannot interpret is not a neutral event: the ticket is
% carrying evidence the reasoner is blind to, so no answer derived without it is complete.
blind_spot :- unmapped_code(_, _).

% --- candidate explanations ---

candidate(H) :- hypothesis(H), symptom(T, S), explains(H, S), ticket(T), not eliminated(H).

eliminated(H) :- test_result(Test, Value), rules_out(Test, Value, H).
confirmed(H) :- test_result(Test, Value), confirms(Test, Value, H).

% Evidence pointing both ways about the same explanation. Once readings arrive from
% instruments rather than fixtures this is the normal case, not the exotic one: an OTDR shot
% down the wrong fibre, a port mis-scoped, a reading taken against a stale topology.
%
% Left alone the contradiction resolves itself the worst possible way -- `eliminated` wins,
% the explanation vanishes from the candidate set without comment, and whatever remains is
% reported as the answer with no positive evidence behind it.
contested(H) :- confirmed(H), eliminated(H).
any_contested :- contested(_).

% Which readings disagree, so the next action can be "re-run that test" rather than another
% test that cannot help.
disputed_by(H, T1, T2) :- contested(H),
                          test_result(T1, V1), confirms(T1, V1, H),
                          test_result(T2, V2), rules_out(T2, V2, H).

% --- what a diagnosis leans on ---
% If blaming a fiber span depends on a record saying this router is fed by that span, then
% that record is load-bearing and its reliability is part of the diagnosis.

load_bearing(F) :- candidate(H), requires_fact(H, F).

eliminated(H) :- requires_fact(H, F), refuted(F).

% A hypothesis resting on an unverified record can still be true, but cannot be concluded.
% This is what keeps a stale row from being laundered into a confident answer.
provisional(H) :- candidate(H), requires_fact(H, F), unverified(F).

% --- what a test responds to, and what it can return ---
% Both DERIVED from the outcome table, never authored. Stating them separately lets the two
% drift: `observes(ping_node, config_drift)` once claimed discriminating power no outcome
% delivered, so the planner kept scheduling a test that could not move either candidate.

observes(T, H) :- rules_out(T, _, H).
observes(T, H) :- confirms(T, _, H).

outcome(T, V) :- rules_out(T, V, _).
outcome(T, V) :- confirms(T, V, _).

test_without_outcomes(T) :- test(T), not outcome(T, _).

% --- discrimination ---
% Not coverage. Two candidates have to be told APART.
%
% Discrimination happens at the level of an OUTCOME, not a test. Asking "does this test
% respond to H1 but not H2" gets the ideal case exactly backwards: read_optical_power
% responds to both fiber_cut and optic_degraded, so a test-level rule calls it useless for
% that pair -- when in fact `no_light` confirms one and rules out the other, and it is the
% cheapest thing that settles them. Under the test-level rule the planner reached past a
% cost-1 optical read for a cost-8 OTDR.

effect(T, V, H, ruled_out) :- rules_out(T, V, H).
effect(T, V, H, confirmed) :- confirms(T, V, H).
effect(T, V, H, no_change) :- outcome(T, V), hypothesis(H),
                              not rules_out(T, V, H), not confirms(T, V, H).

separates(T, H1, H2) :- candidate(H1), candidate(H2), H1 < H2, outcome(T, V),
                        effect(T, V, H1, E1), effect(T, V, H2, E2), E1 != E2.

distinguishable(H1, H2) :- separates(T, H1, H2), test(T).

% A pair nothing available can separate. Surfaced rather than tolerated: it means the
% diagnosis cannot be completed with the tests on hand, which is a dispatch decision rather
% than a reasoning failure.
indistinguishable(H1, H2) :- candidate(H1), candidate(H2), H1 < H2,
                             not distinguishable(H1, H2).

useful_test(T) :- do_test(T), separates(T, _, _).

% --- is it solved ---

open_candidates(N) :- N = #count { H : candidate(H) }.

solved :- open_candidates(1), candidate(H),
          not provisional(H), not blind_spot, not any_contested.

% Every distinct reason a ticket is still open is reported, so "not solved" is never a bare
% negative.
unsolved_reason("no explanation covers the reported symptoms") :- open_candidates(0).
unsolved_reason("several explanations remain") :- open_candidates(N), N > 1.
unsolved_reason("the only explanation rests on an unverified record") :-
    open_candidates(1), candidate(H), provisional(H).
unsolved_reason("the ticket carries alarm codes this knowledge base does not recognize") :-
    blind_spot.
unsolved_reason("evidence for and against the same explanation") :- contested(_).

% --- resolution ---

recommended(R) :- solved, candidate(H), confirmed(H), resolution(H, R).
recommended(R) :- solved, candidate(H), resolution(H, R), not confirmed(H).

truck_roll :- recommended(R), dispatch_required(R).

% ===========================================================================
% TEST
% ===========================================================================

% Every separable pair must actually be separated by the chosen plan.
:- candidate(H1), candidate(H2), H1 < H2, distinguishable(H1, H2),
   not do_test(T) : separates(T, H1, H2).

% No test that separates nothing outstanding.
:- do_test(T), not useful_test(T).

% A test the planner can schedule but whose result nobody can record is a hole in the
% knowledge base, not a valid plan. It sends a technician to do work that cannot change the
% answer.
:- do_test(T), test_without_outcomes(T).

% Load-bearing records still unverified must be confirmed before the answer is relied on.
:- needs_verification(F), not verify(F).

% ===========================================================================
% OPTIMIZE
% ===========================================================================

#minimize { C, T : do_test(T), test_cost(T, C) }.
#minimize { 1, F : verify(F) }.

% ===========================================================================
% DISPLAY
% ===========================================================================

#show candidate/1.
#show provisional/1.
#show eliminated/1.
#show confirmed/1.
#show contested/1.
#show disputed_by/3.
#show do_test/1.
#show verify/1.
#show indistinguishable/2.
#show solved/0.
#show unsolved_reason/1.
#show recommended/1.
#show truck_roll/0.
#show blind_spot/0.
#show outcome/2.
#show test_without_outcomes/1.
#show needs_verification/1.
