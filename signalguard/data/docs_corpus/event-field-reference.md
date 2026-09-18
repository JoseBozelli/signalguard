# Event Field Reference

## Event Identifiers and Correlation

Every event carries an `account_id` identifying the account it belongs
to, and an `event_type` describing what happened. Most event types also
carry a `ref_id`, which identifies the specific lifecycle instance the
event is part of — for example, a particular session, a particular task,
or a particular follow-up. Two events with the same `ref_id` and
compatible event types (such as a booking and its outcome) refer to the
same underlying instance and should be evaluated together when checking
sequencing rules.

A small number of event types also carry a `related_ref_id`, which
references a *different* lifecycle instance than the one the event
itself belongs to. This field exists specifically to support
cross-lifecycle rules, such as linking a follow-up back to the session
that triggered it. `related_ref_id` should not be confused with `ref_id`
— the former points to another entity's lifecycle, the latter identifies
the event's own lifecycle.

## Supported Event Types

The engagement event stream currently supports the following event
types: `account.created`, `session.booked`, `session.completed`,
`session.no_show`, `task.required`, `task.completed`,
`followup.required`, and `followup.completed`. Any event type outside
this list should be treated as unrecognized and flagged, since it likely
indicates either an upstream schema change that has not yet been
documented, or a data corruption issue.

## Required Fields and Missing-Data Handling

Every event must carry a non-null `account_id`. An event with a missing
or null `account_id` cannot be attributed to any account and should be
treated as a data-quality defect rather than silently dropped or
attributed to a default account.

Fields that are legitimately optional (such as `ref_id` on an
`account.created` event, which has no lifecycle instance to correlate
against) should be recorded as null rather than omitted from the record
entirely, so that their absence is distinguishable from a data pipeline
error that failed to populate the field.

## Deprecated Field Names

Older versions of the event schema used the field name `customer_id`
instead of `account_id`, and used a single combined `entity_ref` field
instead of the current split between `ref_id` and `related_ref_id`. Any
archived data still using these legacy field names should be migrated
before being loaded into current analysis pipelines; this document does
not cover the migration procedure itself.