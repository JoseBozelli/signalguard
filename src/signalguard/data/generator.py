"""
Clean synthetic event-stream generator for SignalGuard.

Produces a baseline dataset where every account's event history satisfies
the five locked documented rules by construction:

  R1  session.completed / session.no_show requires a preceding
      session.booked with the same ref_id (session_id)
  R2  task.completed cannot precede task.required (same ref_id / task_id)
  R3  followup.completed requires a preceding followup.required
      with the same ref_id (followup_id)
  R4  followup.completed cannot precede followup.required
  R5  when a session.no_show occurs, a followup.required (linked via
      related_ref_id) must occur within 7 days

This is the *clean* baseline only. Defect injection (Tier 1 / Tier 2) is a
separate module that corrupts a copy of this output — it is not part of
this generator, so this file stays a single-responsibility unit.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import List

from signalguard.schemas.event import Event, EventType

# Locked benchmark parameter: followup.required must land within this many
# days of the triggering session.no_show (R5). The generator always
# schedules within [1, FOLLOWUP_SLA_DAYS] so clean data never grazes the
# boundary ambiguously.
FOLLOWUP_SLA_DAYS = 7


def _new_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:05d}"


def generate_clean_dataset(
    num_accounts: int = 80,
    seed: int = 42,
    session_no_show_rate: float = 0.25,
    followup_completion_rate: float = 0.7,
    base_date: datetime = datetime(2026, 1, 1),
) -> List[Event]:
    """Generate a clean, rule-compliant synthetic event dataset.

    Returns a flat list of Event objects (not globally sorted by time;
    each account's own events are chronologically consistent).
    """
    rng = random.Random(seed)
    events: List[Event] = []

    session_counter = 0
    task_counter = 0
    followup_counter = 0

    for acct_idx in range(1, num_accounts + 1):
        account_id = _new_id("acct", acct_idx)
        account_created_at = base_date + timedelta(days=rng.randint(0, 60))
        events.append(
            Event(
                account_id=account_id,
                event_type=EventType.ACCOUNT_CREATED,
                timestamp=account_created_at,
            )
        )

        cursor = account_created_at

        # --- session cycles: booked -> (completed | no_show [-> followup]) ---
        num_sessions = rng.randint(1, 3)
        for _ in range(num_sessions):
            session_counter += 1
            session_id = _new_id("sess", session_counter)

            booked_at = cursor + timedelta(days=rng.randint(1, 10))
            events.append(
                Event(
                    account_id=account_id,
                    event_type=EventType.SESSION_BOOKED,
                    timestamp=booked_at,
                    ref_id=session_id,
                )
            )

            outcome_at = booked_at + timedelta(days=rng.randint(1, 14))

            if rng.random() < session_no_show_rate:
                events.append(
                    Event(
                        account_id=account_id,
                        event_type=EventType.SESSION_NO_SHOW,
                        timestamp=outcome_at,
                        ref_id=session_id,
                    )
                )

                followup_counter += 1
                followup_id = _new_id("fu", followup_counter)
                followup_required_at = outcome_at + timedelta(
                    days=rng.randint(1, FOLLOWUP_SLA_DAYS)
                )
                events.append(
                    Event(
                        account_id=account_id,
                        event_type=EventType.FOLLOWUP_REQUIRED,
                        timestamp=followup_required_at,
                        ref_id=followup_id,
                        related_ref_id=session_id,
                    )
                )

                if rng.random() < followup_completion_rate:
                    followup_completed_at = followup_required_at + timedelta(
                        days=rng.randint(1, 5)
                    )
                    events.append(
                        Event(
                            account_id=account_id,
                            event_type=EventType.FOLLOWUP_COMPLETED,
                            timestamp=followup_completed_at,
                            ref_id=followup_id,
                        )
                    )
                    cursor = followup_completed_at
                else:
                    cursor = followup_required_at
            else:
                events.append(
                    Event(
                        account_id=account_id,
                        event_type=EventType.SESSION_COMPLETED,
                        timestamp=outcome_at,
                        ref_id=session_id,
                    )
                )
                cursor = outcome_at

        # --- task cycles: required -> completed ---
        num_tasks = rng.randint(1, 3)
        for _ in range(num_tasks):
            task_counter += 1
            task_id = _new_id("task", task_counter)

            required_at = cursor + timedelta(days=rng.randint(1, 10))
            events.append(
                Event(
                    account_id=account_id,
                    event_type=EventType.TASK_REQUIRED,
                    timestamp=required_at,
                    ref_id=task_id,
                )
            )

            completed_at = required_at + timedelta(hours=rng.randint(2, 96))
            events.append(
                Event(
                    account_id=account_id,
                    event_type=EventType.TASK_COMPLETED,
                    timestamp=completed_at,
                    ref_id=task_id,
                )
            )
            cursor = completed_at

    return events