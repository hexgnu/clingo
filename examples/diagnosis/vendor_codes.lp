% Vendor alarm codes -> the symptom vocabulary the knowledge base reasons in.
%
% Data, not code. Adding a new alarm type from a new NMS is a line here, and an alarm code
% nobody has mapped yet is caught by the reasoner rather than being quietly ignored.

#program base.

#defined raw_alarm/2.

% maps_to(Source, VendorCode, Symptom)
maps_to(samsung_nms, "LOS-A1",        loss_of_signal).
maps_to(samsung_nms, "LOS-A2",        loss_of_signal).
maps_to(samsung_nms, "NODE-UNREACH",  node_unreachable).
maps_to(samsung_nms, "HB-MISS",       no_heartbeat).
maps_to(samsung_nms, "ES-THRESH",     errored_seconds).
maps_to(samsung_nms, "RT-FLAP",       routing_flap).
maps_to(samsung_nms, "OPT-LOW",       loss_of_signal).

maps_to(netcool, "LinkDown",          node_unreachable).
maps_to(netcool, "SignalLoss",        loss_of_signal).

% Datacenter / facility alarms
maps_to(samsung_nms, "AC-INPUT-FAIL", ac_input_fail).
maps_to(samsung_nms, "BATTERY-MODE",  battery_mode).
maps_to(samsung_nms, "TEMP-HIGH",     high_temperature).
maps_to(samsung_nms, "PHYSICAL-ALARM", physical_alarm).

% A code nobody has mapped. Reported, never dropped: an unrecognized alarm means the
% ticket carries information the knowledge base cannot use, and a diagnosis reached
% without it is not trustworthy however tidy it looks.
unmapped_code(Src, Code) :- raw_alarm(Src, Code), not maps_to(Src, Code, _).

#show unmapped_code/2.
