from concurrent.futures import ThreadPoolExecutor

import pytest

from everlock.controller import Controller
from everlock.storage import Storage


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def test_server_expiry_without_browser(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    clock = FakeClock()
    controller = Controller(storage, clock)
    controller.action("unlock")
    clock.value += 3
    controller.tick()
    assert controller.door.secured
    assert controller.events(5)[0]["type"] == "release_expired"
    storage.close()


@pytest.mark.parametrize("opened", [False, True])
def test_restart_preserves_position_but_never_restores_release(tmp_path, opened):
    path = tmp_path / "test.sqlite3"
    storage = Storage(path)
    controller = Controller(storage, FakeClock())
    controller.action("unlock")
    if opened:
        controller.action("open")
    previous_revision = controller.status()["revision"]
    storage.close()

    storage = Storage(path)
    restored = Controller(storage, FakeClock())
    status = restored.status()
    assert status["door"]["position"] == ("open" if opened else "closed")
    assert status["door"]["lock"] == ("pending_close" if opened else "engaged")
    assert status["door"]["release_remaining_seconds"] == 0
    assert status["revision"] > previous_revision
    assert len(restored.events(100)) == (4 if opened else 3)
    storage.close()


def test_simultaneous_unlocks_have_only_one_success(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    controller = Controller(storage, FakeClock())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: controller.action("unlock"), range(16)))
    assert sum(code == 200 for code, _ in results) == 1
    assert sum(code == 409 for code, _ in results) == 15
    assert len(controller.events(100)) == 17
    storage.close()


def test_failed_persistence_does_not_publish_unlock(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "test.sqlite3")
    controller = Controller(storage, FakeClock())

    def fail(*args):
        raise OSError("Disco indisponível")

    monkeypatch.setattr(storage, "save", fail)
    with pytest.raises(OSError):
        controller.action("unlock")
    assert controller.door.secured
    storage.close()


@pytest.mark.parametrize("instant, expected", [(102.999, 200), (103.0, 409), (103.001, 409)])
def test_entry_at_release_deadline(tmp_path, instant, expected):
    storage = Storage(tmp_path / "boundary.sqlite3")
    clock = FakeClock()
    controller = Controller(storage, clock)
    controller.action("unlock")
    clock.value = instant
    code, _ = controller.action("open")
    assert code == expected
    if expected == 409:
        assert controller.door.secured
    storage.close()
