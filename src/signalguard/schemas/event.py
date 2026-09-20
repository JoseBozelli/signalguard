"""
SignalGuard-specific event schema (Zone A: public portfolio).

Defines the locked 8-type event vocabulary and each type's correlation-ID requirements, built on the domain-neutral
mechanic in base_event.py. Public API unchanged from the pre-split version:
`from signalguard.schemas.event import Event, EventType` still works exactly as before, including identical validation
error conditions and to_dict() behavior.
"""

from __future__ import annotations

from enum import Enum

from pydantic import model_validator

from signalguard.schemas.base_event import BaseCorrelatedEvent, validate_correlation_ids

class EventType(str, Enum):
    ACCOUNT_CREATED = "account.created"
    SESSION_BOOKED = "session.booked"
    SESSION_COMPLETED = "session.completed"
    SESSION_NO_SHOW = "session.no_show"
    TASK_REQUIRED = "task.required"
    TASK_COMPLETED = "task.completed"
    FOLLOWUP_REQUIRED = "followup.required"
    FOLLOWUP_COMPLETED = "followup.completed"

# Event types that must carry a ref_id (i.e. everything except account.created)
_REQUIRED_REF_ID = {
    EventType.SESSION_BOOKED,
    EventType.SESSION_COMPLETED,
    EventType.SESSION_NO_SHOW,
    EventType.TASK_REQUIRED,
    EventType.TASK_COMPLETED,
    EventType.FOLLOWUP_REQUIRED,
    EventType.FOLLOWUP_COMPLETED
}
_NO_REF_ID_TYPES = {EventType.ACCOUNT_CREATED}
_ALLOWS_RELATED_REF_ID = {EventType.FOLLOWUP_REQUIRED}

class Event(BaseCorrelatedEvent):
    event_type: EventType

    @model_validator(mode="after")
    def _validate(self) -> "Event":
        validate_correlation_ids(
            account_id=self.account_id,
            event_type=self.event_type,
            ref_id=self.ref_id,
            related_ref_id=self.related_ref_id,
            requires_ref_id=_REQUIRED_REF_ID,
            no_ref_id_types=_NO_REF_ID_TYPES,
            allows_related_ref_id=_ALLOWS_RELATED_REF_ID
        )
        return self