% Example site: one 24-cell battery string, two fuse panels, a handful of leads.
%
% Facts describe what is *installed*, never what has been *observed*. Keeping the two
% apart is what allows the same site file to be reasoned over before any evidence exists
% (producing a capture plan) and again afterwards (producing a verdict).

site(den01).

% -- Battery plant -----------------------------------------------------------
battery_string(bs1).
cell(bs1, 1..24).

% -- Fuse panels -------------------------------------------------------------
fuse_panel(fp1).
fuse_panel(fp2).
misc_bay_mounted(fp2).
% fp2 has no other means of fuse identification, so D.6.3 is in force for it.

fuse_record_book(frb1).

% -- Conductors --------------------------------------------------------------
lead(l1).  battery_lead(l1).  terminates_at(l1, return_bus_bar).
lead(l2).  battery_lead(l2).  terminates_at(l2, rectifier).
lead(l3).  battery_lead(l3).  internal_to_rack(l3).   % exempt per D.6.8
lead(l4).  ground_cable(l4).  terminates_at(l4, office_ground_bar).
lead(l5).  ground_cable(l5).  short_visible_run(l5).  % exempt per D.6.9
