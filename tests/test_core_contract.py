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
    Commitment,
    ItemBatch,
    Location,
    PersonState,
    RunManifest,
    ScheduledEvent,
)
from plain_life.core_adapters import (  # noqa: E402
    PopulationStateAdapter,
    WorldClockAdapter,
    population_from_state,
    population_to_state,
    world_from_state,
    world_to_state,
)
from plain_life.core import (  # noqa: E402
    SimulationCore,
    TransferItemHandler,
    create_run,
)
from plain_life.environment import (  # noqa: E402
    generate_environment,
    load_environment_baseline,
)
from plain_life.population import generate_population  # noqa: E402


def _manifest(run_id: str = "test-core") -> RunManifest:
    return RunManifest(
        run_id=run_id,
        code_commit="test",
        contract_version=CONTRACT_VERSION,
        scenario_id="core_unit_fixture",
        scenario_fingerprint="scenario",
        parameter_fingerprint="parameters",
        random_seed=7,
        environment_fingerprint="environment",
        population_fingerprint="population",
        initial_day_of_year=90,
        start_world_seconds=0,
        day_seconds=86400,
        mode="contract_fixture",
    )


def _core() -> SimulationCore:
    core = create_run(
        _manifest(),
        {"transfer_item": TransferItemHandler()},
    )
    core.register_person(
        PersonState(
            person_id="p1",
            household_id="h1",
            location=Location(0.0, 0.0, 0),
            body={"hunger": 0.2},
        )
    )
    core.register_person(
        PersonState(
            person_id="p2",
            household_id="h2",
            location=Location(1.0, 0.0, 1),
            body={"hunger": 0.3},
        )
    )
    core.register_person(
        PersonState(
            person_id="p3",
            household_id="h3",
            location=Location(2.0, 0.0, 2),
            body={"hunger": 0.4},
        )
    )
    core.add_item(
        ItemBatch(
            batch_id="food",
            category="berries",
            quantity=1.0,
            unit="kg",
            state="edible",
            owner_kind="person",
            owner_id="p1",
            location=Location(0.0, 0.0, 0),
            kcal_per_kg=500.0,
        )
    )
    return core


def _transfer_intent(
    *,
    action_id: str,
    target_person_id: str,
    formed_at: int,
    duration_seconds: int,
) -> ActionIntent:
    return ActionIntent(
        action_id=action_id,
        person_id="p1",
        action_type="transfer_item",
        formed_at_world_seconds=formed_at,
        expected_duration_seconds=duration_seconds,
        target={
            "batch_id": "food",
            "quantity": 0.6,
            "to_owner_kind": "person",
            "to_owner_id": target_person_id,
        },
    )


