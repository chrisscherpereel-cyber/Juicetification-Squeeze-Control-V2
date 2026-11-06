"""End-to-end regression: play the whole game headlessly (Streamlit AppTest),
with and without the (faked) progress store, and check session isolation."""
import os

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

import student_store
import juicetification as J

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "juicetification.py")


def _btn(at, prefix):
    for b in list(at.button) + list(getattr(at, "form_submit_button", [])):
        if b.label.startswith(prefix):
            return b
    raise LookupError(prefix)


def _click(at, prefix):
    _btn(at, prefix).click().run(timeout=60)
    assert not at.exception, [e.message for e in at.exception]


def _by_label(seq, prefix):
    return next(w for w in seq if w.label.startswith(prefix))


def play(at, seed, weeks=5):
    """Act 1 → Funnel → Act 2 (computing every answer) → Act 3 → Results."""
    at.sidebar.select_slider[0].set_value("⚡ Instant").run(timeout=60)
    _click(at, "🏭 Run")
    _click(at, "➡️ Next")
    _by_label(at.radio, "**Predict:**").set_value("Less consistent").run()
    _click(at, "⏩ Auto-run 10 (adjust each)")
    _click(at, "➡️ Proceed")
    ss = at.session_state
    lim, plim = J.xbar_r_limits(ss.baseline), J.p_chart_limits(ss.p_baseline, ss.p_inspect)
    n = ss.sub_n
    kf = J.SPC_CONSTANTS[n]
    _by_label(at.radio, "Fill volume").set_value("X-bar & R chart").run()
    _by_label(at.radio, "Defective bottles").set_value("p-chart").run()
    _by_label(at.radio, "**Sample size (n)**").set_value(f"{n} bottles in each sample").run()
    _by_label(at.radio, "**Number of samples (k)**").set_value("24 samples (one per shift)").run()
    _by_label(at.radio, "What is the **sample size").set_value(str(ss.p_inspect)).run()
    at.number_input(key="cl_x").set_value(round(lim["xbarbar"], 2)).run()
    at.number_input(key="cl_r").set_value(round(lim["rbar"], 2)).run()
    at.number_input(key="cl_p").set_value(round(plim["pbar"], 3)).run()
    if hasattr(at, "download_button"):            # AppTest API in newer Streamlit only
        assert len(at.download_button) >= 2       # raw-data CSV + Excel offered
    at.selectbox(key="sel_a2").set_value(kf["A2"]).run()
    at.selectbox(key="sel_d3").set_value(kf["D3"]).run()
    at.selectbox(key="sel_d4").set_value(kf["D4"]).run()
    for key, v in [("c_ux", lim["ucl_x"]), ("c_lx", lim["lcl_x"]), ("c_ur", lim["ucl_r"]),
                   ("c_lr", lim["lcl_r"]), ("c_up", plim["ucl"]), ("c_lp", plim["lcl"])]:
        at.number_input(key=key).set_value(round(v, 3 if key.endswith("p") else 2)).run()
    _click(at, "✅ Certify")
    assert at.session_state.phase == 4
    for wk in range(weeks):
        at.multiselect(key="pick_x").set_value(["beyond_limits"])
        _click(at, "🔍 Submit")                      # form submit: picks applied here
        assert at.session_state.answered
        assert at.session_state.picks["x"] == {"beyond_limits"}
        at.radio(key=f"ocap_{wk + 1}").set_value(at.radio(key=f"ocap_{wk + 1}").options[0]).run()
        if wk < weeks - 1:
            _click(at, "▶️ Next production week")
    at.sidebar.number_input[0].set_value(weeks).run()
    _click(at, "🏁 Finish")
    assert at.session_state.phase == 5
    at.text_input(key="lms_name").set_value("Test Student").run()
    code = at.code[0].value
    assert code == J.completion_code("Test Student", at.session_state.score, weeks)
    return at


def _new(query):
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_full_game_without_storage():
    at = play(_new({"seed": "42"}), 42)
    assert at.session_state.rounds_played == 5


