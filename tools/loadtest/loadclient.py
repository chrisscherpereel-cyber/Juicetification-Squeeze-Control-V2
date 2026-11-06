"""Streamlit-protocol load client for Juicetification: Squeeze Control.

Each simulated student opens a real WebSocket session (/_stcore/stream), speaks
Streamlit's BackMsg/ForwardMsg protobuf protocol exactly like the browser does
(full widget-state snapshots on every rerun, triggers for buttons, form widgets
only sent on submit), and plays the whole game: Act 1 -> Funnel -> Act 2 (every
answer entered one field at a time) -> Act 3 (N weeks, incl. Excel download) ->
Results. It records the latency of every interaction (send rerun -> script
finished) and the bytes received.

usage: python loadclient.py --users 10 --port 8501 --app-dir <repo> --out res.json
"""
import argparse, asyncio, json, os, random, sys, time, statistics as S, urllib.request

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.WidgetStates_pb2 import WidgetState
import websockets

GAME = "LOADTEST"


class Session:
    def __init__(self, idx, port, query, think):
        self.idx, self.port, self.query, self.think = idx, port, query, think
        self.widgets = {}        # id -> persisted WidgetState (value widgets)
        self.elements = []       # (kind, proto) from the latest run
        self.lat = []            # (category, seconds)
        self.bytes = 0
        self.errors = []
        self.page_hash = ""

    async def connect(self):
        self.ws = await websockets.connect(
            f"ws://127.0.0.1:{self.port}/_stcore/stream",
            subprotocols=["streamlit"], max_size=None, open_timeout=60, ping_interval=None)

    async def rerun(self, category, trigger=None):
        msg = BackMsg()
        cs = msg.rerun_script
        cs.query_string = self.query
        cs.page_script_hash = self.page_hash
        for ws_ in self.widgets.values():
            cs.widget_states.widgets.append(ws_)
        if trigger is not None:
            t = cs.widget_states.widgets.add(); t.id = trigger; t.trigger_value = True
        t0 = time.perf_counter()
        await self.ws.send(msg.SerializeToString())
        self.elements = []
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=180)
            self.bytes += len(raw)
            fm = ForwardMsg(); fm.ParseFromString(raw)
            kind = fm.WhichOneof("type")
            if kind == "new_session":
                self.page_hash = fm.new_session.page_script_hash or self.page_hash
            elif kind == "delta" and fm.delta.WhichOneof("type") == "new_element":
                el = fm.delta.new_element
                ek = el.WhichOneof("type")
                self.elements.append((ek, getattr(el, ek)))
                if ek == "exception":
                    self.errors.append(el.exception.message)
            elif kind == "script_finished":
                # 0 = finished successfully, 1 = compile error, 2 = rerun, 3 = fragment
                if fm.script_finished in (0, 1):
                    break
        self.lat.append((category, time.perf_counter() - t0))
        if self.think:
            await asyncio.sleep(random.uniform(*self.think))

    # --- element helpers ----------------------------------------------------
    def find(self, kind, label_start):
        for k, p in reversed(self.elements):
            if k == kind and getattr(p, "label", "").startswith(label_start):
                return p
        raise LookupError(f"{kind} '{label_start}' not on page")

    async def click(self, label, category):
        p = self.find("button", label)
        await self.rerun(category, trigger=p.id)

    async def set_value(self, kind, label, field, value, category, form=False):
        p = self.find(kind, label)
        w = WidgetState(); w.id = p.id
        if field == "string_array_value":
            w.string_array_value.data.extend(value)
        else:
            setattr(w, field, value)
        self.widgets[p.id] = w
        if not (form or getattr(p, "form_id", "")):
            await self.rerun(category)

    def download_urls(self):
        return [p.url for k, p in self.elements if k == "download_button" and p.url]


def expected(seed):
    """Recompute the student's baseline answers from the same seeded stream."""
    import numpy as np
    import juicetification as J
    rng = np.random.default_rng(seed)
    sub, pc = J.clean_baseline(5, 200, rng)
    lim = J.xbar_r_limits(sub)
    plim = J.p_chart_limits(pc, 200)
    return lim, plim


