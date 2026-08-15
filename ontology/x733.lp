% ITU-T X.733 alarm semantics, and what they are allowed to authorise.
%
% Samsung's NMS already emits X.733-shaped alarms, and the ticket model already parses
% perceived severity -- then throws it away. So a `warning` and a `critical` produce an
% identical plan today, which is wrong in the direction that costs money: it will either
% dispatch a truck for a warning or refuse to dispatch one for an outage.
%
% Severity does not change *what is true*. It changes **what you are entitled to spend
% finding out**. That is the whole of its job here, and keeping it to that stops it leaking
% into the diagnosis, where it has no business -- a critical alarm does not make a fibre cut
% more likely, it only makes waiting to find out more expensive.

#program base.

#defined alarm_severity/2.
#defined raw_alarm/2.
#defined ticket/1.

% ---------------------------------------------------------------------------
% X.733 perceived severity
% ---------------------------------------------------------------------------

severity_rank(cleared,       0).
severity_rank(indeterminate, 1).
severity_rank(warning,       2).
severity_rank(minor,         3).
severity_rank(major,         4).
severity_rank(critical,      5).

% An alarm with no severity stated is `indeterminate` -- X.733's own default, and the
% honest one. It is not "fine".
%
% Kept in a separate predicate from the supplied `alarm_severity/2`. Defaulting into the
% same predicate reads naturally and is unstratified: alarm_severity would depend on
% `not stated_severity`, which depends on alarm_severity. That cycle silently emptied the
% plan rather than erroring.
severity_of(C, S) :- alarm_severity(C, S).
severity_of(C, indeterminate) :- raw_alarm(_, C), not alarm_severity(C, _).

% A ticket takes the severity of its worst live alarm. Anything else lets a stray warning
% dilute an outage.
ticket_severity(T, S) :- ticket(T), severity_rank(S, R),
                         R = #max { K : raw_alarm(_, C), severity_of(C, Sev),
                                        severity_rank(Sev, K) }.

% ---------------------------------------------------------------------------
% What each severity authorises
% ---------------------------------------------------------------------------
% A ceiling on what a single probe may cost. Critical buys an immediate truck; a warning
% buys remote telemetry and nothing else. These numbers are as invented as the rest of the
% cost model -- what is defensible is the *ordering*, and that a warning can never
% authorise a dispatch.

probe_ceiling(critical,      50).
probe_ceiling(major,         10).
probe_ceiling(minor,          3).
probe_ceiling(warning,        2).
probe_ceiling(indeterminate,  2).
probe_ceiling(cleared,        0).

authorised_spend(T, C) :- ticket_severity(T, S), probe_ceiling(S, C).

#show severity_of/2.
#show ticket_severity/2.
#show authorised_spend/2.
