# Concurrency load test

Simulates N students playing the whole game at once against a **local** server.
Do not point it at the production Community Cloud app.

```bash
pip install -r requirements.txt psutil websockets
python tools/loadtest/runload.py "$PWD" 40 results_40.json 3   # app dir, users, out, weeks
```

- `runload.py` starts `streamlit run juicetification.py` pinned to **one CPU core**
  (Community Cloud's allocation is not published precisely; one core is a
  conservative stand-in), samples server CPU and memory, and runs the client on
  another core.
- `loadclient.py` opens one real WebSocket session per student and speaks
  Streamlit's own protocol (the same messages the browser sends: full widget
  state on each rerun, button triggers, form widgets only on submit). Each
  student plays Act 1 → Funnel → Act 2 (one answer at a time, including one
  wrong entry) → Act 3 (3 weeks, including an Excel download each week), with
  0.5–1.5 s of "think time" between actions and a staggered 0–5 s start.
- `fakedbx/` is a stand-in for the `dropbox` package so progress saving is
  exercised without real credentials: an in-memory store with a fixed simulated
  network delay per call (`FAKE_DBX_LATENCY_MS`, default 300 ms). Every call is
  logged so uploads can be counted.

Latency is measured from sending an interaction to the server reporting the
script run finished, so animation interactions include the intentional
animation delay (Normal speed: 24 frames × 0.11 s ≈ 2.6 s for a week chart).