def test_seeded_runs_are_reproducible():
    a = _new({"seed": "7"}); b = _new({"seed": "7"}); c = _new({"seed": "8"})
    for at in (a, b, c):
        at.sidebar.select_slider[0].set_value("⚡ Instant").run()
        _click(at, "🏭 Run")
    assert np.array_equal(a.session_state.baseline, b.session_state.baseline)
    assert not np.array_equal(a.session_state.baseline, c.session_state.baseline)


class FakeStore:
    def __init__(self):
        self.data, self.uploads = {}, 0

    def save(self, game, sid, state, **kw):
        self.uploads += 1
        self.data[(game, sid)] = dict(state)
        return True

    def load(self, game, sid):
        return dict(self.data.get((game, sid), {}))


@pytest.fixture
def fake_store(monkeypatch):
    fs = FakeStore()
    monkeypatch.setattr(student_store, "ENABLED", True)
    monkeypatch.setattr(student_store, "save", fs.save)
    monkeypatch.setattr(student_store, "load", fs.load)
    monkeypatch.setattr(student_store, "record_completion", lambda *a, **k: True)
    return fs


def _flush():
    J._autosaver().flush(timeout=10)


def test_progress_saved_and_resumed(fake_store):
    q = {"sid": "alice", "game": "T1"}
    at = _new(q)
    at.sidebar.select_slider[0].set_value("⚡ Instant").run()
    _click(at, "🏭 Run")
    _click(at, "➡️ Next")
    _flush()
    saved = fake_store.data[("T1", "alice")]
    assert saved["phase"] == 2 and len(saved["baseline"]) == 24
    # A brand-new browser session for the same student resumes exactly there.
    at2 = _new(q)
    assert at2.session_state.phase == 2
    assert np.allclose(at2.session_state.baseline, at.session_state.baseline)


def test_unchanged_state_is_not_reuploaded(fake_store):
    at = _new({"sid": "bob", "game": "T1"})
    at.sidebar.select_slider[0].set_value("⚡ Instant").run()
    _click(at, "🏭 Run"); _click(at, "➡️ Next")
    _by_label(at.radio, "**Predict:**").set_value("Less consistent").run()
    _click(at, "⏩ Auto-run 10 (adjust each)"); _click(at, "➡️ Proceed")
    _by_label(at.radio, "Fill volume").set_value("X-bar & R chart").run()
    _by_label(at.radio, "Defective bottles").set_value("p-chart").run()   # → Step 2 checkpoint
    _flush()
    before = fake_store.uploads
    assert fake_store.data[("T1", "bob")]["sel_att"] == "p-chart"
    for _ in range(5):                       # Act 2 reruns with nothing new to save
        at.run()
    _flush()
    assert fake_store.uploads == before      # the original uploaded 5 more times here
    _by_label(at.radio, "**Sample size (n)**").set_value(at.session_state.q_n or
                                                         f"{at.session_state.sub_n} bottles in each sample").run()
    _flush()
    assert fake_store.uploads == before + 1  # a real change is still saved
    assert fake_store.data[("T1", "bob")]["q_n"] is not None


def test_restart_resets_stored_progress(fake_store):
    at = _new({"sid": "carol", "game": "T1"})
    at.sidebar.select_slider[0].set_value("⚡ Instant").run()
    _click(at, "🏭 Run"); _click(at, "➡️ Next")
    _click(at, "↺ Restart")
    _flush()
    assert fake_store.data[("T1", "carol")] == {}
    assert at.session_state.phase == 1 and at.session_state.baseline is None


def test_students_are_isolated(fake_store):
    a = _new({"sid": "dana", "game": "T1"}); b = _new({"sid": "eli", "game": "T1"})
    for at in (a, b):
        at.sidebar.select_slider[0].set_value("⚡ Instant").run()
        _click(at, "🏭 Run")
    assert not np.array_equal(a.session_state.baseline, b.session_state.baseline)
    _flush()
    assert np.allclose(fake_store.data[("T1", "dana")]["baseline"], a.session_state.baseline)
    assert np.allclose(fake_store.data[("T1", "eli")]["baseline"], b.session_state.baseline)
