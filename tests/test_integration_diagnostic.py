from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.integration import run_seven_day_integration  # noqa: E402


class IntegrationDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_seven_day_integration(ROOT)

    def test_seven_day_integration_keeps_accounts_closed(self) -> None:
        self.assertFalse(self.result["formal_history"])
        self.assertFalse(self.result["long_term_conclusion_allowed"])
        self.assertEqual(7, self.result["days"])
        self.assertEqual(0.0, self.result["time_account_hours"]["closure_error_hours"])
        for ledger in self.result["resource_ledger"].values():
            self.assertLessEqual(abs(ledger["closure_error_kg"]), 0.001)
            self.assertTrue(ledger["non_negative"])

    def test_integration_connects_social_actions_without_global_search(self) -> None:
        social = self.result["social_action_funnel"]
        self.assertEqual(
            "connected_to_integrated_loop", social["classification"]
        )
        request_count = sum(
            social[aid_type]["request_sent"]
            for aid_type in (
                "water",
                "food",
                "fire",
                "care",
                "shelter",
                "teaching",
            )
        )
        self.assertGreater(request_count, 0)
        for record in self.result["social_action_records"]:
            distance = record.get("distance_km")
            if distance is not None:
                self.assertLessEqual(distance, 1.0)

    def test_body_feedback_is_enabled_and_bounded(self) -> None:
        integration = self.result["integration"]
        self.assertTrue(integration["enabled"])
        self.assertFalse(integration["death_modeled"])
        self.assertFalse(integration["disease_modeled"])
        self.assertEqual(0, integration["deaths"])
        self.assertGreaterEqual(integration["minimum_work_capacity"], 0.05)


if __name__ == "__main__":
    unittest.main()
