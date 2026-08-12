% Core compliance reasoning. Chapter-independent.
%
% This file encodes the one idea the whole project rests on: under partial observation a
% requirement is not binary. It is satisfied, violated, or *undetermined* -- and it is the
% undetermined set that tells a field tech what to go and capture.
%
% Inputs (supplied by generated rule files, a site file, and observations):
%   applies(Rule, Subject)              this requirement is in force for this thing
%   requires_obs(Rule, Subject, Obs)    settling it needs this observation
%   satisfied(Rule, Subject)            derived by generated rules from obs/3
%   violated(Rule, Subject)             derived by generated rules from obs/3
%   obs(Subject, Obs, Value)            a captured observation; Value is true or false
%   action(A), action_cost(A, C)        an available capture action and its effort
%   action_covers(A, Obs)               observations that action can settle
%   action_target(A, Subject)           the thing that action is performed on

#program base.

% Observations are supplied at solve time and are legitimately absent on a site nobody has
% visited yet -- which is the most important case this system handles. Declaring the
% predicate keeps that from being reported as a modelling mistake.
#defined obs/3.
#defined satisfied/2.
#defined violated/2.
#defined applies/2.
#defined requires_obs/3.
#defined obs_kind/2.

% ---------------------------------------------------------------------------
% Observation bookkeeping
% ---------------------------------------------------------------------------

% An observation counts as captured once it has any recorded value.
captured(X, O) :- obs(X, O, _).

% ---------------------------------------------------------------------------
% The three-valued verdict
% ---------------------------------------------------------------------------

% Undetermined is the default for anything in force that the evidence does not settle.
% Closed-world reasoning would collapse this into "not violated" and report a site clean
% purely because nobody looked at it. That failure mode is the reason this is not Datalog.
undetermined(R, X) :- applies(R, X), not satisfied(R, X), not violated(R, X).

% A missing observation on an undetermined requirement is an evidence gap.
gap(R, X, O) :- undetermined(R, X), requires_obs(R, X, O), not captured(X, O).

% Any observation some action could still produce.
coverable(X, O) :- action_covers(A, O), action_target(A, X), action(A).

% A gap nothing available can close. Surfacing these is the point: the alternative is a
% plan that quietly omits requirements it has no way to settle.
unreachable(R, X, O) :- gap(R, X, O), not coverable(X, O).

% ---------------------------------------------------------------------------
% Evidence plan: choose the cheapest set of actions that closes every reachable gap
% ---------------------------------------------------------------------------

{ do(A) } :- action(A).

covers(A, X, O) :- action_covers(A, O), action_target(A, X), action(A).

% Every closable gap must actually be closed by the chosen plan.
:- gap(R, X, O), coverable(X, O), not do(A) : covers(A, X, O).

% Never schedule an action that closes nothing outstanding -- otherwise the optimum is
% under-constrained and the plan fills up with harmless no-ops.
useful(A) :- covers(A, X, O), gap(_, X, O).
:- do(A), not useful(A).

% One video walk down a battery string settles the same observable for every cell on it.
% Minimizing total cost is what turns a flat list of dozens of checks into a short route,
% and is the capability that motivated using a solver rather than a rules engine.
#minimize { C, A : do(A), action_cost(A, C) }.

% Exactly which requirement, on which subject, each chosen action settles. Derived here
% rather than reconstructed afterwards, so the manifest's claims about what an action
% discharges are the solver's own and cannot drift from the logic that chose it.
closes(A, R, X, O) :- do(A), covers(A, X, O), gap(R, X, O).

#show do/1.
#show action_cost/2.
#show closes/4.
#show gap/3.
#show unreachable/3.
#show violated/2.
#show satisfied/2.
#show undetermined/2.
