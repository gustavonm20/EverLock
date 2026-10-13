import json
import sqlite3
import threading
import time

from everlock.notifications import DeliveryError
from everlock.outbox import DurableNotifier


def test_pending_survives_restart_with_same_id_and_no_personal_data(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    attempted = threading.Event()
    received = []

    def offline(body):
        attempted.set()
        raise DeliveryError("offline", True)

    first = DurableNotifier(path, "http://localhost/test", sender=offline,
                            retry_delays=(0.4, 0.4))
    assert first.publish("mains_lost", "Nome pessoal", "Imagem base64 privada", actor="pessoa")
    assert attempted.wait(2)
    first.close()
    with sqlite3.connect(path) as db:
        stored = db.execute("SELECT body, attempts FROM notification_outbox").fetchone()
    assert stored[1] == 1
    assert not any(word in stored[0].decode() for word in ("Nome pessoal", "base64", "pessoa"))
    second = DurableNotifier(path, "http://localhost/test", sender=received.append,
                             retry_delays=(0.4, 0.4))
    try:
        assert second.flush(3)
        assert len(received) == 1
        assert json.loads(received[0])["id"] == json.loads(stored[0])["id"]
        assert second.status()["sent"] == 1
    finally:
        second.close()


def test_changed_destination_and_expired_notifications_are_not_replayed(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    first = DurableNotifier(path, "http://localhost/original", sender=lambda _: None)
    first.close()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO notification_outbox VALUES (?,?,?,?,?,0)",
                   ("old", first.destination_key, b"{}", time.time() + 60, 0))
        db.execute("INSERT INTO notification_outbox VALUES (?,?,?,?,?,0)",
                   ("expired", first.destination_key, b"{}", time.time() - 1, 0))
    received = []
    second = DurableNotifier(path, "http://localhost/new", sender=received.append)
    try:
        assert second.flush() and received == []
    finally:
        second.close()


def test_retry_budget_survives_restart_and_bad_storage_does_not_raise(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    first = DurableNotifier(path, "http://localhost/a", sender=lambda _: None, retry_delays=())
    first.close()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO notification_outbox VALUES (?,?,?,?,?,1)",
                   ("spent", first.destination_key, b"{}", time.time() + 60, 0))
    received = []
    second = DurableNotifier(path, "http://localhost/a", sender=received.append, retry_delays=())
    try:
        assert second.flush() and received == [] and second.status()["failed"] == 1
    finally:
        second.close()
    broken = DurableNotifier(tmp_path, "http://localhost/a")
    assert broken.publish("mains_lost", "t", "d") is False
    assert not broken.status()["configured"]


def test_capacity_includes_inflight_and_rejects_new_without_losing_accepted_event(tmp_path):
    entered, release = threading.Event(), threading.Event()
    received = []

    def waiting_sender(body):
        received.append(json.loads(body)["id"])
        entered.set()
        assert release.wait(3)

    notifier = DurableNotifier(tmp_path / "bounded.sqlite3", "http://localhost/a",
                               sender=waiting_sender, queue_size=1)
    try:
        assert notifier.publish("mains_lost", "t", "d")
        assert entered.wait(2)
        assert not notifier.publish("mains_lost", "t", "d")
        assert notifier.status()["queued"] == 1 and notifier.status()["dropped"] == 1
        assert not notifier.flush(0.01)
        release.set()
        assert notifier.flush(2) and len(received) == 1
        assert notifier.publish("mains_lost", "t", "d")
        assert notifier.flush(2) and len(received) == 2
        assert received[0] != received[1]
    finally:
        release.set()
        notifier.close()


def test_failed_write_rolls_back_purge_without_corrupting_pending_count(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def waiting_sender(_body):
        entered.set()
        assert release.wait(3)

    notifier = DurableNotifier(tmp_path / "rollback.sqlite3", "http://localhost/a",
                               sender=waiting_sender, queue_size=3)
    try:
        assert notifier.publish("mains_lost", "t", "d")
        assert entered.wait(2)
        with notifier.lock, notifier.db:
            notifier.db.execute("INSERT INTO notification_outbox VALUES (?,?,?,?,?,0)",
                                ("expired", notifier.destination_key, b"{}", time.time() - 1, 0))
            notifier.pending += 1
            notifier.db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON notification_outbox "
                                "BEGIN SELECT RAISE(ROLLBACK, 'injected'); END")
        assert not notifier.publish("mains_lost", "t", "d")
        with notifier.lock:
            count = notifier.db.execute("SELECT count(*) FROM notification_outbox").fetchone()[0]
            assert count == 2
            assert notifier.pending == 2
            assert notifier.dropped == 1  # A purga não foi confirmada: não é descarte ainda.
            notifier.db.execute("DROP TRIGGER fail_insert")
        release.set()
        assert notifier.flush(2)
        assert notifier.status()["sent"] == 1
        assert notifier.status()["dropped"] == 2
    finally:
        release.set()
        notifier.close()
