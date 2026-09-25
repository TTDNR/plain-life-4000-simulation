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

    def test_integration_does_not_force_social_events(self) -> None:
        social = self.result["social_actions"]
        self.assertEqual(0, social["interhousehold_food_requests"])
        self.assertEqual(0, social["teaching_events"])
        self.assertEqual(0, social["temporary_cohabitation_events"])

    def test_body_feedback_is_enabled_and_bounded(self) -> None:
        integration = self.result["integration"]
        self.assertTrue(integration["enabled"])
        self.assertFalse(integration["death_modeled"])
        self.assertFalse(integration["disease_modeled"])
        self.assertEqual(0, integration["deaths"])
        self.assertGreaterEqual(integration["minimum_work_capacity"], 0.05)


if __name__ == "__main__":
    unittest.main()
