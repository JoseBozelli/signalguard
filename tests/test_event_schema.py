import unittest
from datetime import datetime

from pydantic import ValidationError
from signalguard.schemas.event import Event, EventType


class TestEventSchema(unittest.TestCase):
    def test_account_created_without_ref_id_is_valid(self):
        e = Event(
            account_id="acct_00001",
            event_type=EventType.ACCOUNT_CREATED,
            timestamp=datetime(2026, 1, 1),
        )
        self.assertIsNone(e.ref_id)
        self.assertIsNone(e.related_ref_id)

    def test_account_created_with_ref_id_is_invalid(self):
        with self.assertRaises(ValidationError):
            Event(
                account_id="acct_00001",
                event_type=EventType.ACCOUNT_CREATED,
                timestamp=datetime(2026, 1, 1),
                ref_id="sess_00001",
            )

    def test_session_booked_requires_ref_id(self):
        with self.assertRaises(ValidationError):
            Event(
                account_id="acct_00001",
                event_type=EventType.SESSION_BOOKED,
                timestamp=datetime(2026, 1, 1),
            )

    def test_session_booked_with_ref_id_is_valid(self):
        e = Event(
            account_id="acct_00001",
            event_type=EventType.SESSION_BOOKED,
            timestamp=datetime(2026, 1, 1),
            ref_id="sess_00001",
        )
        self.assertEqual(e.ref_id, "sess_00001")

    def test_task_completed_requires_ref_id(self):
        with self.assertRaises(ValidationError):
            Event(
                account_id="acct_00001",
                event_type=EventType.TASK_COMPLETED,
                timestamp=datetime(2026, 1, 1),
            )

    def test_followup_required_needs_related_ref_id_allowed(self):
        # related_ref_id is optional at the schema level (generator always
        # sets it, but schema shouldn't force it — that's a generator/business
        # rule, not a structural constraint)
        e = Event(
            account_id="acct_00001",
            event_type=EventType.FOLLOWUP_REQUIRED,
            timestamp=datetime(2026, 1, 1),
            ref_id="fu_00001",
            related_ref_id="sess_00001",
        )
        self.assertEqual(e.related_ref_id, "sess_00001")

    def test_related_ref_id_disallowed_outside_followup_required(self):
        with self.assertRaises(ValidationError):
            Event(
                account_id="acct_00001",
                event_type=EventType.SESSION_BOOKED,
                timestamp=datetime(2026, 1, 1),
                ref_id="sess_00001",
                related_ref_id="sess_00002",
            )

    def test_empty_account_id_is_invalid(self):
        with self.assertRaises(ValidationError):
            Event(
                account_id="",
                event_type=EventType.ACCOUNT_CREATED,
                timestamp=datetime(2026, 1, 1),
            )

    def test_event_id_auto_generated_and_unique(self):
        e1 = Event(
            account_id="acct_00001",
            event_type=EventType.ACCOUNT_CREATED,
            timestamp=datetime(2026, 1, 1),
        )
        e2 = Event(
            account_id="acct_00001",
            event_type=EventType.ACCOUNT_CREATED,
            timestamp=datetime(2026, 1, 1),
        )
        self.assertNotEqual(e1.event_id, e2.event_id)

    def test_to_dict_serializes_enum_and_datetime(self):
        e = Event(
            account_id="acct_00001",
            event_type=EventType.SESSION_BOOKED,
            timestamp=datetime(2026, 1, 1, 12, 30),
            ref_id="sess_00001",
        )
        d = e.to_dict()
        self.assertEqual(d["event_type"], "session.booked")
        self.assertEqual(d["timestamp"], "2026-01-01T12:30:00")
        self.assertEqual(d["ref_id"], "sess_00001")


if __name__ == "__main__":
    unittest.main()