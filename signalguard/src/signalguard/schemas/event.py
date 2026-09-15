"""
Event schema for SignalGuard.

Event correlation model
------------------------
Each event optionally carries two correlation IDs:

- `ref_id`: the ID of the *lifecycle* this event belongs to. Required for
  every event type except `account.created`. Events that are two ends of
  the same lifecycle (e.g. `session.booked` -> `session.completed`) share
  the same `ref_id`.
- `related_ref_id`: an optional cross-lifecycle reference. Currently only
  used by `followup.required`, which points back at the `ref_id` of the
  `session.no_show` that triggered it (this is what R5's timing-window
  check is evaluated against).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
_REQUIRES_REF_ID = {
    EventType.SESSION_BOOKED,
    EventType.SESSION_COMPLETED,
    EventType.SESSION_NO_SHOW,
    EventType.TASK_REQUIRED,
    EventType.TASK_COMPLETED,
    EventType.FOLLOWUP_REQUIRED,
    EventType.FOLLOWUP_COMPLETED,
}

# Event types allowed to carry related_ref_id
_ALLOWS_RELATED_REF_ID = {EventType.FOLLOWUP_REQUIRED}


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str
    event_type: EventType
    timestamp: datetime
    ref_id: Optional[str] = None
    related_ref_id: Optional[str] = None
    event_id: str = Field(default_factory=lambda: str(uuid4()))

    @model_validator(mode="after")
    def _validate_correlation_ids(self) -> "Event":
        if not self.account_id:
            raise ValueError("account_id must be non-empty")

        if self.event_type in _REQUIRES_REF_ID and self.ref_id is None:
            raise ValueError(
                f"ref_id is required for event_type={self.event_type.value}"
            )
        if self.event_type == EventType.ACCOUNT_CREATED and self.ref_id is not None:
            raise ValueError(
                "ref_id must be None for event_type=account.created"
            )

        if self.related_ref_id is not None and self.event_type not in _ALLOWS_RELATED_REF_ID:
            allowed = ", ".join(e.value for e in _ALLOWS_RELATED_REF_ID)
            raise ValueError(
                f"related_ref_id is only allowed for event_type in [{allowed}], "
                f"got event_type={self.event_type.value}"
            )
        return self

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")