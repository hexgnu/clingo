% Datacenter and facility fault diagnosis.
%
% What can go wrong at a colocation site that takes out multiple devices simultaneously,
% and how to tell the causes apart with minimal site access.

#program base.

% ---------------------------------------------------------------------------
% Hypotheses — what could cause a multi-device outage
% ---------------------------------------------------------------------------

hypothesis(utility_power_outage).
hypothesis(ups_battery_depleted).
hypothesis(hvac_failure_thermal).
hypothesis(upstream_aggregation_down).
hypothesis(fiber_bundle_cut).
hypothesis(facility_network_fault).
hypothesis(physical_access_incident).

% ---------------------------------------------------------------------------
% Symptoms each hypothesis would produce
% ---------------------------------------------------------------------------

explains(utility_power_outage,      ac_input_fail).
explains(utility_power_outage,      battery_mode).
explains(utility_power_outage,      node_unreachable).

explains(ups_battery_depleted,      battery_mode).
explains(ups_battery_depleted,      node_unreachable).

explains(hvac_failure_thermal,      node_unreachable).
explains(hvac_failure_thermal,      high_temperature).

explains(upstream_aggregation_down, node_unreachable).

explains(fiber_bundle_cut,          loss_of_signal).
explains(fiber_bundle_cut,          node_unreachable).

explains(facility_network_fault,    node_unreachable).

explains(physical_access_incident,  node_unreachable).
explains(physical_access_incident,  physical_alarm).

% ---------------------------------------------------------------------------
% Record dependencies
% ---------------------------------------------------------------------------

requires_fact(utility_power_outage,      utility_power_stable).
requires_fact(ups_battery_depleted,      site_has_generator).
requires_fact(upstream_aggregation_down, upstream_agg_known).
requires_fact(hvac_failure_thermal,      hvac_operational).

% ---------------------------------------------------------------------------
% Diagnostic tests
% ---------------------------------------------------------------------------

test(query_power_telemetry).     test_cost(query_power_telemetry, 1).
test(check_ups_battery_level).   test_cost(check_ups_battery_level, 1).
test(read_temperature_sensors).  test_cost(read_temperature_sensors, 1).
test(check_upstream_alarms).     test_cost(check_upstream_alarms, 1).
test(read_optical_power).        test_cost(read_optical_power, 2).
test(review_access_logs).        test_cost(review_access_logs, 2).
test(check_hvac_status).         test_cost(check_hvac_status, 2).
test(site_visit).                test_cost(site_visit, 40).

% ---------------------------------------------------------------------------
% Test outcomes and what they tell us
% ---------------------------------------------------------------------------

% Power telemetry
rules_out(query_power_telemetry, ac_present, utility_power_outage).
confirms(query_power_telemetry,  ac_absent,  utility_power_outage).

% UPS battery
rules_out(check_ups_battery_level, charging,    ups_battery_depleted).
rules_out(check_ups_battery_level, full,        ups_battery_depleted).
confirms(check_ups_battery_level,  critical,    ups_battery_depleted).
confirms(check_ups_battery_level,  discharging, utility_power_outage).

% Temperature
rules_out(read_temperature_sensors, nominal,      hvac_failure_thermal).
confirms(read_temperature_sensors,  over_threshold, hvac_failure_thermal).

% Upstream status
rules_out(check_upstream_alarms, none,   upstream_aggregation_down).
confirms(check_upstream_alarms,  active, upstream_aggregation_down).

% Optical power
rules_out(read_optical_power, nominal, fiber_bundle_cut).
confirms(read_optical_power,  no_light, fiber_bundle_cut).

% HVAC
rules_out(check_hvac_status, operational, hvac_failure_thermal).
confirms(check_hvac_status,  failed,      hvac_failure_thermal).

% Physical access
rules_out(review_access_logs, no_recent_entry, physical_access_incident).
confirms(review_access_logs,  unauthorized,    physical_access_incident).

% Site visit confirms anything that requires physical presence
confirms(site_visit, visual_confirmation, utility_power_outage).
confirms(site_visit, visual_confirmation, hvac_failure_thermal).
confirms(site_visit, visual_confirmation, physical_access_incident).
