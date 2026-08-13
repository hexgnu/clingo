% What can produce evidence, and how far each is trusted.
%
% Configuration, not code. Adding a Samsung debug app or retiring a vision model is a line
% here.

#program base.

% Tier 1 automated, tier 2 assisted, tier 3 a person on site. The tiers exist so escalation
% has a direction: a marginal automated read goes to a person, never the other way.
source_tier(cv_label_reader,   1).
source_tier(cv_routing_check,  1).
source_tier(samsung_diag_app,  1).
source_tier(technician,        3).

% can_observe(Source, Observable): what each source is actually competent at. A vision
% model that reads printed characters well has no business judging torque, and saying so
% here is what stops the planner from sending it.
can_observe(cv_label_reader, cell_number_legible).
can_observe(cv_label_reader, cell_polarity_symbol_visible).
can_observe(cv_label_reader, tr_cell_marked).
can_observe(cv_label_reader, battery_group_marked).
can_observe(cv_label_reader, install_date_marked).
can_observe(cv_label_reader, spec_number_marked).
can_observe(cv_label_reader, circuit_labelled).
can_observe(cv_label_reader, do_not_disconnect_tag_present).

can_observe(cv_routing_check, cable_flows_over_rack_edge).
can_observe(cv_routing_check, ac_dc_not_shared).

% A technician can observe anything. That is what makes them the escalation target and
% also why they are the expensive one.
can_observe(technician, O) :- obs_kind(O, _).

% ---------------------------------------------------------------------------
% How sure a machine has to be
% ---------------------------------------------------------------------------

default_confidence(80).

% Reading a printed number off a clean cell face is something a model does well, so the bar
% can sit at the default. Judging a spatial relationship from a photo is harder and the
% consequences of getting it wrong are physical, so it is set higher.
confidence_required(cable_flows_over_rack_edge, 95).
confidence_required(ac_dc_not_shared,           95).

% Ordering matters here and a model cannot see electrical position, only printed digits.
% Effectively this forces a human, which is the correct answer rather than a limitation.
confidence_required(numbering_starts_at_positive_end, 99).
