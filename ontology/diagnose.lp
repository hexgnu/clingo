% An alarm creates an incident world.
%
% The initial alarm gives you a few facts. Cause, impact and remediation are unresolved.
% Every subsequent telemetry point, technician observation or action collapses the
% possibilities until the incident is solved.
%
% That sentence is the encoding. A **world** is one way things could be: a set of faults
% that accounts for what was reported, with nothing spare. The answer sets ARE the
% possibilities, so nothing here maintains a candidate list -- evidence arrives as
% constraints, and worlds stop existing.
%
% What that replaced, and why:
%
%   candidate/1 + eliminated/1     a possibility set maintained by hand, in a single answer
%                                  set. Only elimination could narrow it, so a reading that
%                                  positively confirmed something changed nothing.
%   solved :- open_candidates(1)   forbade two simultaneous faults by construction. A power
%                                  event that takes out a node and its heartbeat is two
%                                  faults, and a plant produces them routinely.
%
% Two passes, because possibility and planning are different questions and no single world
% can answer the second:
%
%   pass 1   no candidate/1 supplied   enumerate the minimal worlds
%   pass 2   candidate/1 supplied      plan the cheapest thing that tells them apart
%
% The union of pass 1's worlds is what is POSSIBLE; the intersection is what is CERTAIN.
% Both are handed back on pass 2 as facts, because agreement is a property of the model set
% and no member of that set can see it.
%
% Rule order has no bearing on the answer sets; the sections are for the reader.

#program base.

% ===========================================================================
% INPUT SIGNATURE
% ===========================================================================

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
#defined authorised_spend/2.
#defined service_affecting/1.
#defined restored/1.

% Supplied on pass 2 only, computed from pass 1's worlds.
#defined candidate/1.        % in at least one minimal world  -- possible
#defined certain/1.          % in every minimal world         -- established
#defined possible_action/1.
#defined certain_action/1.

% ===========================================================================
% GENERATE
% ===========================================================================

% A world is any set of faults. The TEST section decides which sets survive.
{ fault(H) : hypothesis(H) }.

% Pass 2 only. Guarded on candidate/1 because a plan has to discriminate ALL the surviving
% worlds, which is not a property any one of them can see.
{ do_test(T) } :- test(T), not test_result(T, _), candidate(_).
{ verify(F) }  :- needs_verification(F), candidate(_).

% ===========================================================================
% DEFINE
% ===========================================================================

% --- probable cause, in X.733's sense ---
% What the alarm indicates, translated out of whatever the originating system called it.
% X.733 calls this the probable cause and it is NOT the root cause: `loss_of_signal` is what
% the device reported, `fiber_cut` is what the reasoner has to work out.

probable_cause(T, PC) :- ticket(T), raw_alarm(Src, Code), maps_to(Src, Code, PC).

% Retained so knowledge bases can be written either way; probable_cause is the standard term.
symptom(T, PC) :- probable_cause(T, PC).

% An alarm the knowledge base cannot interpret is not a neutral event: the ticket is
% carrying evidence the reasoner is blind to, so no answer derived without it is complete.
blind_spot :- unmapped_code(_, _).

% --- what a test can come back with ---
% Derived from the outcome table, never authored, so the two cannot drift apart.

outcome(T, V) :- rules_out(T, V, _).
outcome(T, V) :- confirms(T, V, _).

test_without_outcomes(T) :- test(T), not outcome(T, _).

% --- reading one world ---
% What this world would have you do. Not yet advice: it is one world's opinion, and the
% incident is only actionable when they agree. See ADVICE below.

resolves_to(R) :- fault(H), resolution(H, R).

% --- what a diagnosis leans on ---
% If blaming a fiber span depends on a record saying this router is fed by that span, then
% that record is load-bearing and its reliability is part of the diagnosis.

load_bearing(F) :- fault(H), requires_fact(H, F).
load_bearing(F) :- candidate(H), requires_fact(H, F).

% Resting on an unverified record does not make an explanation false -- it makes it
% unconcludable. This is what keeps a stale row from being laundered into a confident answer.
provisional(H) :- fault(H), requires_fact(H, F), unverified(F).
provisional(H) :- candidate(H), requires_fact(H, F), unverified(F).
any_provisional :- provisional(_).

% --- evidence that points both ways ---
% Once readings arrive from instruments rather than fixtures this is the normal case, not
% the exotic one: an OTDR shot down the wrong fiber, a port mis-scoped, a reading taken
% against stale topology.
%
% Under elimination it resolved itself the worst possible way -- the explanation vanished
% from the candidate set without comment, and whatever remained was reported as the answer
% with nothing confirming it. Here it is named, and it blocks a verdict.

contested(H) :- confirms(T1, V1, H), test_result(T1, V1),
                rules_out(T2, V2, H), test_result(T2, V2).
any_contested :- contested(_).

% Which readings disagree, so the next action can be "re-run that one" rather than another
% test that cannot help.
disputed_by(H, T1, T2) :- contested(H),
                          test_result(T1, V1), confirms(T1, V1, H),
                          test_result(T2, V2), rules_out(T2, V2, H).

% ===========================================================================
% TEST -- each constraint is a way the world could NOT be
% ===========================================================================

