# Exceptions and Known Limitations

## Documented Exceptions to Standard QC

Internal test accounts, identified by an `account_id` prefixed with
`test_`, are excluded from standard data-quality review. These accounts
are created by engineering and QA teams for platform testing purposes
and their event histories frequently do not follow normal business
sequencing, since they are generated specifically to exercise edge cases
in the platform rather than to represent real customer behavior. Findings
against `test_`-prefixed accounts should not be reported as genuine data
defects.

## Known Benign Patterns (Not Defects)

A `task.completed` event occurring only minutes after its corresponding
`task.required` event is common and expected for simple checklist-style
tasks, and should not, by itself, be treated as suspicious or flagged for
review. Rapid completion is not evidence of a data-quality problem unless
it also violates an explicit sequencing or timing rule documented
elsewhere.

Similarly, an account with only a single session cycle and no follow-up
or task activity at all is a normal pattern for newly created accounts
and does not indicate missing data.

## Open Timing Questions Not Yet Formalized

Some account managers have asked whether there should be a maximum
allowed interval between a session being booked and that session being
completed — the concern being that sessions booked far in advance and
completed much later might indicate stale bookings. This has been
discussed informally but has not been formalized into a documented
business rule, and no specific threshold has been agreed upon or
approved. Until such a rule is formally adopted and documented, the
interval between `session.booked` and `session.completed` should not be
treated as a governed timing constraint, regardless of how long that
interval is in any particular case.