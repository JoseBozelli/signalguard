import unittest

from signalguard.schemas.base_event import validate_correlation_ids

REQUIRES = {"booked", "completed"}
NO_REF = {"created"}
ALLOWS_RELATED = {"followup_required"}

class TestValidateCorrelationIds(unittest.TestCase):
    """
    Exercises the domain-neutral correlation validator directly, with an invented toy vocabulary -- providing it has
    no hidden dependency on SignalGuard's specific 8 event types.
    """

    def test_empty_account_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_correlation_ids(
                account_id="", event_type="created", ref_id=None, related_ref_id=None,
                requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
            )

    def test_requires_ref_id_type_without_ref_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_correlation_ids(
                account_id="a1", event_type="booked", ref_id=None, related_ref_id=None,
                requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
            )

    def test_requires_ref_id_type_with_ref_id_accepted(self):
        validate_correlation_ids(
            account_id="a1", event_type="booked", ref_id="r1", related_ref_id=None,
            requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
        )   # no exception = pass

    def test_no_ref_id_type_with_ref_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_correlation_ids(
                account_id="a1", event_type="created", ref_id="r1", related_ref_id=None,
                requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
            )

    def test_no_ref_id_type_without_ref_id_accepted(self):
        validate_correlation_ids(
            account_id="a1", event_type="created", ref_id=None, related_ref_id=None,
            requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
        )

    def test_related_ref_id_on_disallowed_type_rejected(self):
        with self.assertRaises(ValueError):
            validate_correlation_ids(
                account_id="a1", event_type="booked", ref_id="r1", related_ref_id="other",
                requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
            )

    def test_related_ref_id_on_allowed_type_accepted(self):
        validate_correlation_ids(
            account_id="a1", event_type="followup_required", ref_id="f1", related_ref_id="s1",
            requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
        )

    def test_type_in_neither_set_with_no_ref_id_is_fine(self):
        # An event type that is in neither requires_ref_id nor no_ref_id_types (e.g., some future vocabulary's
        # optional-ref_id type) should not be forced eithe way.
        validate_correlation_ids(
            account_id="a1", event_type="untracked_type", ref_id=None, related_ref_id=None,
            requires_ref_id=REQUIRES, no_ref_id_types=NO_REF, allows_related_ref_id=ALLOWS_RELATED
        )

if __name__ == "__main__":
    unittest.main()