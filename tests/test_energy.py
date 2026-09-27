import sqlite3
from dataclasses import replace

import pytest

from everlock.controller import Controller
from everlock.domain import Door, apply_action
from everlock.energy import Power, PowerConfig
from everlock.simulation import Timeline, advance, estimated_runtime
from everlock.storage import Storage


def test_one_hour_counts_conversion_loss_once():
    power, timeline = Power(mains_available=False), Timeline()
    expected_runtime = (32 * 0.9 / 8 + 6 * 0.9 / 4) * 3600
    assert power.runtime_seconds() == pytest.approx(expected_runtime)
    assert advance(Door(), power, timeline, 3600) == []
    assert power.stored_wh == pytest.approx(40 - 8 / 0.9)
    assert power.runtime_seconds() == pytest.approx(expected_runtime - 3600)


def test_large_step_crosses_low_shutdown_and_exhaustion_in_order():
    power, timeline, door = Power(mains_available=False), Timeline(), Door()
    events = advance(door, power, timeline, 86400)
    assert [e.type for e in events] == ["battery_low", "battery_critical", "battery_empty"]
    assert [e.simulated_at for e in events] == pytest.approx([12960, 17820, 82620])
    assert power.stored_wh == 0
    assert not power.device_on
    assert door.secured
    assert power.runtime_seconds() == 0
    assert advance(door, power, timeline, 86400) == []


def test_big_and_small_steps_produce_same_energy_and_events():
    large, small = Power(mains_available=False), Power(mains_available=False)
    big_time, small_time = Timeline(), Timeline()
    big_events = advance(Door(), large, big_time, 20000)
    small_events = []
    door = Door()
    for _ in range(2000):
        small_events.extend(advance(door, small, small_time, 10))
    assert small.stored_wh == pytest.approx(large.stored_wh)
    assert [e.type for e in small_events] == [e.type for e in big_events]
    assert [e.simulated_at for e in small_events] == pytest.approx(
        [e.simulated_at for e in big_events],
    )


def test_charge_caps_at_capacity_and_uses_efficiency_once():
    power, timeline = Power(stored_wh=0), Timeline()
    assert advance(Door(), power, timeline, 3600) == []
    assert power.stored_wh == pytest.approx(9)
    events = advance(Door(), power, timeline, 86400)
    assert power.stored_wh == 40
    assert [e.type for e in events] == ["battery_full"]
    assert events[0].simulated_at == pytest.approx(16000)
    assert power.flow_w == 0


def test_power_shutdown_precedes_release_expiry_and_keeps_door_open():
    power = Power(stored_wh=2.001, mains_available=False)
    door, timeline = Door(position="open"), Timeline()
    apply_action(door, "unlock", 0)
    events = advance(door, power, timeline, 3)
    assert [e.type for e in events] == ["battery_critical"]
    assert events[0].simulated_at == pytest.approx(0.2025)
    assert door.position == "open" and door.lock == "pending_close"
    assert door.release_deadline is None


def test_release_expires_before_later_energy_events():
    power, timeline, door = Power(mains_available=False), Timeline(), Door()
    apply_action(door, "unlock", 0)
    events = advance(door, power, timeline, 20000)
    assert [e.type for e in events] == [
        "release_expired", "battery_low", "battery_critical",
    ]
    assert events[0].simulated_at == 3


@pytest.mark.parametrize("changes", [
    {"capacity_wh": 0}, {"normal_load_w": float("nan")}, {"efficiency": 0},
    {"efficiency": float("inf")}, {"economy_load_w": 10}, {"standby_load_w": 4},
])
def test_invalid_energy_parameters_are_rejected(changes):
    with pytest.raises(ValueError):
        PowerConfig(**changes)


def test_zero_standby_load_keeps_reserve_after_shutdown():
    power = Power(config=PowerConfig(standby_load_w=0), mains_available=False)
    events = advance(Door(), power, Timeline(), 86400)
    assert power.stored_wh == 2
    assert [e.type for e in events] == ["battery_low", "battery_critical"]


@pytest.fixture
def lab(tmp_path):
    storage = Storage(tmp_path / "energy.sqlite3")
    real = [100.0]
    controller = Controller(storage, lambda: real[0])
    yield controller, real
    storage.close()


def test_pause_and_step_control_both_release_and_battery(lab):
    controller, real = lab
    controller.set_power(False)
    controller.control_clock(paused=True)
    controller.action("unlock")
    real[0] += 500
    assert controller.status()["door"]["release_remaining_seconds"] == 3
    assert controller.power.stored_wh == 40
    controller.control_clock(advance_seconds=2)
    assert controller.status()["door"]["release_remaining_seconds"] == 1
    assert controller.power.stored_wh == pytest.approx(40 - (8 + 12) / 0.9 * 2 / 3600)
    controller.control_clock(advance_seconds=1)
    assert controller.door.secured


def test_speed_change_does_not_retime_previous_interval(lab):
    controller, real = lab
    real[0] += 2
    controller.control_clock(speed=60)
    real[0] += 1
    assert controller.status()["simulation"]["elapsed_seconds"] == 62
    controller.control_clock(paused=True)
    real[0] += 60
    assert controller.status()["simulation"]["elapsed_seconds"] == 62
    assert controller.control_clock(advance_seconds=3600)[0] == 200
    assert controller.timeline.elapsed_seconds == 3662


def test_step_requires_pause(lab):
    controller, _ = lab
    code, body = controller.control_clock(advance_seconds=3600)
    assert code == 409 and body["code"] == "clock_not_paused"
    assert controller.timeline.elapsed_seconds == 0