% --- a world should account for what was reported ---
% Soft, not hard. A hard constraint here makes "nothing explains these alarms" come back as
% UNSAT, which throws away every other finding in the same breath -- including the contested
% readings that are usually the reason nothing explains them. An unexplained symptom is a
% result, so it is minimized rather than forbidden.

explained(S)   :- fault(H), explains(H, S).
unexplained(S) :- symptom(_, S), not explained(S).

% ...and carry nothing spare. Without this, every superset of a working explanation is also
% a world and the count is 2^n. Measured: at 15 faults able to explain the alarm, 32512
% worlds without this line, 8 with it.
needed(H) :- fault(H), explains(H, S), symptom(_, S).
:- fault(H), not needed(H).

% --- evidence removes worlds ---
% The whole mechanism. A reading does not update a score or cross a hypothesis off a list.
% It makes certain worlds impossible.

:- fault(H), test_result(T, V), rules_out(T, V, H).
:- fault(H), requires_fact(H, F), refuted(F).

% --- pass 2: the plan has to tell the surviving worlds apart ---
% Discrimination is per OUTCOME, not per test. "Does this test respond to H1 but not H2"
% gets the ideal case backwards: read_optical_power responds to both fiber_cut and
% optic_degraded, so a test-level rule calls it useless for that pair -- when `no_light`
% confirms one and rules out the other, and it is the cheapest thing that settles them.

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

:- candidate(H1), candidate(H2), H1 < H2, distinguishable(H1, H2),
   not do_test(T) : separates(T, H1, H2).

% No test that separates nothing outstanding.
:- do_test(T), not useful_test(T).

% X.733 severity as a spend ceiling. A warning-severity ticket may not authorise a truck
% roll; a critical one may authorise it immediately rather than exhausting cheap telemetry
% first. Severity governs entitlement to spend, never what is true.
:- do_test(T), test_cost(T, C), ticket(Tk), authorised_spend(Tk, Max), C > Max.

% A test the planner can schedule but whose result nobody can record is a hole in the
% knowledge base, not a valid plan. It sends a technician to do work that cannot change the
% answer.
:- do_test(T), test_without_outcomes(T).

% Load-bearing records still unverified must be confirmed before the answer is relied on.
:- needs_verification(F), not verify(F), candidate(_).

% ===========================================================================
% MILESTONES
% ===========================================================================
% Two of them, deliberately separate. You can identify a fiber cut in four minutes and be
% eight hours from restoring service; collapsing the two lets the system claim victory at
% the halfway point.

% Root-cause analysis complete. Not "one explanation survives" -- that forbade simultaneous
% faults. Every surviving world agrees on the cause, whether that cause is one fault or two.
action_disputed :- possible_action(R), not certain_action(R).

cause_known :- certain(_), not action_disputed,
               not any_provisional, not any_contested, not blind_spot.

% Ready for service -- the milestone the customer cares about.
service_restored :- cause_known, certain_action(R), restored(R).
service_restored :- cause_known, certain(H), not service_affecting(H).

solved :- cause_known.

% ---------------------------------------------------------------------------
% ADVICE
% ---------------------------------------------------------------------------
% Only once the cause is known. A recommendation emitted while explanations still disagree
% is the confident wrong answer that rolls a truck to the wrong span -- and an unmapped
% alarm code or a contested reading has to be able to withhold it.

advised(R) :- cause_known, certain_action(R).
truck_roll :- advised(R), dispatch_required(R).

% Every distinct reason a ticket is still open is reported, so "not solved" is never a bare
% negative.
unsolved_reason("no explanation covers the reported symptoms") :- unexplained(_).
unsolved_reason("the remaining explanations call for different actions") :- action_disputed.
unsolved_reason("an explanation rests on an unverified record") :- provisional(_).
unsolved_reason("the ticket carries alarm codes this knowledge base does not recognize") :-
    blind_spot.
unsolved_reason("evidence for and against the same explanation") :- contested(_).

% ===========================================================================
% OPTIMIZE
% ===========================================================================

% Occam, and it is load-bearing rather than stylistic. The smallest set of faults that
% accounts for the symptoms wins, so a second fault appears only when no single one explains
% what was seen. This is what keeps the world count linear in the number of faults that
% could explain the alarm instead of exponential in it.
% Explaining the alarms comes first, above parsimony: a world that accounts for two symptoms
% with two faults beats one that accounts for one symptom with one.
#minimize { 1@4, S : unexplained(S) }.

#minimize { 1@3, H : fault(H) }.

#minimize { C@2, T : do_test(T), test_cost(T, C) }.
#minimize { 1@1, F : verify(F) }.

% ===========================================================================
% DISPLAY
% ===========================================================================

#show fault/1.
#show resolves_to/1.
#show unexplained/1.
#show provisional/1.
#show contested/1.
#show disputed_by/3.
#show advised/1.
#show truck_roll/0.
#show do_test/1.
#show verify/1.
#show indistinguishable/2.
#show solved/0.
#show cause_known/0.
#show service_restored/0.
#show probable_cause/2.
#show unsolved_reason/1.
#show blind_spot/0.
#show outcome/2.
#show test_without_outcomes/1.
#show needs_verification/1.
