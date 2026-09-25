from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import phase1_audit  # noqa: E402
from plain_life.environment import (  # noqa: E402
    advance_day,
    evaluate_boundary_attempt,
    generate_environment,
    load_environment_baseline,
)
from plain_life.population import generate_population  # noqa: E402
from plain_life.reporting import (  # noqa: E402
    render_environment_report,
    render_initialization_report,
    render_survival_report,
)
from plain_life.survival import (  # noqa: E402
    _exploration_radius_km,
    run_survival_validation,
)


class Phase1ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_environment_baseline(
            ROOT
            / "data"
            / "phase1"
            / "versions"
            / "v2"
            / "environment_baseline.json"
        )
        cls.world = generate_environment(cls.baseline)
        cls.population = generate_population(cls.baseline.raw["seed"])

    def test_world_is_fixed_and_deterministic(self) -> None:
        second = generate_environment(self.baseline)
        self.assertEqual(5000, len(self.world.cells))
        self.assertEqual(50.0, 5000 * 0.01)
        self.assertEqual(self.world.initial_fingerprint, second.initial_fingerprint)
        self.assertEqual(354, len(self.world.water_cells))

    def test_environment_can_regenerate_the_next_season(self) -> None:
        world = copy.deepcopy(self.world)
        initial_acorns = sum(world.plant_stock_kg["oak_acorn"])
        for _ in range(365):
            advance_day(world)
        recovered_acorns = sum(world.plant_stock_kg["oak_acorn"])
        self.assertGreater(recovered_acorns, initial_acorns * 0.9)

    def test_population_is_internally_consistent(self) -> None:
        contract = phase1_audit.load_json(
            ROOT / "data" / "phase1" / "versions" / "v2" / "population.json"
        )
        contract["snapshot"] = self.population.to_snapshot_dict()
        contract["ecology_link"] = {
            "status": "ready",
            "aggregate_population_target": 4000,
            "household_capability_distribution": "test",
            "care_load": "test",
            "labor_time_available": "test",
            "food_and_water_access_by_household": "test",
            "evidence": ["TEST"],
        }
        blockers = [
            finding
            for finding in phase1_audit.audit_population(contract)
            if finding.severity == "blocker"
        ]
        self.assertEqual([], blockers)
        self.assertEqual(4000, len(self.population.people))
        self.assertEqual(1000, len(self.population.households))
        self.assertEqual(
            sum(
                person.life_stage == "infant"
                for person in self.population.people
            ),
            len(self.population.lactation_links),
        )

    def test_v2_drop_and_survival_ledgers_are_explicit(self) -> None:
        result = run_survival_validation(
            self.world, self.population, days=3
        )
        initial = result.window_results["initial_days"]
        self.assertEqual("failed", initial["status"])
        self.assertGreaterEqual(initial["minimum_water_ratio"], 0.9)
        self.assertEqual(1, result.migration_summary["drop_instant_camps"])
        self.assertGreater(
            result.migration_summary["camps_after_day_one_selection"], 1
        )
        self.assertEqual(
            "fixed_population_demand_pressure_test", result.test_kind
        )
        for ledger in result.resource_ledger.values():
            self.assertLessEqual(abs(ledger["closure_error_kg"]), 0.001)
            self.assertTrue(ledger["non_negative"])
        fish = result.harvest_details["fish"]
        self.assertLess(fish["edible_food_kg"], fish["stock_kg_removed"])
        self.assertTrue(result.initial_world_unchanged)
        environment_report = render_environment_report(
            self.world, self.population, result, "v2-test"
        )
        survival_report = render_survival_report(result, "v2-test")
        initialization_report = render_initialization_report(
            self.population, result, [], "v2-test", "BLOCKED"
        )
        self.assertIn("期末存量 = 期初存量", environment_report)
        self.assertIn("固定人口需求压力测试", survival_report)
        self.assertIn("全部审计阻断项", initialization_report)

    def test_climate_matches_warm_humid_early_season(self) -> None:
        climate = self.baseline.raw["climate"]
        self.assertEqual(90, self.baseline.raw["start_day_of_year"])
        self.assertGreater(sum(climate["rainfall_mm"]), 1300.0)
        self.assertGreater(sum(climate["temperature_c"]) / 12.0, 18.0)

    def test_exploration_radius_expands_without_global_map(self) -> None:
        self.assertLess(_exploration_radius_km(1), _exploration_radius_km(20))
        self.assertEqual(5.0, _exploration_radius_km(100))

    def test_world_edge_is_consistent_non_damaging_and_silent(self) -> None:
        corner = self.world.cells[0]
        first = evaluate_boundary_attempt(
            self.world, corner.index, -1, 0
        )
        second = evaluate_boundary_attempt(
            self.world, corner.index, -1, 0
        )
        self.assertEqual(first, second)
        self.assertEqual("blocked", first["outcome"])
        self.assertEqual(0.0, first["damage"])
        self.assertIsNone(first["hint"])


if __name__ == "__main__":
    unittest.main()
