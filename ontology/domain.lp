% Site vocabulary and capture-action generation.
%
% Hand-written and stable. Generated rule files reference these predicates but never
% redefine them, so re-running extraction against a new revision of the source document
% cannot disturb the domain model.

#program base.

% Site vocabulary a given site file may legitimately omit. A site with no miscellaneous
% bay-mounted panels simply never states `misc_bay_mounted`, and the requirements guarded
% on it correctly never apply.
#defined battery_string/1.
#defined cell/2.
#defined fuse_panel/1.
#defined fuse_record_book/1.
#defined relay_rack/1.
#defined lead/1.
#defined battery_lead/1.
#defined ground_cable/1.
#defined terminates_at/2.
#defined internal_to_rack/1.
#defined short_visible_run/1.
#defined misc_bay_mounted/1.
#defined other_fuse_identification/1.

% ---------------------------------------------------------------------------
% Site vocabulary
% ---------------------------------------------------------------------------
% Supplied by a site file:
%   battery_string(S)          a string of cells
%   cell(S, C)                 cell C belongs to string S
%   fuse_panel(P)              a fuse panel
%   relay_rack(R)              a relay rack / bay
%   lead(L)                    a power or ground conductor
%   terminates_at(L, X)        lead L lands on X
%   internal_to(L, R)          lead L runs entirely inside rack R
%   group(G) / member(G, X)    a set of things one capture pass can sweep

% Every cell is a subject in its own right, and belongs to its string's group.
subject(cell(S, C)) :- cell(S, C).
subject(S) :- battery_string(S).
subject(P) :- fuse_panel(P).
subject(L) :- lead(L).

% Chapter H vocabulary. Added as declarations, not code.
#defined cable_rack/1.
#defined power_cable/1.
#defined on_rack/2.
#defined leaves_rack/1.
#defined has_exposed_end/1.
#defined gauge_1_0_or_smaller/1.
#defined gauge_2_0_or_larger/1.
#defined power_bay/1.
#defined distribution_circuit/1.

subject(R) :- cable_rack(R).
subject(C) :- power_cable(C).
subject(B) :- power_bay(B).
subject(X) :- distribution_circuit(X).

% ---------------------------------------------------------------------------
% Sweep groups
% ---------------------------------------------------------------------------
% A group is any set of subjects one physical pass can observe together. Nothing about
% the notion is specific to batteries -- it just needs a container and its members.

% A battery string: one pass down the row sees every cell face.
group(S) :- battery_string(S).
member(S, cell(S, C)) :- cell(S, C).

% A cable rack: one pass along the rack sees every cable on it. Declared exactly like the
% battery string above, which is the test of whether the sweep machinery was general or
% just fitted to the first case.
group(R) :- cable_rack(R).
member(R, C) :- on_rack(C, R).

% ---------------------------------------------------------------------------
% Capture actions
% ---------------------------------------------------------------------------
% Actions are derived, not enumerated by hand. Two competing ways to obtain any given
% observation are always offered, and the optimizer in core.lp decides which is cheaper
% for the site actually in front of it.

% Only things you look at can be bundled into one pass. A meter reading or a torque check
% happens per subject however they are grouped, so those never bundle.
bundleable(O) :- obs_kind(O, photo).
bundleable(O) :- obs_kind(O, video).

% Three tiers of increasing reach and cost. The optimizer in core.lp picks whichever
% combination is cheapest for the site actually in front of it -- so the same rules give a
% different plan for a 2-cell string than for a 24-cell one, with nothing tuned by hand.

% (1) One observation, one subject. The fallback that always exists.
action(capture(X, O)) :- requires_obs(_, X, O).
action_cost(capture(X, O), 5) :- action(capture(X, O)).
action_covers(capture(X, O), O) :- action(capture(X, O)).
action_target(capture(X, O), X) :- action(capture(X, O)).
action_kind(capture(X, O), K) :- action(capture(X, O)), obs_kind(O, K).

% (2) One framing of a single subject, establishing every marking of that kind at once.
% Barely more expensive than a single shot, so it wins as soon as a subject carries two
% or more markings -- which is why a fuse panel gets photographed once, not twice.
action(survey(X, K)) :- requires_obs(_, X, O), obs_kind(O, K), bundleable(O).
action_cost(survey(X, K), 6) :- action(survey(X, K)).
action_covers(survey(X, K), O) :- action(survey(X, K)), obs_kind(O, K), requires_obs(_, X, O).
action_target(survey(X, K), X) :- action(survey(X, K)).
action_kind(survey(X, K), K) :- action(survey(X, K)).

% (3) One pass over a whole group, settling every marking of that kind for every member.
% Costs twice a single shot and replaces dozens: one walk down a battery string sees all
% 24 cell faces. This is the tier that makes an inspection tractable.
action(sweep(G, K)) :- group(G), member(G, X), requires_obs(_, X, O), obs_kind(O, K), bundleable(O).
action_cost(sweep(G, K), 10) :- action(sweep(G, K)).
action_covers(sweep(G, K), O) :- action(sweep(G, K)), obs_kind(O, K),
                                 member(G, X), requires_obs(_, X, O).
action_target(sweep(G, K), X) :- action(sweep(G, K)), member(G, X).
action_kind(sweep(G, K), K) :- action(sweep(G, K)).

#show action_kind/2.
