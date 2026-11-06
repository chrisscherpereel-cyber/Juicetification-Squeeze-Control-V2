"""Start the app under `streamlit run` (pinned to ONE CPU core, storage enabled
against the latency-simulating Dropbox double), drive N simulated students with
loadclient.py (on the other core), and sample server CPU / RSS throughout.

usage: python runload.py <app_dir> <users> <out.json> [weeks] [dbx_latency_ms]
"""
import json, os, subprocess, sys, time, threading, psutil, signal

app, users, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
weeks = int(sys.argv[4]) if len(sys.argv) > 4 else 3
lat_ms = sys.argv[5] if len(sys.argv) > 5 else "300"
port = 8600 + users
here = os.path.dirname(os.path.abspath(__file__))
log = f"/tmp/fakedbx_{users}_{os.path.basename(app)}.log"
if os.path.exists(log):
    os.remove(log)
env = dict(os.environ,
           PYTHONPATH=os.path.join(here, "fakedbx"),
           DB_ENCRYPTION_KEY="kU0y3sd0yC1Qf1JX8Z2b1v4b0r9yFQh8Jf2p7Tq5o1M=",
           DROPBOX_ACCESS_TOKEN="fake", FAKE_DBX_LATENCY_MS=lat_ms, FAKE_DBX_LOG=log)
srv = subprocess.Popen(
    ["taskset", "-c", "0", sys.executable, "-m", "streamlit", "run",
     os.path.join(app, "juicetification.py"), "--server.port", str(port),
     "--server.headless", "true", "--server.enableXsrfProtection", "false",
     "--server.enableCORS", "false", "--browser.gatherUsageStats", "false"],
    cwd=app, env=env, stdout=subprocess.DEVNULL, stderr=open(f"/tmp/srv_{users}.err", "w"))
proc = psutil.Process(srv.pid)
# wait for health
import urllib.request
t0 = time.time()
while True:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1); break
    except Exception:
        if time.time() - t0 > 60: raise SystemExit("server did not start")
        time.sleep(0.3)
startup_s = time.time() - t0

samples, stop = [], threading.Event()
def sampler():
    proc.cpu_percent(None)
    while not stop.is_set():
        time.sleep(0.5)
        try:
            samples.append((proc.cpu_percent(None), proc.memory_info().rss / 2**20))
        except psutil.Error:
            break
rss_idle = proc.memory_info().rss / 2**20
th = threading.Thread(target=sampler, daemon=True); th.start()
cl = subprocess.run(["taskset", "-c", "1", sys.executable, os.path.join(here, "loadclient.py"),
                     "--users", str(users), "--port", str(port), "--app-dir", app,
                     "--weeks", str(weeks), "--out", out + ".client"],
                    env=dict(os.environ, PYTHONPATH=os.path.join(here, "fakedbx")),
                    capture_output=True, text=True)
stop.set(); th.join()
rss_end = proc.memory_info().rss / 2**20
srv.send_signal(signal.SIGTERM); srv.wait(timeout=20)
res = json.load(open(out + ".client")) if os.path.exists(out + ".client") else {"client_err": cl.stderr[-2000:]}
cpus = [c for c, _ in samples]
ops = [l.split("\t")[1] for l in open(log)] if os.path.exists(log) else []
res.update(server_startup_s=startup_s, rss_idle_mb=rss_idle, rss_peak_mb=max(r for _, r in samples),
           rss_end_mb=rss_end, cpu_mean_pct=sum(cpus) / len(cpus),
           cpu_p95_pct=sorted(cpus)[int(0.95 * (len(cpus) - 1))],
           cpu_busy_frac=sum(1 for c in cpus if c > 90) / len(cpus),
           dropbox_uploads=ops.count("upload"), dropbox_downloads=ops.count("download"))
json.dump(res, open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "by_category"}, indent=1))
for c, v in res.get("by_category", {}).items():
    print(f"  {c:24s} n={v['n']:4d} p50={v['p50']*1000:7.0f}ms p95={v['p95']*1000:7.0f}ms max={v['max']*1000:7.0f}ms")
