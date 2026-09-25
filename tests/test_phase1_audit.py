from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import phase1_audit  # noqa: E402


class Phase1AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data_dir = ROOT / "data" / "phase1"
        cls.world = phase1_audit.load_json(data_dir / "world.json")
        cls.survival = phase1_audit.load_json(data_dir / "survival.json")
        cls.population = phase1_audit.load_json(data_dir / "population.json")

    def test_current_baseline_is_blocked(self) -> None:
        audit = phase1_audit.build_audit(
            self.world, self.survival, self.population
        )
        self.assertEqual("BLOCKED", audit["gate_status"])
        self.assertGreater(audit["summary"]["blockers"], 0)

    def test_external_biota_breaks_closed_world(self) -> None:
        world = copy.deepcopy(self.world)
        world["boundary"]["external_biota"]["value"] = "migrating fish"
        findings = phase1_audit.audit_environment(world)
        self.assertIn("external_biota", {item.code for item in findings})

    def test_known_fact_requires_evidence(self) -> None:
        world = copy.deepcopy(self.world)
        record = world["components"]["terrain.slope"]
        record["status"] = "known"
        record["value"] = {"range_degrees": [0, 2]}
        record["evidence"] = []
        findings = phase1_audit.audit_environment(world)
        self.assertIn(
            "known_without_evidence", {item.code for item in findings}
        )

    def test_required_environment_field_cannot_be_deleted(self) -> None:
        world = copy.deepcopy(self.world)
        del world["components"]["freshwater.quality"]
        findings = phase1_audit.audit_environment(world)
        self.assertIn("missing_record", {item.code for item in findings})

    def test_required_survival_problem_cannot_be_deleted(self) -> None:
        survival = copy.deepcopy(self.survival)
        survival["paths"]["water"]["required_problems"].remove("reach water")
        findings = phase1_audit.audit_survival(survival)
        self.assertIn(
            "incomplete_required_problems", {item.code for item in findings}
        )

    def test_evaluated_window_requires_quantitative_result(self) -> None:
        survival = copy.deepcopy(self.survival)
        survival["windows"][0]["status"] = "evaluated"
        findings = phase1_audit.audit_survival(survival)
        codes = {item.code for item in findings}
        self.assertIn("missing_bottleneck", codes)
        self.assertIn("missing_feasible_paths", codes)
        self.assertIn("missing_capacity_margin", codes)

    def test_consistent_population_snapshot_passes_population_audit(self) -> None:
        population = copy.deepcopy(self.population)
        population["snapshot"] = self._consistent_snapshot()
        population["ecology_link"] = {
            "status": "ready",
            "aggregate_population_target": 4000,
            "household_capability_distribution": "fixture",
            "care_load": "fixture",
            "labor_time_available": "fixture",
            "food_and_water_access_by_household": "fixture",
            "evidence": ["TEST-FIXTURE"],
        }
        blockers = [
            item
            for item in phase1_audit.audit_population(population)
            if item.severity == "blocker"
        ]
        self.assertEqual([], blockers)

    def test_infant_requires_resolving_caregiver(self) -> None:
        population = copy.deepcopy(self.population)
        population["snapshot"] = self._consistent_snapshot()
        population["snapshot"]["people"][0]["caregiver_ids"] = ["missing"]
        population["ecology_link"] = {
            "status": "ready",
            "aggregate_population_target": 4000,
            "household_capability_distribution": "fixture",
            "care_load": "fixture",
            "labor_time_available": "fixture",
            "food_and_water_access_by_household": "fixture",
            "evidence": ["TEST-FIXTURE"],
        }
        findings = phase1_audit.audit_population(population)
        self.assertIn("invalid_reference", {item.code for item in findings})

    @staticmethod
    def _consistent_snapshot() -> dict:
        people = []
        households = []
        for index in range(4000):
            person_id = f"p{index}"
            people.append(
                {
                    "id": person_id,
                    "life_stage": "infant" if index == 0 else "adult",
                    "life_history": ["fixture history"],
                    "skills": [],
                    "caregiver_ids": ["p1"] if index == 0 else [],
                }
            )
            households.append({"id": f"h{index}", "member_ids": [person_id]})
        return {
            "status": "ready",
            "people": people,
            "households": households,
            "kinship_edges": [
                {"kind": "parent_child", "from": "p1", "to": "p0"}
            ],
            "pregnancy_events": [
                {
                    "person_id": "p1",
                    "outcome": "live_birth",
                    "infant_id": "p0",
                }
            ],
            "lactation_links": [{"person_id": "p1", "infant_id": "p0"}],
        }


if __name__ == "__main__":
    unittest.main()
