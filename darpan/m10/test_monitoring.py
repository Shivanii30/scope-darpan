from __future__ import annotations

import unittest
from datetime import datetime, timezone

from drift import compare, should_block
from scheduler import next_run


class DriftTests(unittest.TestCase):
    def test_schema_variant_change_is_critical(self):
        before = {"sources": {"report.pdf": {"schema_variant": "v1", "format_era": "old"}}}
        after = {"sources": {"report.pdf": {"schema_variant": "v2", "format_era": "old"}}}
        changes = compare(before, after)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["severity"], "critical")
        self.assertEqual(changes[0]["field"], "schema_variant")

    def test_added_source_is_critical(self):
        before = {"sources": {}}
        after = {"sources": {"new.pdf": {"reporting_year": "2025-26"}}}
        changes = compare(before, after)
        self.assertEqual(changes[0]["kind"], "source_added")
        self.assertEqual(changes[0]["severity"], "critical")

    def test_page_change_is_warning(self):
        before = {"sources": {"report.pdf": {"page_count": 100}}}
        after = {"sources": {"report.pdf": {"page_count": 101}}}
        changes = compare(before, after)
        self.assertEqual(changes[0]["severity"], "warning")

    def test_warning_drift_does_not_block(self):
        changes = [{"severity": "warning"}]
        self.assertFalse(should_block(changes, "block", False))

    def test_critical_drift_blocks_until_accepted(self):
        changes = [{"severity": "critical"}]
        self.assertTrue(should_block(changes, "block", False))
        self.assertFalse(should_block(changes, "block", True))
        self.assertFalse(should_block(changes, "warn", False))


class ScheduleTests(unittest.TestCase):
    def test_next_monthly_boundary(self):
        now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run(now, "monthly", 3), datetime(2026, 12, 1, 3, tzinfo=timezone.utc))

    def test_next_quarterly_boundary(self):
        now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run(now, "quarterly", 3), datetime(2027, 1, 1, 3, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
