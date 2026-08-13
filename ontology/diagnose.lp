% Ticket resolution: unsolved world -> solved world.
%
% The compliance side asks "which obligations are undischarged?" and plans a minimum cover.
% A ticket asks a different question -- "which of the competing explanations is true?" --
% and the right plan is the cheapest set of tests that tells them apart. Same solver, same
% three-valued honesty, different objective.
%
% A ticket is SOLVED when exactly one candidate explanation survives and every fact that
% explanation rests on is established. Anything less is reported as still open, with the
% specific reason, rather than as a best guess.

#program base.

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
#defined observes/2.
#defined rules_out/3.
#defined confirms/3.
#defined test_result/2.
#defined requires_fact/2.
#defined resolution/2.
#defined dispatch_required/1.

% ---------------------------------------------------------------------------
% Symptoms, translated from whatever the originating system called them
% ---------------------------------------------------------------------------

symptom(T, S) :- ticket(T), raw_alarm(Src, Code), maps_to(Src, Code, S).

% An alarm the knowledge base cannot interpret is not a neutral event. The ticket is
% carrying evidence that the reasoner is blind to, so no answer derived without it can be
% called complete.
blind_spot :- unmapped_code(_, _).

% ---------------------------------------------------------------------------
% Candidate explanations
% ---------------------------------------------------------------------------

% Anything that would explain a symptom this ticket actually reported.
candidate(H) :- hypothesis(H), symptom(T, S), explains(H, S), ticket(T), not eliminated(H).

eliminated(H) :- test_result(Test, Value), rules_out(Test, Value, H).

confirmed(H) :- test_result(Test, Value), confirms(Test, Value, H).

% ---------------------------------------------------------------------------
% Facts a diagnosis leans on
% ---------------------------------------------------------------------------
% If blaming a fiber span depends on a OneVizion row saying this router is fed by that
% span, then that row is load-bearing and its reliability is part of the diagnosis.

load_bearing(F) :- candidate(H), requires_fact(H, F).

% A hypothesis resting on a refuted fact is not a live explanation.
eliminated(H) :- requires_fact(H, F), refuted(F).

% One that rests on an unverified fact can still be true, but cannot be concluded. This is
% the distinction that keeps a stale record from being laundered into a confident answer.
provisional(H) :- candidate(H), requires_fact(H, F), unverified(F).

% ---------------------------------------------------------------------------
% Is the ticket solved?
% ---------------------------------------------------------------------------

open_candidates(N) :- N = #count { H : candidate(H) }.

solved :- open_candidates(1), candidate(H), not provisional(H), not blind_spot.

% Every distinct reason a ticket is still open is reported, so "not solved" is never a
% bare negative.
unsolved_reason("no explanation covers the reported symptoms") :- open_candidates(0).
unsolved_reason("several explanations remain") :- open_candidates(N), N > 1.
unsolved_reason("the only explanation rests on an unverified record") :-
    open_candidates(1), candidate(H), provisional(H).
unsolved_reason("the ticket carries alarm codes this knowledge base does not recognize") :-
    blind_spot.

% ---------------------------------------------------------------------------
% Planning the next work: a minimum discriminating test set
% ---------------------------------------------------------------------------
% Not a cover. Two candidates must be told APART, so a test is useful exactly when it
% responds differently to them.

{ do_test(T) } :- test(T), not test_result(T, _).

separates(T, H1, H2) :- test(T), candidate(H1), candidate(H2), H1 < H2,
                        observes(T, H1), not observes(T, H2).
separates(T, H1, H2) :- test(T), candidate(H1), candidate(H2), H1 < H2,
                        observes(T, H2), not observes(T, H1).

distinguishable(H1, H2) :- separates(T, H1, H2), test(T).

% Any pair no available test can separate is surfaced rather than silently tolerated --
% it means the diagnosis cannot be completed with the tests on hand, which is a dispatch
% decision, not a reasoning failure.
indistinguishable(H1, H2) :- candidate(H1), candidate(H2), H1 < H2,
                             not distinguishable(H1, H2).

% Every separable pair must actually be separated by the chosen plan.
:- candidate(H1), candidate(H2), H1 < H2, distinguishable(H1, H2),
   not do_test(T) : separates(T, H1, H2).

% Load-bearing records that are still unverified have to be confirmed before the answer
% can be relied on.
{ verify(F) } :- needs_verification(F).
:- needs_verification(F), not verify(F).

% No test that separates nothing outstanding.
useful_test(T) :- do_test(T), separates(T, _, _).
:- do_test(T), not useful_test(T).

#minimize { C, T : do_test(T), test_cost(T, C) }.
#minimize { 1, F : verify(F) }.

% ---------------------------------------------------------------------------
% Resolution
% ---------------------------------------------------------------------------

recommended(R) :- solved, candidate(H), confirmed(H), resolution(H, R).
recommended(R) :- solved, candidate(H), resolution(H, R), not confirmed(H).

truck_roll :- recommended(R), dispatch_required(R).

#show candidate/1.
#show provisional/1.
#show eliminated/1.
#show confirmed/1.
#show do_test/1.
#show verify/1.
#show indistinguishable/2.
#show solved/0.
#show unsolved_reason/1.
#show recommended/1.
#show truck_roll/0.
#show blind_spot/0.
