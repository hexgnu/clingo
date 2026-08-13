% Battery closeout: two 24-cell strings and their feeder leads.
%
% The shape of a real acceptance walk after a battery install -- what an inspector is
% actually handed when a vendor says the plant is ready to sign off.

site(den03).

battery_string(bsA).
cell(bsA, 1..24).

battery_string(bsB).
cell(bsB, 1..24).

% Feeder and return leads. l5 is internal to the relay rack, so D.6.8 exempts it from
% 145C tagging -- an inspector should never be sent to photograph a tag that is not
% required.
lead(l1). battery_lead(l1). terminates_at(l1, return_bus_bar).
lead(l2). battery_lead(l2). terminates_at(l2, return_bus_bar).
lead(l3). battery_lead(l3). terminates_at(l3, rectifier).
lead(l4). battery_lead(l4). terminates_at(l4, rectifier).
lead(l5). battery_lead(l5). internal_to_rack(l5).
