from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.behavior import Task, run_behavior_scenarios  # noqa: E402


class BehaviorScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_behavior_scenarios(ROOT)

    def test_all_required_short_scenarios_pass(self) -> None:
        self.assertTrue(self.result["all_passed"])
        scenario_ids = {
            item["scenario_id"] for item in self.result["scenarios"]
        }
        self.assertEqual(
            {
                "caregiver_outing",
                "neighbor_request",
                "personal_knowledge",
                "teaching_processing",
                "persistent_hunger",
                "family_food_allocation",
                "shared_fire_and_shelter",
                "trace_replay",
            },
            scenario_ids,
        )

    def test_replay_keeps_facts_summaries_and_narrative_separate(self) -> None:
        replay = next(
            item
            for item in self.result["scenarios"]
            if item["scenario_id"] == "trace_replay"
        )
        self.assertTrue(replay["checks"]["summary_marked_as_generated"])
        self.assertTrue(replay["checks"]["no_fabricated_dialogue"])

    def test_overlapping_task_cannot_be_scheduled(self) -> None:
        from plain_life.behavior import BodyState, BehaviorState

        state = BehaviorState(
            person_id="p-test",
            age_years=30,
            life_stage="adult",
            household_id="h-test",
            location_cell=0,
            body=BodyState(
                hunger=0.1,
                thirst=0.1,
                fatigue=0.1,
                sleep_debt_hours=0.0,
                pain=0.0,
                injury=0.0,
                energy_balance_kcal=0.0,
                mobility=1.0,
            ),
        )
        self.assertTrue(
            state.schedule(
                Task("a", "work", 480, 600, 0)
            )
        )
        self.assertFalse(
            state.schedule(
                Task("b", "care", 540, 660, 0)
            )
        )


if __name__ == "__main__":
    unittest.main()
