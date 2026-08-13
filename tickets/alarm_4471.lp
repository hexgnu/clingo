% Ticket 4471 -- loss of signal plus node unreachable on a fielded Samsung router.
%
% The asset facts come from OneVizion, with the confidence and as-of date the record
% carries. Two of them are exactly the kind that go stale: the uplink span (re-groomed
% last quarter, record not updated) and the golden config baseline.

ticket(t4471).
ticket_asset(t4471, rtr_den_042).
asset(rtr_den_042).

symptom(t4471, loss_of_signal).
symptom(t4471, node_unreachable).

today(240).
stale_after(90).
min_confidence(80).

% claim(Source, Fact, Confidence, AsOfDay)
claim(onevizion, site_location_known,  95, 235).   % fresh, high confidence
claim(onevizion, upstream_node_known,  90, 230).   % fresh
claim(onevizion, uplink_span_known,    85, 110).   % 130 days old -> stale
claim(onevizion, golden_config_known,  60, 238).   % fresh but low confidence