class CoreContractTests(unittest.TestCase):
    def test_reservation_blocks_double_delivery(self) -> None:
        core = _core()
        first = core.submit_action(
            _transfer_intent(
                action_id="a1",
                target_person_id="p2",
                formed_at=0,
                duration_seconds=3600,
            )
        )
        core.start_action(first.action_id)
        second = core.submit_action(
            _transfer_intent(
                action_id="a2",
                target_person_id="p3",
                formed_at=0,
                duration_seconds=3600,
            )
        )
        core.start_action(second.action_id)
        self.assertEqual("blocked", core.actions["a2"].status)
        self.assertEqual(0.4, core.available_item_quantity("food"))
        core.advance_to(3600)
        self.assertEqual(0.4, core.items["food"].quantity)
        outputs = [
            batch
            for batch in core.items.values()
            if batch.owner_id == "p2"
        ]
        self.assertEqual(1, len(outputs))
        self.assertEqual(0.6, outputs[0].quantity)

    def test_interrupted_action_has_no_output(self) -> None:
        core = _core()
        action = core.submit_action(
            _transfer_intent(
                action_id="a1",
                target_person_id="p2",
                formed_at=0,
                duration_seconds=3600,
            )
        )
        core.start_action(action.action_id)
        core.advance_to(1800)
        core.interrupt_action(action.action_id, reason="test")
        self.assertEqual("interrupted", core.actions["a1"].status)
        self.assertEqual(1.0, core.items["food"].quantity)
        self.assertFalse(core.actions["a1"].output_batch_ids)
        self.assertFalse(core.reservations)

    def test_sqlite_restore_continues_active_action_and_preserves_state(
        self,
    ) -> None:
        core = _core()
        core.record_knowledge(
            person_id="p1",
            subject="water",
            stage="independent",
            source_event_id=None,
            certainty=0.9,
        )
        core.set_relationship(
            person_id="p1",
            other_person_id="p2",
            domain="care",
            value=0.8,
        )
        core.add_commitment(
            Commitment(
                commitment_id="c1",
                request_id="q1",
                responder_id="p2",
                beneficiary_id="p1",
                service_or_item="care_handover",
                quantity=None,
                unit=None,
                due_start_world_seconds=7200,
                due_end_world_seconds=9000,
                status="pending",
                source_response_id="r1",
            )
        )
        core.schedule_event(
            due_world_seconds=7200,
            event_type="checkpoint",
            actor_ids=["p1"],
            facts={"purpose": "restore"},
            observed_by=["p1"],
        )
        action = core.submit_action(
            _transfer_intent(
                action_id="a1",
                target_person_id="p2",
                formed_at=0,
                duration_seconds=3600,
            )
        )
        core.start_action(action.action_id)
        core.advance_to(1800)
        rng_before = core.random.getstate()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.sqlite3"
            core.save(path)
            loaded = SimulationCore.load(
                path,
                handlers={"transfer_item": TransferItemHandler()},
            )
            self.assertEqual("active", loaded.actions["a1"].status)
            self.assertEqual(rng_before, loaded.random.getstate())
            self.assertEqual("water", loaded.perceived_state("p1").knowledge[0]["subject"])
            loaded.advance_to(7200)
        self.assertEqual(0.4, loaded.items["food"].quantity)
        self.assertEqual(0.6, loaded.items["food:transfer:000001"].quantity)
        self.assertEqual("completed", loaded.actions["a1"].status)
        self.assertEqual(
            1,
            len(
                [
                    event
                    for event in loaded.events
                    if event.event_type == "checkpoint"
                ]
            ),
        )

    def test_clock_is_monotonic_and_pause_blocks_advance(self) -> None:
        core = _core()
        core.advance_to(10)
        with self.assertRaises(ValueError):
            core.advance_to(9)
        core.pause()
        with self.assertRaises(RuntimeError):
            core.advance_by(1)
        core.resume()
        core.advance_by(1)
        self.assertEqual(11, core.clock.current_world_seconds)

    def test_existing_world_follows_core_clock_and_round_trips(self) -> None:
        baseline = load_environment_baseline(
            ROOT
            / "data"
            / "phase1"
            / "versions"
            / "v6"
            / "environment_baseline.json"
        )
        world = generate_environment(baseline)
        population = generate_population(baseline.raw["seed"], 4000)
        manifest = _manifest("adapter-test")
        manifest.environment_fingerprint = world.initial_fingerprint
        manifest.population_fingerprint = population.fingerprint
        core = create_run(manifest)
        WorldClockAdapter(world).bind(core)
        PopulationStateAdapter(population).bind(core)
        self.assertEqual(
            population.fingerprint,
            population_from_state(
                core.module_state("body_population")
            ).fingerprint,
        )
        core.advance_to(2 * 86400)
        self.assertEqual(2, world.elapsed_days)
        state = core.module_state("environment_world")
        self.assertEqual(world.fingerprint(), world_from_state(state).fingerprint())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "adapter.sqlite3"
            core.save(path)
            loaded = SimulationCore.load(path)
            restored_world = world_from_state(
                loaded.module_state("environment_world")
            )
        self.assertEqual(world.fingerprint(), restored_world.fingerprint())


if __name__ == "__main__":
    unittest.main()
