from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from everlock.ups import UPSMonitor, UPSObservation


def test_unconfigured_has_no_fabricated_measurements():
    monitor = UPSMonitor()
    state = monitor.snapshot()
    assert state["source"] == "real_ups" and state["status"] == "not_configured"
    assert state["observation"] is None and not state["controls_available"]


def test_readings_age_on_real_time_and_keep_unknown_fields():
    now = [1000.0]
    monitor = UPSMonitor(clock=lambda: now[0])
    monitor.receive(UPSObservation(observed_at=datetime.fromtimestamp(now[0], UTC),
                                   external_power=False))
    assert monitor.snapshot()["status"] == "available"
    assert monitor.snapshot()["observation"]["battery_percent"] is None
    now[0] += 15
    assert monitor.snapshot()["status"] == "stale"
    monitor.unavailable()
    assert monitor.snapshot()["status"] == "unavailable"
    assert monitor.snapshot()["observation"] is not None


def test_out_of_order_and_invalid_ups_data_are_not_accepted():
    monitor = UPSMonitor(clock=lambda: 1000)
    latest = UPSObservation(observed_at=datetime.fromtimestamp(1000, UTC), battery_percent=50)
    monitor.receive(latest)
    monitor.receive(UPSObservation(
        observed_at=datetime.fromtimestamp(990, UTC), battery_percent=90,
    ))
    assert monitor.snapshot()["observation"]["battery_percent"] == 50
    with pytest.raises(ValueError):
        monitor.receive(UPSObservation(observed_at=datetime.fromtimestamp(1100, UTC)))
    with pytest.raises(ValidationError):
        UPSObservation(observed_at=datetime.now(UTC), battery_percent=101)
    with pytest.raises(ValidationError):
        UPSObservation(observed_at=datetime.now(UTC), runtime_seconds=float("nan"))