def test_manual_access_works_while_powered_off_and_restore_does_not_unlock(lab):
    controller, _ = lab
    controller.control_clock(paused=True)
    controller.set_power(False)
    controller.control_clock(advance_seconds=86400)
    assert controller.status()["device"]["status"] == "powered_off"
    assert controller.action("unlock")[1]["code"] == "device_powered_off"
    for action in ("exit", "close", "key_entry", "close"):
        assert controller.action(action)[0] == 200
    controller.set_power(True)
    assert controller.status()["device"]["status"] == "recovering"
    assert controller.door.secured
    assert controller.action("unlock")[1]["code"] == "device_recovering"
    controller.control_clock(advance_seconds=3600)
    assert controller.power.device_on
    assert controller.power.stored_wh == pytest.approx(9)
    assert controller.door.release_deadline is None


def test_configure_preserves_position_and_clears_release(lab):
    controller, _ = lab
    controller.action("unlock")
    controller.action("open")
    controller.configure_power(PowerConfig(capacity_wh=20), 50)
    assert controller.door.position == "open"
    assert controller.door.release_deadline is None
    assert controller.timeline.paused
    assert controller.power.stored_wh == 10


def test_failed_transaction_does_not_publish_clock_or_power(lab, monkeypatch):
    controller, _ = lab
    controller.control_clock(paused=True)
    controller.set_power(False)
    before = controller.status()

    def fail(*args):
        raise OSError("Disco indisponível")

    monkeypatch.setattr(controller.storage, "save", fail)
    with pytest.raises(OSError):
        controller.control_clock(advance_seconds=20000)
    after = controller.status()
    assert after["power"] == before["power"]
    assert after["simulation"] == before["simulation"]
    assert after["revision"] == before["revision"]


def test_restart_restores_energy_pauses_time_and_never_replays_unlock(tmp_path):
    path = tmp_path / "restart.sqlite3"
    storage = Storage(path)
    controller = Controller(storage, lambda: 100)
    controller.configure_power(PowerConfig(capacity_wh=20), 75)
    controller.set_power(False)
    controller.control_clock(advance_seconds=1000)
    controller.control_clock(speed=600)
    controller.action("unlock")
    previous = replace(controller.power)
    storage.close()
    storage = Storage(path)
    restored = Controller(storage, lambda: 999999)
    assert restored.power == previous
    assert restored.timeline.paused and restored.timeline.speed == 1
    assert restored.timeline.elapsed_seconds == 1000
    assert restored.door.secured
    assert restored.power.mains_available is False
    storage.close()


def test_periodic_checkpoint_saves_charge_without_threshold_event(tmp_path):
    path = tmp_path / "checkpoint.sqlite3"
    real = [0.0]
    storage = Storage(path)
    controller = Controller(storage, lambda: real[0])
    controller.set_power(False)
    real[0] = 10
    controller.tick()
    previous = controller.power.stored_wh
    storage.close()
    storage = Storage(path)
    restored = Controller(storage, lambda: 0)
    assert restored.power.stored_wh == previous
    assert restored.timeline.elapsed_seconds == 10
    storage.close()


def test_old_database_migrates_without_losing_door_or_history(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE door_state (id INTEGER PRIMARY KEY, position TEXT,
                revision INTEGER, updated_at TEXT);
            INSERT INTO door_state VALUES (1, 'open', 8, '2026-09-24T00:00:00Z');
            CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT,
                title TEXT, detail TEXT, source TEXT, outcome TEXT, created_at TEXT);
            INSERT INTO events VALUES
                (1, 'open', 'Porta aberta', 'Evento antigo', 'lab', 'success', '2026-09-24');
        """)
    storage = Storage(path)
    controller = Controller(storage, lambda: 0)
    assert controller.door.position == "open" and controller.door.revision == 9
    assert controller.power.stored_wh == 40
    events = controller.events(10)
    assert events[-1]["title"] == "Porta aberta"
    assert events[-1]["simulated_at"] is None
    storage.close()


def test_actuator_extra_stops_at_expiry_and_prediction_includes_it():
    power, door, timeline = Power(mains_available=False), Door(), Timeline()
    apply_action(door, "unlock", 0)
    runtime = estimated_runtime(door, power, timeline)
    events = advance(door, power, timeline, runtime)
    assert events[-1].type == "battery_critical"
    assert runtime == pytest.approx(17815.5)
    assert power.stored_wh == pytest.approx(2)
    assert not power.device_on


def test_current_peak_prediction_handles_shutdown_before_expiry():
    power = Power(stored_wh=2.001, mains_available=False)
    door, timeline = Door(), Timeline()
    apply_action(door, "unlock", 0)
    assert estimated_runtime(door, power, timeline) == pytest.approx(0.2025)
    assert door.release_deadline == 3 and power.device_on


def test_recovery_requires_two_virtual_seconds(lab):
    controller, _ = lab
    controller.configure_power(PowerConfig(), 0)
    controller.set_power(False)
    controller.set_power(True)
    assert controller.status()["device"]["status"] == "recovering"
    controller.control_clock(advance_seconds=1.999)
    assert not controller.power.device_on
    controller.control_clock(advance_seconds=0.001)
    assert controller.power.device_on and controller.door.secured
    assert any(e["type"] == "device_recovered" for e in controller.events(10))


def test_power_loss_during_recovery_cannot_complete_boot(lab):
    controller, _ = lab
    controller.configure_power(PowerConfig(), 0)
    controller.set_power(False)
    controller.set_power(True)
    controller.control_clock(advance_seconds=1)
    controller.set_power(False)
    controller.control_clock(advance_seconds=3)
    assert controller.status()["device"]["status"] == "powered_off"
    assert controller.power.recovery_deadline is None
    assert controller.door.secured
