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

    def test_season_rejection_audit_is_resource_specific(self) -> None:
        season = self.result["season_rejection_audit"]
        self.assertEqual(0, season["records_without_day_of_year"])
        self.assertEqual(90, season["drop_instant_day_of_year"])
        self.assertEqual(list(range(91, 98)), season["observed_world_days"])
        self.assertEqual(
            "whole_resource_cell_uses_day_of_year_window",
            season["season_model"],
        )
        self.assertFalse(season["local_maturity_modeled"])
        self.assertEqual(0, season["incorrect_outside_window_rejections"])
        self.assertEqual(
            {
                "arrowhead",
                "mixed_berries",
                "hazelnut",
                "oak_acorn",
            },
            set(season["season_only_by_resource"]),
        )
        for resource_id in (
            "cattail",
            "spring_greens",
            "fish",
            "waterfowl",
            "hare",
            "deer",
        ):
            self.assertEqual(
                0,
                season["resource_assessments"][resource_id][
                    "outside_window_rejections"
                ],
            )

    def test_fishing_exits_have_specific_cause_and_time_destination(self) -> None:
        fishing = self.result["fishing_exit_diagnosis"]
        self.assertEqual(651, fishing["day_2_fishing_households"])
        self.assertEqual(420, fishing["day_4_fishing_households_all"])
        self.assertEqual(200, fishing["day_5_fishing_households_all"])
        self.assertEqual(
            413, fishing["day_4_fishing_households_from_day_2"]
        )
        self.assertEqual(
            193, fishing["day_5_fishing_households_from_day_2"]
        )
        self.assertEqual(238, fishing["exited_both_days_households"])
        self.assertEqual(
            fishing["day_2_fishing_households"] * 2,
            sum(fishing["exit_daily_classification"].values()),
        )
        self.assertEqual(
            fishing["exited_both_days_households"],
            sum(fishing["exit_cohort_classification"].values()),
        )
        self.assertEqual(
            1,
            fishing[
                "exit_cohort_household_days_with_positive_fish_stock"
            ],
        )
        self.assertGreater(
            fishing["exit_daily_classification"].get(
                "known_fish_cells_depleted", 0
            ),
            0,
        )
        fish_activity = fishing[
            "resource_activity_shift_per_exiting_household"
        ]["day_2_fish"]
        self.assertGreater(fish_activity["harvest_hours"], 0.0)
        self.assertGreater(fish_activity["stock_kg_removed"], 0.0)
        concentration = fishing["fish_selected_cells_by_day"]
        self.assertLess(
            concentration["5"]["distinct_selected_cells"],
            concentration["2"]["distinct_selected_cells"],
        )
        self.assertGreater(
            concentration["5"]["largest_cell_households"], 0
        )
        self.assertTrue(fishing["representative_exits"])
        for item in fishing["representative_exits"]:
            for day in item["daily"]:
                if day["day"] in (4, 5):
                    self.assertNotIn(
                        "fish", day["selected_resources"]
                    )

    def test_space_information_control_isolates_discovery_limit(self) -> None:
        limited = self.result["spatial_rule_audit"]
        self.assertEqual(
            {
                "1": 951,
                "2": 0,
                "3": 0,
                "4": 0,
                "5": 0,
                "6": 0,
                "7": 0,
            },
            limited["migration_by_day"],
        )
        self.assertEqual(
            238, limited["target_limited_exit_households"]
        )
        self.assertEqual(
            195, limited["target_limited_exit_migrations"]
        )
        self.assertEqual(
            237,
            limited["target_limited_exit_blocked_reasons"][
                "migration_cooldown"
            ],
        )
        self.assertFalse(
            limited["rules"]["harvest_uses_person_known_cells"]
        )

        control = self.result["spatial_information_control"]
        self.assertTrue(control["same_initial_world"])
        self.assertTrue(control["same_initial_population"])
        self.assertTrue(control["same_initial_skills"])
        self.assertTrue(control["same_season"])
        self.assertTrue(control["same_travel_tool_and_processing_rules"])
        limited_day_seven = self.result["daily_metrics"][-1]["food_ratio"]
        control_day_seven = control["daily_metrics"][-1]["food_ratio"]
        self.assertGreater(control_day_seven, limited_day_seven)
        self.assertLess(control_day_seven, 0.8)
        self.assertEqual(
            1,
            control["fish_exit_diagnosis"][
                "exited_both_days_households"
            ],
        )
        self.assertGreater(
            control["fish_exit_diagnosis"][
                "fish_selected_cells_by_day"
            ]["7"]["selected_cell_occurrences"],
            500,
        )


if __name__ == "__main__":
    unittest.main()
