import pytest

from everlock.domain import Denied, Door, apply_action, expire


def test_initial_state_is_closed_and_engaged():
    door = Door()
    assert door.secured
    assert door.lock == "engaged"


def test_external_entry_denied_when_locked():
    door = Door()
    with pytest.raises(Denied, match="Acesso negado"):
        apply_action(door, "open", 0)
    assert door.secured


def test_external_entry_rejects_an_elapsed_release():
    door = Door()
    apply_action(door, "unlock", 100)
    with pytest.raises(Denied, match="Acesso negado"):
        apply_action(door, "open", 103.001)
    assert door.position == "closed"


def test_release_does_not_open_door_and_expires_at_boundary():
    door = Door()
    apply_action(door, "unlock", 10)
    assert door.position == "closed"
    assert door.lock == "released"
    assert not door.secured
    assert expire(door, 12.999) is None
    assert expire(door, 13) is not None
    assert door.secured
    assert expire(door, 14) is None


def test_open_door_never_reports_engaged_after_expiry():
    door = Door()
    apply_action(door, "unlock", 10)
    apply_action(door, "open", 11)
    expire(door, 13)
    assert door.position == "open"
    assert door.lock == "pending_close"
    assert not door.secured
    apply_action(door, "close", 14)
    assert door.secured


def test_end_release_does_not_close_door():
    door = Door()
    apply_action(door, "unlock", 0)
    apply_action(door, "open", 1)
    apply_action(door, "end_release", 2)
    assert door.position == "open"
    assert door.lock == "pending_close"


@pytest.mark.parametrize("manual_action", ["exit", "key_entry"])
def test_manual_access_bypasses_locked_state(manual_action):
    door = Door()
    event = apply_action(door, manual_action, 0)
    assert door.position == "open"
    assert door.lock == "pending_close"
    assert event.source == "manual"


def test_duplicate_unlock_cannot_extend_release():
    door = Door()
    apply_action(door, "unlock", 0)
    with pytest.raises(Denied):
        apply_action(door, "unlock", 2)
    assert door.release_deadline == 3


def test_closing_during_release_does_not_claim_secured():
    door = Door()
    apply_action(door, "unlock", 0)
    apply_action(door, "open", 1)
    apply_action(door, "close", 2)
    assert door.position == "closed"
    assert door.lock == "released"
    assert not door.secured


@pytest.mark.parametrize("action", ["close", "end_release"])
def test_inapplicable_action_is_rejected(action):
    with pytest.raises(Denied):
        apply_action(Door(), action, 0)
