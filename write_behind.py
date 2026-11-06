"""
write_behind.py — background, coalescing writer for student progress autosaves.

Why: `student_store.save()` is a synchronous Dropbox upload (typically a few
hundred ms). The app autosaves after nearly every Act 2 answer, so each answer
used to block that student's page until Dropbox replied — and with 30–40
students the uploads queue up behind Dropbox's rate limit.

How: the page now hands the snapshot to this module and returns immediately.
A small pool of daemon threads uploads it in the background.

Guarantees
  * Latest wins per student: if a student produces several snapshots while an
    upload is in flight, only the newest is uploaded next (older ones are
    dropped, they would be overwritten anyway).
  * Per-student ordering: a student's key is never uploaded by two workers at
    once, so an older snapshot can never land after a newer one.
  * cancel(key) drops a pending snapshot and waits for an in-flight one, so a
    caller that then writes synchronously (restart → blank record, or the
    explicit "Save progress" button) is guaranteed to be the last writer.

This lives in its own module (not in the Streamlit script) because the main
script is re-executed on every rerun; an imported module keeps one queue and one
worker pool per server process.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Hashable


class WriteBehind:
    def __init__(self, write_fn: Callable[[Hashable, Any], None], workers: int = 4):
        self._write = write_fn
        self._cv = threading.Condition()
        self._pending: dict = {}          # key -> latest payload (insertion-ordered)
        self._inflight: set = set()
        self._n_workers = workers
        self._started = False
        self.failed: set = set()          # keys whose most recent write raised

    def _ensure_started(self):
        if self._started:
            return
        with self._cv:
            if self._started:
                return
            for i in range(self._n_workers):
                threading.Thread(target=self._loop, name=f"autosave-{i}", daemon=True).start()
            self._started = True

    def submit(self, key: Hashable, payload: Any) -> None:
        self._ensure_started()
        with self._cv:
            self._pending.pop(key, None)  # re-insert at the back (fair FIFO across students)
            self._pending[key] = payload
            self._cv.notify()

    def cancel(self, key: Hashable, timeout: float = 30.0) -> None:
        """Drop any pending write for key and wait for an in-flight one to finish."""
        with self._cv:
            self._pending.pop(key, None)
            self._cv.wait_for(lambda: key not in self._inflight, timeout=timeout)

    def flush(self, key: Hashable | None = None, timeout: float = 30.0) -> bool:
        """Wait until key (or everything, if None) has been written."""
        with self._cv:
            if key is None:
                pred = lambda: not self._pending and not self._inflight
            else:
                pred = lambda: key not in self._pending and key not in self._inflight
            return self._cv.wait_for(pred, timeout=timeout)

    def _next_key(self):
        for k in self._pending:
            if k not in self._inflight:
                return k
        return None

    def _loop(self):
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._next_key() is not None)
                key = self._next_key()
                payload = self._pending.pop(key)
                self._inflight.add(key)
            try:
                self._write(key, payload)
                self.failed.discard(key)
            except Exception:              # best-effort, same as the old inline autosave,
                self.failed.add(key)       # but remembered so the caller can retry
            finally:
                with self._cv:
                    self._inflight.discard(key)
                    self._cv.notify_all()