async def play(idx, args):
    import student_store
    sid = f"s{idx:03d}"
    seed = student_store.derive_seed(GAME, sid, lo=1, hi=10 ** 6)
    lim, plim = expected(seed)
    s = Session(idx, args.port, f"sid={sid}&game={GAME}", tuple(args.think) if args.think[1] else None)
    t_start = time.perf_counter()
    try:
        await asyncio.sleep(random.uniform(0, args.ramp))
        await s.connect()
        await s.rerun("page_load")
        await s.click("🏭 Run", "act1_animation")
        await s.click("➡️ Next", "navigate")
        await s.set_value("radio", "**Predict:**", "string_value", "Less consistent", "interact")
        await s.click("⏩ Auto-run 10 (adjust each)", "funnel_animation")
        await s.click("⏩ Auto-run 10 (leave each)", "funnel_animation")
        await s.click("➡️ Proceed", "navigate")
        # Act 2 — one field at a time, like a student typing + Enter
        await s.set_value("radio", "Fill volume", "string_value", "X-bar & R chart", "act2_answer")
        await s.set_value("radio", "Defective bottles", "string_value", "p-chart", "act2_answer")
        await s.set_value("radio", "**Sample size (n)**", "string_value", "5 bottles in each sample", "act2_answer")
        await s.set_value("radio", "**Number of samples (k)**", "string_value", "24 samples (one per shift)", "act2_answer")
        await s.set_value("radio", "What is the **sample size", "string_value", "200", "act2_answer")
        # one wrong entry first (realistic), then the right ones
        await s.set_value("number_input", "X̄̄ — grand mean", "double_value", 250.0, "act2_answer")
        await s.set_value("number_input", "X̄̄ — grand mean", "double_value", round(lim["xbarbar"], 2), "act2_answer")
        await s.set_value("number_input", "R̄ — mean range", "double_value", round(lim["rbar"], 2), "act2_answer")
        await s.set_value("number_input", "p̄ — mean fraction", "double_value", round(plim["pbar"], 3), "act2_answer")
        if s.download_urls():
            await fetch(s, s.download_urls()[-1], args.port)
        await s.set_value("selectbox", "A₂", "string_value", "0.577", "act2_answer")
        await s.set_value("selectbox", "D₃", "string_value", "0.000", "act2_answer")
        await s.set_value("selectbox", "D₄", "string_value", "2.114", "act2_answer")
        for lbl, v in [("UCL X̄", lim["ucl_x"]), ("LCL X̄", lim["lcl_x"]), ("UCL R", lim["ucl_r"]),
                       ("LCL R", lim["lcl_r"]), ("UCL p", plim["ucl"]), ("LCL p", plim["lcl"])]:
            await s.set_value("number_input", lbl, "double_value",
                              round(v, 3 if "p" in lbl.split()[1] else 2), "act2_answer")
        await s.click("✅ Certify", "act3_animation")
        for wk in range(args.weeks):
            if s.download_urls():
                await fetch(s, s.download_urls()[-1], args.port)
            await s.set_value("multiselect", "X-bar signals", "string_array_value",
                              ["Point beyond the limits"], "act3_pick")
            await s.set_value("multiselect", "p signals", "string_array_value", [], "act3_pick")
            sub = None
            for k, p in s.elements:
                if k == "button" and p.label.startswith("🔍 Submit"):
                    sub = p
            await s.rerun("act3_reveal_animation", trigger=sub.id)
            await s.set_value("radio", "Choose one:", "string_value",
                              s.find("radio", "Choose one:").options[0], "interact")
            if wk < args.weeks - 1:
                await s.click("▶️ Next production week", "act3_animation")
        s.result_ok = any(k == "button" and p.label.startswith("🏁") for k, p in s.elements) or args.weeks < 10
        await s.ws.close()
    except Exception as e:  # noqa
        s.errors.append(f"{type(e).__name__}: {e}")
    s.total = time.perf_counter() - t_start
    return s


async def fetch(s, url, port):
    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, lambda: urllib.request.urlopen(
        f"http://127.0.0.1:{port}{url}", timeout=60).read())
    s.bytes += len(data)
    s.lat.append(("download_fetch", time.perf_counter() - t0))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else float("nan")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=1)
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--app-dir", required=True)
    ap.add_argument("--weeks", type=int, default=3)
    ap.add_argument("--ramp", type=float, default=5.0)
    ap.add_argument("--think", type=float, nargs=2, default=[0.5, 1.5])
    ap.add_argument("--out")
    args = ap.parse_args()
    sys.path.insert(0, args.app_dir)
    import logging, warnings; logging.disable(logging.CRITICAL); warnings.filterwarnings("ignore")
    sessions = await asyncio.gather(*(play(i, args) for i in range(args.users)))
    cats = {}
    for s in sessions:
        for c, t in s.lat:
            cats.setdefault(c, []).append(t)
    allint = [t for s in sessions for c, t in s.lat]
    res = {
        "users": args.users,
        "errors": [e for s in sessions for e in s.errors][:20],
        "sessions_failed": sum(1 for s in sessions if s.errors),
        "total_interactions": len(allint),
        "bytes_per_session_kb": S.mean(s.bytes for s in sessions) / 1024,
        "session_wall_s": S.mean(s.total for s in sessions),
        "by_category": {c: {"n": len(v), "mean": S.mean(v), "p50": pct(v, 50), "p95": pct(v, 95),
                            "max": max(v)} for c, v in sorted(cats.items())},
    }
    print(json.dumps(res, indent=1))
    if args.out:
        json.dump(res, open(args.out, "w"), indent=1)

if __name__ == "__main__":
    asyncio.run(main())
