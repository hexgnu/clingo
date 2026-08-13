% What can go wrong with a fielded Samsung router, and how to tell the cases apart.
%
% Declarative and asset-agnostic: nothing here names a particular router or site. This is
% the equivalent of a compiled chapter on the compliance side -- the reusable knowledge a
% ticket is reasoned against.

#program base.

% ---------------------------------------------------------------------------
% Explanations, and the symptoms each would produce
% ---------------------------------------------------------------------------

hypothesis(fiber_cut).
hypothesis(upstream_outage).
hypothesis(site_power_loss).
hypothesis(optic_degraded).
hypothesis(config_drift).
hypothesis(hardware_fault).
hypothesis(backhaul_congestion).

explains(fiber_cut,          loss_of_signal).
explains(fiber_cut,          node_unreachable).
explains(upstream_outage,    loss_of_signal).
explains(upstream_outage,    node_unreachable).
explains(site_power_loss,    node_unreachable).
explains(site_power_loss,    no_heartbeat).
explains(optic_degraded,     loss_of_signal).
explains(optic_degraded,     errored_seconds).
explains(config_drift,       node_unreachable).
explains(config_drift,       routing_flap).
explains(hardware_fault,     node_unreachable).
explains(hardware_fault,     errored_seconds).
explains(hardware_fault,     no_heartbeat).
explains(backhaul_congestion, errored_seconds).
explains(backhaul_congestion, routing_flap).

% ---------------------------------------------------------------------------
% What each explanation assumes about the record
% ---------------------------------------------------------------------------
% Blaming a fiber span only makes sense if the record correctly says which span feeds this
% router. Blaming site power assumes the record has the right site. When those rows are
% stale, the diagnosis is provisional however clean the test results look.

requires_fact(fiber_cut,       uplink_span_known).
requires_fact(upstream_outage, upstream_node_known).
requires_fact(site_power_loss, site_location_known).
requires_fact(config_drift,    golden_config_known).

% ---------------------------------------------------------------------------
% Tests, ordered by what they cost to run
% ---------------------------------------------------------------------------
% Remote telemetry is nearly free. A technician in a truck is not, and the gap between
% them is the whole point of planning before dispatching.

test(ping_node).            test_cost(ping_node, 1).
test(read_optical_power).   test_cost(read_optical_power, 1).
test(check_upstream_alarms). test_cost(check_upstream_alarms, 1).
test(query_power_telemetry). test_cost(query_power_telemetry, 1).
test(diff_running_config).  test_cost(diff_running_config, 2).
test(read_error_counters).  test_cost(read_error_counters, 1).
test(otdr_trace).           test_cost(otdr_trace, 8).
test(site_visit).           test_cost(site_visit, 40).

% observes(Test, Hypothesis): this test responds to that explanation. A test that responds
% to two candidates cannot tell them apart, which is what the planner exploits.
observes(read_optical_power,   fiber_cut).
observes(read_optical_power,   optic_degraded).
observes(otdr_trace,           fiber_cut).
observes(check_upstream_alarms, upstream_outage).
observes(query_power_telemetry, site_power_loss).
observes(diff_running_config,  config_drift).
observes(read_error_counters,  optic_degraded).
observes(read_error_counters,  hardware_fault).
observes(read_error_counters,  backhaul_congestion).
observes(ping_node,            config_drift).
observes(ping_node,            hardware_fault).
observes(site_visit,           hardware_fault).
observes(site_visit,           site_power_loss).
observes(site_visit,           fiber_cut).

% ---------------------------------------------------------------------------
% How results move the diagnosis
% ---------------------------------------------------------------------------

rules_out(read_optical_power, nominal,   fiber_cut).
rules_out(read_optical_power, nominal,   optic_degraded).
confirms(read_optical_power,  no_light,  fiber_cut).
rules_out(read_optical_power, no_light,  optic_degraded).
confirms(read_optical_power,  low,       optic_degraded).
rules_out(read_optical_power, low,       fiber_cut).

rules_out(check_upstream_alarms, none,   upstream_outage).
confirms(check_upstream_alarms,  active, upstream_outage).

rules_out(query_power_telemetry, ac_present, site_power_loss).
confirms(query_power_telemetry,  ac_absent,  site_power_loss).

rules_out(diff_running_config, matches_golden, config_drift).
confirms(diff_running_config,  differs,        config_drift).

rules_out(read_error_counters, clean,      hardware_fault).
rules_out(read_error_counters, clean,      backhaul_congestion).
confirms(read_error_counters,  crc_errors, hardware_fault).
confirms(read_error_counters,  congestion, backhaul_congestion).

confirms(otdr_trace, break_at_distance, fiber_cut).
rules_out(otdr_trace, continuous,       fiber_cut).

% ---------------------------------------------------------------------------
% What to do about it
% ---------------------------------------------------------------------------

resolution(fiber_cut,           dispatch_splice_crew).
resolution(optic_degraded,      dispatch_optic_replacement).
resolution(hardware_fault,      dispatch_rma_swap).
resolution(site_power_loss,     dispatch_power_restoration).
resolution(config_drift,        push_golden_config).
resolution(upstream_outage,     escalate_to_transport).
resolution(backhaul_congestion, escalate_to_capacity_planning).

dispatch_required(dispatch_splice_crew).
dispatch_required(dispatch_optic_replacement).
dispatch_required(dispatch_rma_swap).
dispatch_required(dispatch_power_restoration).
