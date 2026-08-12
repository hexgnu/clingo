% A power-plant site exercising Chapter H: cable racks, power cables, bays and circuits.
%
% Deliberately shaped to test things den01 cannot: a group that is not a battery string,
% conductor gauges that select different thresholds from the same clause, and obligations
% that need an instrument rather than a camera.

site(den02).

% -- Battery plant (so both chapters can be run together) --------------------
battery_string(bs1).
cell(bs1, 1..12).
fuse_panel(fp1).
fuse_record_book(frb1).

% -- Cable racks -------------------------------------------------------------
cable_rack(rk1).
cable_rack(rk2).

% -- Power cables ------------------------------------------------------------
% rk1 carries eight cables, which is what makes a sweep worth choosing over eight visits.
power_cable(pc1). on_rack(pc1, rk1).
power_cable(pc2). on_rack(pc2, rk1).
power_cable(pc3). on_rack(pc3, rk1).
power_cable(pc4). on_rack(pc4, rk1).
power_cable(pc5). on_rack(pc5, rk1).
power_cable(pc6). on_rack(pc6, rk1).
power_cable(pc7). on_rack(pc7, rk1).
power_cable(pc8). on_rack(pc8, rk1).
power_cable(pc9). on_rack(pc9, rk2).

% Cables leaving the rack are subject to the unsupported-span limit, and which limit
% applies depends on gauge -- H.10.7a for 1/0 and smaller, H.10.7b for 2/0 and larger.
leaves_rack(pc1).  gauge_1_0_or_smaller(pc1).
leaves_rack(pc2).  gauge_1_0_or_smaller(pc2).
leaves_rack(pc3).  gauge_2_0_or_larger(pc3).
leaves_rack(pc9).  gauge_2_0_or_larger(pc9).

has_exposed_end(pc8).

% -- Bays and circuits -------------------------------------------------------
power_bay(rect1).
power_bay(pdb1).
distribution_circuit(dc1). distribution_circuit(dc2).
distribution_circuit(dc3). distribution_circuit(dc4).
