import unittest
from collections import defaultdict

from signalguard.data.generator import generate_clean_dataset, FOLLOWUP_SLA_DAYS
from signalguard.schemas.event import EventType


class TestCleanGenerator(unittest.TestCase):
    """
    These checks are deliberately hand-rolled here, NOT calls into the
    production deterministic-QC / tool-calling modules that get built on. 
    This test file's only job is to prove the clean
    generator is a valid ground truth to corrupt later -- it is not the
    QC system itself.
    """

    @classmethod
    def setUpClass(cls):
        cls.events = generate_clean_dataset(num_accounts=80, seed=42)
        cls.by_ref_id = defaultdict(list)
        for e in cls.events:
            if e.ref_id is not None:
                cls.by_ref_id[e.ref_id].append(e)

    def test_locked_account_count(self):
        created = [e for e in self.events if e.event_type == EventType.ACCOUNT_CREATED]
        self.assertEqual(len(created), 80)

    def test_locked_event_count_in_range(self):
        # Locked benchmark target: ~600-900 total events for 80 accounts
        self.assertGreaterEqual(len(self.events), 600)
        self.assertLessEqual(len(self.events), 900)

    def test_only_locked_event_types_present(self):
        allowed = set(EventType)
        seen = {e.event_type for e in self.events}
        self.assertTrue(seen.issubset(allowed))

    def test_r1_session_outcome_has_prior_booking(self):
        for ref_id, evs in self.by_ref_id.items():
            types = {e.event_type for e in evs}
            if EventType.SESSION_COMPLETED in types or EventType.SESSION_NO_SHOW in types:
                self.assertIn(
                    EventType.SESSION_BOOKED, types,
                    f"session outcome for {ref_id} missing session.booked (R1)",
                )
                booked_ts = next(e.timestamp for e in evs if e.event_type == EventType.SESSION_BOOKED)
                outcome_ts = next(
                    e.timestamp for e in evs
                    if e.event_type in (EventType.SESSION_COMPLETED, EventType.SESSION_NO_SHOW)
                )
                self.assertLessEqual(booked_ts, outcome_ts, f"booking after outcome for {ref_id} (R1)")

    def test_r2_task_completed_never_precedes_task_required(self):
        for ref_id, evs in self.by_ref_id.items():
            types = {e.event_type for e in evs}
            if EventType.TASK_COMPLETED in types:
                self.assertIn(EventType.TASK_REQUIRED, types, f"task {ref_id} missing task.required (R2)")
                required_ts = next(e.timestamp for e in evs if e.event_type == EventType.TASK_REQUIRED)
                completed_ts = next(e.timestamp for e in evs if e.event_type == EventType.TASK_COMPLETED)
                self.assertLessEqual(required_ts, completed_ts, f"task.completed precedes task.required for {ref_id} (R2)")

    def test_r3_followup_completed_has_prior_required(self):
        for ref_id, evs in self.by_ref_id.items():
            types = {e.event_type for e in evs}
            if EventType.FOLLOWUP_COMPLETED in types:
                self.assertIn(
                    EventType.FOLLOWUP_REQUIRED, types,
                    f"followup {ref_id} missing followup.required (R3)",
                )

    def test_r4_followup_completed_never_precedes_required(self):
        for ref_id, evs in self.by_ref_id.items():
            types = {e.event_type for e in evs}
            if EventType.FOLLOWUP_COMPLETED in types and EventType.FOLLOWUP_REQUIRED in types:
                required_ts = next(e.timestamp for e in evs if e.event_type == EventType.FOLLOWUP_REQUIRED)
                completed_ts = next(e.timestamp for e in evs if e.event_type == EventType.FOLLOWUP_COMPLETED)
                self.assertLessEqual(required_ts, completed_ts, f"followup.completed precedes followup.required for {ref_id} (R4)")

    def test_r5_followup_required_within_sla_of_no_show(self):
        no_shows_by_session = {
            e.ref_id: e.timestamp
            for e in self.events
            if e.event_type == EventType.SESSION_NO_SHOW
        }
        followup_requireds = [e for e in self.events if e.event_type == EventType.FOLLOWUP_REQUIRED]

        # Every no_show must have a linked followup.required (R5 existence)
        linked_sessions = {e.related_ref_id for e in followup_requireds}
        for session_id in no_shows_by_session:
            self.assertIn(
                session_id, linked_sessions,
                f"session.no_show {session_id} has no linked followup.required (R5)",
            )

        # Every followup.required linked to a no_show must land within the SLA window
        for fu in followup_requireds:
            no_show_ts = no_shows_by_session[fu.related_ref_id]
            delta_days = (fu.timestamp - no_show_ts).days
            self.assertGreaterEqual(delta_days, 0, f"followup {fu.ref_id} precedes its triggering no_show (R5)")
            self.assertLessEqual(
                delta_days, FOLLOWUP_SLA_DAYS,
                f"followup {fu.ref_id} scheduled {delta_days}d after no_show, exceeds {FOLLOWUP_SLA_DAYS}d SLA (R5)",
            )

    def test_deterministic_with_fixed_seed(self):
        a = generate_clean_dataset(num_accounts=80, seed=42)
        b = generate_clean_dataset(num_accounts=80, seed=42)
        # event_id is random per call (uuid4), so compare everything except event_id
        strip = lambda evs: [{k: v for k, v in e.to_dict().items() if k != "event_id"} for e in evs]
        self.assertEqual(strip(a), strip(b))


if __name__ == "__main__":
    unittest.main()