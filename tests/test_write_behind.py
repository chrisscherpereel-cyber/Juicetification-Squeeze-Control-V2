import threading
import time

from write_behind import WriteBehind


def test_latest_wins_and_order_per_key():
    writes, lock = [], threading.Lock()

    def slow(key, payload):
        time.sleep(0.05)
        with lock:
            writes.append((key, payload))

    wb = WriteBehind(slow, workers=4)
    for i in range(20):                      # 20 quick snapshots from one student
        wb.submit("s1", i)
    assert wb.flush("s1", timeout=5)
    seq = [p for k, p in writes if k == "s1"]
    assert seq == sorted(seq)                # never out of order
    assert seq[-1] == 19                     # the newest snapshot is what's stored
    assert len(seq) < 20                     # intermediate ones coalesced away


def test_keys_never_written_concurrently():
    active, peak, lock = {}, {}, threading.Lock()

    def w(key, payload):
        with lock:
            active[key] = active.get(key, 0) + 1
            peak[key] = max(peak.get(key, 0), active[key])
        time.sleep(0.01)
        with lock:
            active[key] -= 1

    wb = WriteBehind(w, workers=6)
    for i in range(200):
        wb.submit(f"s{i % 5}", i)
    assert wb.flush(timeout=10)
    assert max(peak.values()) == 1


def test_cancel_then_sync_write_is_last():
    """restart_game: cancel pending autosave, then write the blank record — the
    blank record must be the final state even if an upload was in flight."""
    store, lock = {}, threading.Lock()
    started = threading.Event()

    def w(key, payload):
        started.set()
        time.sleep(0.2)
        with lock:
            store[key] = payload

    wb = WriteBehind(w, workers=2)
    wb.submit("s1", "old-1")
    started.wait(2)                          # old-1 is now in flight
    wb.submit("s1", "old-2")                 # and old-2 pending
    wb.cancel("s1")                          # drops old-2, waits for old-1
    with lock:
        store["s1"] = "BLANK"                # synchronous reset
    time.sleep(0.4)
    assert store["s1"] == "BLANK"


def test_write_errors_are_swallowed():
    calls = []

    def boom(key, payload):
        calls.append(payload)
        raise RuntimeError("dropbox down")

    wb = WriteBehind(boom, workers=1)
    wb.submit("a", 1)
    assert wb.flush(timeout=2)
    wb.submit("a", 2)                        # worker survived the error
    assert wb.flush(timeout=2)
    assert calls == [1, 2]


def test_failed_keys_are_tracked_for_retry():
    ok = {"v": False}

    def flaky(key, payload):
        if not ok["v"]:
            raise RuntimeError("429")

    wb = WriteBehind(flaky, workers=1)
    wb.submit("a", 1); wb.flush(timeout=2)
    assert "a" in wb.failed                  # autosave() will re-submit an unchanged snapshot
    ok["v"] = True
    wb.submit("a", 1); wb.flush(timeout=2)
    assert "a" not in wb.failed
