from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.contracts import (  # noqa: E402
    CONTRACT_VERSION,
    ActionIntent,
    Location,
    PersonState,
    RunManifest,
)
from plain_life.core import SimulationCore, create_run  # noqa: E402
from plain_life.core_adapters import WorldClockAdapter  # noqa: E402
from plain_life.environment import (  # noqa: E402
    generate_environment,
    load_environment_baseline,
)
from plain_life.life_actions import (  # noqa: E402
    DrinkAtWaterHandler,
    MoveToLocationHandler,
    move_duration_seconds,
)


def _cell_location(world, cell_index: int) -> Location:
    cell = world.cells[cell_index]
    return Location(
        x_m=cell.x * world.cell_size_m,
        y_m=cell.y * world.cell_size_m,
        cell_index=cell.index,
    )


class WaterChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_environment(
            load_environment_baseline(
                ROOT
                / "data"
                / "phase1"
                / "versions"
                / "v6"
                / "environment_baseline.json"
            )
        )
        drop = cls.world.drop_point
        water = min(
            cls.world.water_cells,
            key=lambda cell: (
                (cell.x - drop.x) ** 2 + (cell.y - drop.y) ** 2
            ),
        )
        cls.drop_location = _cell_location(cls.world, drop.index)
        cls.water_location = _cell_location(cls.world, water.index)

    def _core(self, run_id: str = "water-chain-test") -> SimulationCore:
        manifest = RunManifest(
            run_id=run_id,
            code_commit="test",
            contract_version=CONTRACT_VERSION,
            scenario_id="water_chain_test",
            scenario_fingerprint="scenario",
            parameter_fingerprint="parameters",
            random_seed=self.world.seed,
            environment_fingerprint=self.world.initial_fingerprint,
            population_fingerprint="water-chain-person",
            initial_day_of_year=self.world.start_day_of_year,
            start_world_seconds=0,
            day_seconds=86400,
            mode="integration_fixture",
        )
        core = create_run(
            manifest,
            {
                "move_to_location": MoveToLocationHandler(),
                "drink_at_water": DrinkAtWaterHandler(),
            },
        )
        WorldClockAdapter(self.world).bind(core)
        core.register_person(
            PersonState(
                person_id="p1",
                household_id="h1",
                location=self.drop_location,
                body={"thirst": 0.72},
            )
        )
        return core

    def test_move_drink_body_water_and_events_share_one_chain(self) -> None:
        core = self._core()
        move_seconds = move_duration_seconds(
            self.drop_location, self.water_location
        )
        core.submit_action(
            ActionIntent(
                action_id="move",
                person_id="p1",
                action_type="move_to_location",
                formed_at_world_seconds=0,
                expected_duration_seconds=move_seconds,
                target={"location": self.water_location.to_dict()},
            )
        )
        core.start_action("move")
        core.advance_to(move_seconds)
        self.assertEqual(
            self.water_location.cell_index,
            core.people["p1"].location.cell_index,
        )

        water_before = core.module_state("environment_world")[
            "water_volume_m3"
        ]
        core.submit_action(
            ActionIntent(
                action_id="drink",
                person_id="p1",
                action_type="drink_at_water",
                formed_at_world_seconds=move_seconds,
                expected_duration_seconds=120,
                target={
                    "water_location": self.water_location.to_dict(),
                    "water_module": "environment_world",
                    "litres": 1.5,
                },
            )
        )
        core.start_action("drink")
        core.advance_to(move_seconds + 120)
        water_after = core.module_state("environment_world")[
            "water_volume_m3"
        ]
        self.assertLess(water_after, water_before)
        self.assertLess(core.people["p1"].body["thirst"], 0.72)
        events = core.query_events(person_id="p1")
        self.assertIn(
            "person_moved",
            [event["event_type"] for event in events],
        )
        self.assertIn(
            "body_state_changed",
            [event["event_type"] for event in events],
        )
        completed = {
            event["action_id"]
            for event in events
            if event["event_type"] == "action_completed"
        }
        self.assertEqual({"move", "drink"}, completed)

    def test_drink_away_from_water_is_blocked(self) -> None:
        core = self._core("water-chain-away")
        core.submit_action(
            ActionIntent(
                action_id="drink-away",
                person_id="p1",
                action_type="drink_at_water",
                formed_at_world_seconds=0,
                expected_duration_seconds=120,
                target={
                    "water_location": self.water_location.to_dict(),
                    "water_module": "environment_world",
                    "litres": 1.5,
                },
            )
        )
        result = core.start_action("drink-away")
        self.assertEqual("blocked", result.status)
        self.assertEqual(
            "person_not_at_water_location", result.result["reason"]
        )

    def test_drink_survives_sqlite_restore_and_body_changes_on_completion(
        self,
    ) -> None:
        core = self._core("water-chain-restore")
        move_seconds = move_duration_seconds(
            self.drop_location, self.water_location
        )
        core.people["p1"].location = self.water_location
        core.submit_action(
            ActionIntent(
                action_id="drink",
                person_id="p1",
                action_type="drink_at_water",
                formed_at_world_seconds=0,
                expected_duration_seconds=120,
                target={
                    "water_location": self.water_location.to_dict(),
                    "water_module": "environment_world",
                    "litres": 1.5,
                },
            )
        )
        core.start_action("drink")
        core.advance_to(60)
        thirst_before_completion = core.people["p1"].body["thirst"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "water.sqlite3"
            core.save(path)
            restored = SimulationCore.load(
                path,
                handlers={
                    "drink_at_water": DrinkAtWaterHandler(),
                },
                module_factories={
                    "environment_world": WorldClockAdapter.restore,
                },
            )
        self.assertEqual(
            thirst_before_completion,
            restored.people["p1"].body["thirst"],
        )
        restored.advance_to(120)
        self.assertLess(restored.people["p1"].body["thirst"], 0.72)


if __name__ == "__main__":
    unittest.main()

