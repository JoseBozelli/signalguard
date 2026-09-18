# Event Lifecycle Rules

## Overview

This document describes the expected lifecycle of the core engagement
events tracked in the platform: sessions, tasks, and follow-ups. Each of
these entities moves through a small number of states, and the event
stream should reflect that progression consistently. This document is
intended for engineering and data-quality teams validating event data
integrity.

## Session Booking and Completion

Every session outcome event — whether the session was completed or the
customer failed to show — must be preceded by a corresponding booking
event for that same session. A session cannot be marked completed, nor
can it be marked as a no-show, unless it was first booked. In practice
this means: for any given session identifier, a `session.booked` event
must exist with a timestamp earlier than the corresponding outcome event.

If an outcome event exists without a matching prior booking event for
the same session identifier, this indicates either a backfill error, a
missing upstream event, or a genuine data integrity problem, and should
be treated as a data-quality finding rather than a normal business
scenario.

## Task Completion Requirements

Tasks follow a simple two-state lifecycle: a task is marked as required,
and it is later marked as completed. A task cannot be completed before
it has been marked as required — the `task.required` event for a given
task must always carry an earlier timestamp than the corresponding
`task.completed` event for that same task.

This ordering constraint holds regardless of how quickly the task is
completed after being required; a task completed minutes after being
required is normal and expected, so long as the required event precedes
the completed event.

## Follow-Up Completion Requirements

Follow-ups are generated in response to certain account events (see the
follow-up response window policy for the specific triggering conditions)
and, like tasks, move through a required-then-completed lifecycle. A
`followup.completed` event must always be preceded by a `followup.required`
event for the same follow-up identifier — a completion recorded without a
corresponding required event, or with a completed timestamp earlier than
the required timestamp, indicates the follow-up lifecycle was not
respected and should be flagged for review.

Not every required follow-up is necessarily completed by the time a given
data extract is taken; an outstanding follow-up with no completion event
yet is not by itself a data-quality issue.

## Account Provisioning Notes

Account records are provisioned through several intake channels,
including self-service signup, sales-assisted onboarding, and bulk
migration from legacy systems. Regardless of intake channel, every
account is represented by a single `account.created` event marking the
start of that account's history. Provisioning metadata (intake channel,
originating campaign, referral source) is tracked internally by the
account management system but is not part of the event stream described
in this document.