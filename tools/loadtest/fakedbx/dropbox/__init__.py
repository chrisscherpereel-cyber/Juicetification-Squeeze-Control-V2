"""Test double for the `dropbox` SDK: in-memory store with simulated network latency.
Latency per call = FAKE_DBX_LATENCY_MS (default 300). Counts calls in a shared file."""
import os, time, threading
from . import exceptions, files
_LAT = float(os.environ.get("FAKE_DBX_LATENCY_MS", "300")) / 1000.0
_STORE = {}
_LOCK = threading.Lock()
_LOG = os.environ.get("FAKE_DBX_LOG", "/tmp/fakedbx.log")
def _log(op, path, n=0):
    with _LOCK, open(_LOG, "a") as f:
        f.write(f"{time.time():.3f}\t{op}\t{path}\t{n}\n")
class _Res:
    def __init__(self, c): self.content = c
class Dropbox:
    def __init__(self, *a, **k): pass
    def files_upload(self, data, path, mode=None):
        time.sleep(_LAT); _log("upload", path, len(data))
        with _LOCK: _STORE[path] = bytes(data)
    def files_download(self, path):
        time.sleep(_LAT); _log("download", path)
        with _LOCK:
            if path not in _STORE:
                raise exceptions.ApiError("not_found")
            return None, _Res(_STORE[path])
    def files_list_folder(self, folder):
        raise exceptions.ApiError("nf")
