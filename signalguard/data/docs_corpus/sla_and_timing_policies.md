# Service Level Agreement (SLA) and Timing Policies

## Overview

This document covers time-bound service commitments related to
engagement events. These are business rules with a specific numeric
threshold attached, as opposed to the purely sequential rules described
in the event lifecycle document.

## Follow-Up Response Window After a Missed Session

When a customer fails to show for a booked session, the account team is
required to initiate a follow-up within seven (7) days of the recorded
no-show. This is tracked in the event stream as a `followup.required`
event whose timestamp falls within seven days of the corresponding
`session.no_show` event for that account.

A follow-up that is required more than seven days after the triggering
no-show is out of policy and represents an SLA breach. This window is
measured from the no-show event itself, not from any earlier event in
the session's lifecycle (such as the original booking).

This policy applies specifically to no-show outcomes. It does not extend
the follow-up requirement to sessions that were completed normally, nor
does it define any SLA for how quickly a required follow-up must itself
be completed once opened.

## Session Reminder Timing

As a courtesy, the scheduling system sends an automated reminder to
customers approximately 24 hours before a booked session. Reminder
delivery is handled by the notifications subsystem and is not currently
represented as a distinct event type in the engagement event stream
covered by this documentation. Questions about reminder delivery
reliability should be directed to the notifications team rather than
treated as an engagement-event data-quality matter.

## Support Ticket Escalation Windows

Support tickets that remain unresolved for more than 48 hours are
automatically escalated to a senior support agent. This escalation
workflow operates on the support ticketing system and its associated
event types, which are outside the scope of the account, session, task,
and follow-up event stream documented here. Escalation timing should not
be conflated with the follow-up response window described above; the two
are governed by entirely separate teams and separate systems.