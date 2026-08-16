% Datacenter HVAC compliance site file
% Based on HVAC CITS 115 standard

% Site identity
site(datacenter01).

% HVAC equipment inventory
hvac_vent(intake_vent_a).
hvac_vent(return_vent_a).
hvac_vent(exhaust_vent_b).
hvac_controller(hvac_ctrl_main).
hvac_controller(hvac_ctrl_backup).

% Multiple units for testing clearance rules
hvac_unit(crac_01).
hvac_unit(crac_02).
