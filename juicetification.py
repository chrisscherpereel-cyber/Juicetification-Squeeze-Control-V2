"""
================================================================================
 JUICETIFICATION: SQUEEZE CONTROL  —  An SPC Learning Game  (v1.0)
================================================================================
Teaches Statistical Process Control with a juice-bottling story.

    Act 1  "Rotterdam"   Collect baseline data (variables + attributes) from an
                         in-control Dutch plant.
    Interlude "Funnel"   Deming's funnel: feel why adjusting for common-cause noise
                         makes variation worse (tampering).
    Act 2  "Blueprints"  Pick the right chart per data type, separate sample size n
                         from number of samples k, then calculate the limits yourself.
    Act 3  "Route 66"    Run a US franchise. Any of the THREE charts may go out of
                         control; diagnose each, then choose an action plan (OCAP).

    OUT-OF-CONTROL RULES (this build)
      * Point beyond the control limits.
      * Run   — 5 or more points in a row on one side of the centerline.
      * Trend — 5 or more points in a row steadily rising or falling.
      * Two-near-a-limit — 2 points in a row out past the 2-sigma warning zone.

    RUN IT
        pip install -r requirements.txt
        streamlit run juicetification.py
================================================================================
"""

import time
import hashlib
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from juice_director import resolve_config, serve_manifest_if_requested
from manifest import MANIFEST
import student_store as store

serve_manifest_if_requested(MANIFEST)          # (A) ?manifest=1 → emit schema & stop
CFG, CTX = resolve_config(MANIFEST)            # (B) instructor config → params, context

# -----------------------------------------------------------------------------
# 1. CONSTANTS
# -----------------------------------------------------------------------------
SPC_CONSTANTS = {
    2: dict(A2=1.880, D3=0.000, D4=3.267, d2=1.128),
    3: dict(A2=1.023, D3=0.000, D4=2.574, d2=1.693),
    4: dict(A2=0.729, D3=0.000, D4=2.282, d2=2.059),
    5: dict(A2=0.577, D3=0.000, D4=2.114, d2=2.326),
    6: dict(A2=0.483, D3=0.000, D4=2.004, d2=2.534),
    7: dict(A2=0.419, D3=0.076, D4=1.924, d2=2.704),
}

# --- Instructor-configurable values (Director; defaults if no config) --------
TARGET_FILL     = CFG["target_fill_ml"]   # 300 mL default
WITHIN_SIGMA    = CFG["within_sigma"]      # filler standard deviation (mL)
SPEC_LOW, SPEC_HIGH = CFG["spec_low"], CFG["spec_high"]   # engineering spec
SUBGROUP_N      = CFG["subgroup_n"]        # fill subgroup size n
N_BASELINE      = CFG["n_baseline"]        # baseline subgroups collected
P_INSPECT       = CFG["p_inspect"]         # bottles inspected per shift (attributes)
P_BASELINE_RATE = CFG["p_baseline_rate"]   # in-control fraction defective
RANDOMIZE_SAMPLING = CFG["randomize_sampling"]   # if True, draw n & n_p per student

COMPLETION_SALT = CFG["completion_salt"]   # instructors: set your own secret

# --- Plant economics: what each kind of error costs the business -------------
COST_RECALL   = CFG["cost_recall"]     # $ per missed signal (Type II)
COST_LINESTOP = CFG["cost_linestop"]   # $ per false alarm (Type I)

RUN_LEN   = 5                 # run   = this many in a row on one side of centerline
TREND_LEN = CFG["trend_len"]  # trend = this many in a row steadily rising/falling

# Director seed: when provided, the whole session is reproducible; else random.
SEED = CTX["seed"]

# --- Per-student identity: a stable, unique scenario seeded from the student id.
#     (No-op when student_store is unconfigured — SID stays None, SEED unchanged.)
GAME = store.game_code()
SID = store.get_student_id()
if SID is not None:
    SEED = store.derive_seed(GAME, SID, lo=1, hi=10 ** 6)

GOOD_COLOR = "#ff7a00"    # good juice = orange
BAD_COLOR  = "#2ecc71"    # defective  = green
FLAG_COLOR = "#c0392b"    # highlighted out-of-control point (X-bar / R)
NAVY       = "#2c3e50"

RULE_LABELS = {
    "beyond_limits": f"Point beyond the limits",
    "run":           f"Run ({RUN_LEN}+ on one side)",
    "trend":         f"Trend ({TREND_LEN}+ rising/falling)",
    "near_limit":    "Two points near a limit",
}

SPEEDS = {"🐢 Slow": 0.24, "Normal": 0.11, "🐇 Fast": 0.045, "⚡ Instant": 0.0}

PHASE_LABELS = {1: "Act 1 · Rotterdam", 2: "Interlude · The Funnel",
                3: "Act 2 · Blueprints", 4: "Act 3 · Route 66", 5: "Results"}
N_PHASES = 5

# --- Theming: the juice company and its product line (SKUs) ------------------
BRAND = "Juicetification Inc."
BRAND_TAG = "Fresh-Pressed Bottling"
PRODUCTS = {
    "NL": dict(name="Valencia Orange", color="#ff7a00", lot="RT"),
    "US": dict(name="Route 66 Mango", color="#f6a01a", lot="R66"),
}

# --- Story cast -------------------------------------------------------------
MARGIT = dict(name="Margit · Rotterdam Plant Manager", emoji="👩‍🏭", accent="#21468B")
HQ = dict(name="Owen · Juicetification HQ", emoji="🧑‍💼", accent="#B22234")

# Root-cause flavor text, per chart and signal.
CAUSES = {
    "x": {
        "beyond_limits": "A filler jam over-filled one shift — a single X-bar point punches past a limit.",
        "run":  "A new, sweeter concentrate lot shifted the mean and held it there — a run to one side.",
        "trend":"A worn pump seal is drifting out of calibration — fill volume creeps steadily.",
        "near_limit":"A sticking valve shoved two shifts hard toward a limit.",
        "combo":"A clogging filter drove a rising trend that finally burst past the limit.",
    },
    "r": {
        "beyond_limits": "A loose fitting made one shift's fills wildly inconsistent — the range leaps past its limit.",
        "run":  "A vibrating conveyor raised bottle-to-bottle variation for several shifts — a range run.",
        "trend":"A wearing nozzle makes fills progressively more erratic — a rising range trend.",
        "near_limit":"Intermittent air in the line pushed the spread near the range limit twice.",
        "combo":"Growing mechanical play widened the spread until the range broke its limit.",
    },
    "p": {
        "beyond_limits": "A contaminated batch spiked defective bottles past the p-chart limit.",
        "run":  "A mislabeled roll raised the defect rate modestly for several shifts — a run above p-bar.",
        "trend":"A drying capper seal makes more bottles leak each shift — a rising defect trend.",
        "near_limit":"A flaky vision sensor let the defect rate ride near its limit twice.",
        "combo":"A failing capper drove a rising defect trend that finally broke the limit.",
    },
}
SIGNAL_POOL = ["beyond_limits", "run", "trend", "near_limit", "combo"]


# -----------------------------------------------------------------------------
# 2. DATA GENERATION
# -----------------------------------------------------------------------------
def make_subgroups(n_groups, n=SUBGROUP_N, mean=TARGET_FILL, sigma=WITHIN_SIGMA, rng=None):
    rng = rng or np.random.default_rng()
    return rng.normal(mean, sigma, size=(n_groups, n))


def subgroup_with_mean(target_mean, rng, n=SUBGROUP_N, sigma=WITHIN_SIGMA):
    """A subgroup whose sample mean is exactly target_mean, normal spread."""
    v = rng.normal(0, sigma, n)
    return (v - v.mean()) + target_mean


def subgroup_with_range(target_mean, target_range, rng, n=SUBGROUP_N):
    """A subgroup with a controlled sample range (drives the R chart) and mean."""
    v = rng.normal(0, 1, n)
    v = v - v.mean()
    span = v.max() - v.min()
    if span < 1e-9:
        v = np.linspace(-1, 1, n)
        span = v.max() - v.min()
    return v * (target_range / span) + target_mean


def make_defects(n_groups, rate, rng, n_inspect=P_INSPECT):
    return rng.binomial(n_inspect, rate, size=n_groups)


# -----------------------------------------------------------------------------
# 3. LIMITS
# -----------------------------------------------------------------------------
def xbar_r_limits(data, n=None):
    n = data.shape[1] if n is None else n
    k = SPC_CONSTANTS[n]
    means = data.mean(axis=1)
    ranges = data.max(axis=1) - data.min(axis=1)
    xbarbar, rbar = means.mean(), ranges.mean()
    return dict(means=means, ranges=ranges, xbarbar=xbarbar, rbar=rbar,
                sigma_xbar=k["A2"] * rbar / 3.0,
                ucl_x=xbarbar + k["A2"] * rbar, lcl_x=xbarbar - k["A2"] * rbar,
                ucl_r=k["D4"] * rbar, lcl_r=k["D3"] * rbar)


def p_chart_limits(defect_counts, n_inspect=P_INSPECT):
    # p-bar = pooled average proportion = total defects / total bottles inspected.
    # (With a constant subgroup size this equals the mean of the per-subgroup
    #  proportions; the pooled form is the standard, correct definition.)
    pbar = np.sum(defect_counts) / (n_inspect * len(defect_counts))
    spread = 3.0 * np.sqrt(pbar * (1 - pbar) / n_inspect)
    return dict(pbar=pbar, ucl=pbar + spread, lcl=max(0.0, pbar - spread))


def sigma_updn(center, ucl, lcl):
    """Per-side 1-sigma estimates (limits are 3-sigma from the center)."""
    su = (ucl - center) / 3.0
    sd = (center - lcl) / 3.0 if lcl < center else su
    return su, sd


def centerline_hint(name, v, xbb, rbar, pbar, p_inspect=P_INSPECT):
    """Diagnose a wrong centerline entry and point at the likely reason."""
    tot = N_BASELINE * p_inspect
    if name == "X̄̄":
        if v > 305 or v < 295:
            return "X̄̄ should land near the 300 mL target — average the **Mean X̄** column (sum of the means ÷ number of shifts)."
        return "Almost — make sure you divided the sum of all the **Mean X̄** values by the number of shifts."
    if name == "R̄":
        if v <= 0:
            return "R̄ is the average of the **Range R** column — a small positive number, not zero."
        if v > 15:
            return "That's too large — you may have summed the ranges. Divide the **Range R** total by the number of shifts."
        return "Almost — average all the **Range R** values (sum ÷ number of shifts)."
    # p̄
    if v > 1:
        return f"That looks like a **count**, not a proportion. Divide total defects by total bottles inspected ({N_BASELINE} × {p_inspect} = {tot:,})."
    if v > 0.15:
        return f"Too high for this defect rate — did you divide by the {N_BASELINE} shifts? Use total bottles inspected = {tot:,}."
    return f"Almost — p̄ = total **Defects** ÷ {tot:,} (that's {N_BASELINE} shifts × {p_inspect} bottles)."


def limit_hint(name, v, c):
    """Diagnose a wrong limit entry. c holds xbb, rbar, pbar, a2, d3, d4, ucl/lcl, np."""
    near = lambda a, b: abs(a - b) <= max(0.3, abs(b) * 0.02)
    nearp = lambda a, b: abs(a - b) <= 0.004
    if name == "UCL X̄":
        if near(v, c["lcl_x"]):
            return "That's the **lower** limit — the UCL **adds** A₂·R̄ to X̄̄."
        if near(v, c["xbb"]):
            return "You left off the term — UCL_X̄ = X̄̄ **+ A₂·R̄**."
        return "UCL_X̄ = X̄̄ + A₂·R̄. Recheck the product A₂ × R̄."
    if name == "LCL X̄":
        if near(v, c["ucl_x"]):
            return "Check the sign — the LCL **subtracts** A₂·R̄ (looks like you added)."
        if near(v, c["xbb"]):
            return "You left off the term — LCL_X̄ = X̄̄ **− A₂·R̄**."
        return "LCL_X̄ = X̄̄ − A₂·R̄."
    if name == "UCL R":
        if near(v, c["rbar"]):
            return "You left it as R̄ — multiply R̄ by **D₄**."
        if abs(v) < 0.05:
            return "That's D₃·R̄ (= 0). The **upper** R limit uses **D₄**, not D₃."
        return "UCL_R = D₄ × R̄."
    if name == "LCL R":
        if c["d3"] == 0:
            return "The table gives **D₃ = 0** for this n, so LCL_R = D₃ × R̄ = **0**."
        return f"LCL_R = D₃ × R̄ — for this n, D₃ = {c['d3']} (nonzero), so it isn't 0."
    if name == "UCL p":
        se = 3 * np.sqrt(c["pbar"] * (1 - c["pbar"]) / c["np"])
        fill_n = c.get("fill_n", SUBGROUP_N)
        se5 = 3 * np.sqrt(c["pbar"] * (1 - c["pbar"]) / fill_n)
        if nearp(v, c["pbar"]):
            return "Add the spread — UCL_p = p̄ **+ 3√(p̄(1−p̄)/n_p)**."
        if nearp(v, c["pbar"] - se):
            return "That's the **lower** limit — the UCL **adds** the 3-sigma term."
        if nearp(v, c["pbar"] + se5):
            return f"Use the **p-chart** sample size n_p = {c['np']} inside the root, not the fill n = {fill_n}."
        return f"UCL_p = p̄ + 3√(p̄(1−p̄)/n_p), with n_p = {c['np']}."
    # LCL p
    if v > 0.02:
        return "LCL_p = p̄ − 3√(p̄(1−p̄)/n_p). If that comes out below 0, floor it to **0**."
    return "LCL_p = max(0, p̄ − 3√(p̄(1−p̄)/n_p))."


# -----------------------------------------------------------------------------
# 4. GENERAL VIOLATION DETECTION  (works for X-bar, R, or p)
# -----------------------------------------------------------------------------
def detect_violations(values, center, ucl, lcl, sigma_up, sigma_dn,
                      check_lower_near=True):
    """Return {rule: [indices]} using this build's run/trend definitions."""
    v = np.asarray(values, float)
    n = len(v)
    hits = {"beyond_limits": [], "run": [], "trend": [], "near_limit": []}

    for i, val in enumerate(v):                       # beyond the limits
        if val > ucl or val < lcl:
            hits["beyond_limits"].append(i)

    side = np.sign(v - center)                        # run: RUN_LEN on one side
    i = 0
    while i < n:
        j = i
        while j + 1 < n and side[j + 1] == side[i] and side[i] != 0:
            j += 1
        if side[i] != 0 and (j - i + 1) >= RUN_LEN:
            hits["run"].extend(range(i, j + 1))
        i = j + 1

    for i in range(n - TREND_LEN + 1):                # trend: TREND_LEN monotone
        w = v[i:i + TREND_LEN]
        d = np.diff(w)
        if np.all(d > 0) or np.all(d < 0):
            hits["trend"].extend(range(i, i + TREND_LEN))

    for i in range(n - 1):                             # two near a limit (Zone A)
        a, b = v[i], v[i + 1]
        if a > center + 2 * sigma_up and b > center + 2 * sigma_up:
            hits["near_limit"].extend([i, i + 1])
        if check_lower_near and a < center - 2 * sigma_dn and b < center - 2 * sigma_dn:
            hits["near_limit"].extend([i, i + 1])

    return {k: sorted(set(val)) for k, val in hits.items() if val}


# -----------------------------------------------------------------------------
# 5. PER-CHART SIGNAL INJECTION
# -----------------------------------------------------------------------------
def inject_xbar(sub, signal, xbb, sx, rng, n=SUBGROUP_N):
    sub = sub.copy(); g = len(sub)
    def place(idx, off): sub[idx] = subgroup_with_mean(xbb + off * sx, rng, n=n)
    if signal == "beyond_limits":
        place(rng.integers(4, g - 2), 4.6)
    elif signal == "run":
        s = int(rng.integers(3, g - RUN_LEN - 2))
        for k in range(RUN_LEN + 1):
            place(s + k, 1.5 + rng.normal(0, 0.15))
    elif signal == "trend":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        for k, off in enumerate(np.linspace(-1.3, 1.9, TREND_LEN + 1)):
            place(s + k, off)
    elif signal == "near_limit":
        i = int(rng.integers(3, g - 3)); place(i, 2.3); place(i + 1, 2.45)
    elif signal == "combo":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        offs = list(np.linspace(-1.0, 1.9, TREND_LEN)) + [3.8]
        for k, off in enumerate(offs):
            place(s + k, off)
    return sub


def inject_range(sub, signal, xbb, sx, rbar, ucl_r, rng, n=SUBGROUP_N):
    sub = sub.copy(); g = len(sub)
    sR = (ucl_r - rbar) / 3.0
    def place(idx, tr):
        m = xbb + rng.normal(0, sx * 0.25)            # keep X-bar near center
        sub[idx] = subgroup_with_range(m, max(1.0, tr), rng, n=n)
    if signal == "beyond_limits":
        place(rng.integers(4, g - 2), ucl_r * 1.25)
    elif signal == "run":
        s = int(rng.integers(3, g - RUN_LEN - 2))
        for k in range(RUN_LEN + 1):
            place(s + k, rbar + (1.3 + rng.normal(0, 0.1)) * sR)
    elif signal == "trend":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        for k, f in enumerate(np.linspace(rbar - 1.4 * sR, rbar + 1.6 * sR, TREND_LEN + 1)):
            place(s + k, f)
    elif signal == "near_limit":
        i = int(rng.integers(3, g - 3))
        place(i, rbar + 2.3 * sR); place(i + 1, rbar + 2.45 * sR)
    elif signal == "combo":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        vals = list(np.linspace(rbar - 1.0 * sR, rbar + 1.5 * sR, TREND_LEN)) + [ucl_r * 1.25]
        for k, f in enumerate(vals):
            place(s + k, f)
    return sub


def inject_pcounts(counts, signal, pbar, ucl_p, n, rng):
    c = counts.copy(); g = len(c)
    sp = (ucl_p - pbar) / 3.0
    def cnt(fr): return int(np.clip(round(fr * n), 0, n))
    if signal == "beyond_limits":
        c[int(rng.integers(4, g - 2))] = cnt(ucl_p * 1.5)
    elif signal == "run":
        s = int(rng.integers(3, g - RUN_LEN - 2))
        val = cnt(pbar + 1.4 * sp)
        for k in range(RUN_LEN + 1):
            c[s + k] = val
    elif signal == "trend":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        base = max(0, cnt(pbar) - 2)
        for k in range(TREND_LEN + 1):
            c[s + k] = base + k                        # strictly increasing ints
    elif signal == "near_limit":
        s = int(rng.integers(3, g - 3))
        nl = cnt(pbar + 2.35 * sp)
        c[s] = nl; c[s + 1] = nl
    elif signal == "combo":
        s = int(rng.integers(3, g - TREND_LEN - 2))
        base = max(0, cnt(pbar) - 2)
        for k in range(TREND_LEN):
            c[s + k] = base + k
        c[s + TREND_LEN] = cnt(ucl_p * 1.5)            # final point beyond limit
    return c


def expected_ok(signal, detected_keys):
    """Acceptance test so each chart shows a crisp, intended signal."""
    d = set(detected_keys)
    if signal == "none":
        return len(d) == 0
    if signal == "combo":
        return {"trend", "beyond_limits"} <= d
    return d == {signal}


# -----------------------------------------------------------------------------
# 6. THEME, CARDS, BOTTLE, GRID
# -----------------------------------------------------------------------------
def inject_theme():
    st.markdown("""
    <style>
      @keyframes shimmer {0%{background-position:-200% center}100%{background-position:200% center}}
      @keyframes pulse   {0%,100%{box-shadow:0 0 0 0 rgba(192,57,43,.55)}50%{box-shadow:0 0 0 14px rgba(192,57,43,0)}}
      @keyframes rise    {from{transform:translateY(8px);opacity:0}to{transform:translateY(0);opacity:1}}
      .jt{font-size:2.3rem;font-weight:800;letter-spacing:-.5px;
          background:linear-gradient(90deg,#ff7a00,#ffcf4d,#ff7a00);background-size:200% auto;
          -webkit-background-clip:text;background-clip:text;color:transparent;
          animation:shimmer 4s linear infinite;margin-bottom:0}
      .sub{color:#8a8f98;margin-top:-4px}
      .alertbox{background:#fdecea;border-left:6px solid #c0392b;padding:12px 16px;border-radius:10px;
                color:#922b21;font-weight:700;animation:pulse 1.4s infinite,rise .4s ease}
      .okbox{background:#eafaf1;border-left:6px solid #27ae60;padding:12px 16px;border-radius:10px;
             color:#1e8449;font-weight:700;animation:rise .4s ease}
      @keyframes belt {from{transform:translateX(0)} to{transform:translateX(-50%)}}
      .hud{display:flex;align-items:center;gap:10px;background:linear-gradient(180deg,#ffffff,#f4f7fb);
           border:1px solid #e5e9f0;border-radius:14px;padding:8px 14px;margin-bottom:10px;
           box-shadow:0 1px 3px rgba(20,30,50,.05)}
      .hud-brand{display:flex;align-items:baseline;gap:6px;font-size:1.15rem;flex:none}
      .hud-name{font-weight:800;background:linear-gradient(90deg,#ff7a00,#ffcf4d,#ff7a00);
                background-size:200% auto;-webkit-background-clip:text;background-clip:text;
                color:transparent;animation:shimmer 4s linear infinite}
      .hud-tag{font-size:.72rem;color:#8a8f98;font-weight:600}
      .hud-belt{flex:1;min-width:60px;overflow:hidden;height:30px;position:relative;
                border-top:2px solid #dbe2ea;border-bottom:2px solid #dbe2ea;background:#f7f9fc}
      .hud-row{position:absolute;top:1px;left:0;display:flex;gap:20px;padding-left:20px;
               animation:belt 7s linear infinite;will-change:transform}
      .hud-meta{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;flex:none}
      .chip{display:inline-flex;align-items:center;gap:5px;background:#eef2f7;border:1px solid #e0e6ee;
            border-radius:20px;padding:3px 10px;font-size:.76rem;color:#3a424e;white-space:nowrap}
      .chip i{width:9px;height:9px;border-radius:50%;display:inline-block}
    </style>""", unsafe_allow_html=True)


def _flag_svg(country, w=34, h=23):
    """Simple inline national-flag SVG (no external images)."""
    if country == "NL":       # Netherlands: red / white / blue horizontal bands
        return (f'<svg width="{w}" height="{h}" viewBox="0 0 3 2" '
                f'style="border:1px solid #d0d5dd;border-radius:3px;vertical-align:middle">'
                f'<rect width="3" height="2" fill="#fff"/>'
                f'<rect width="3" height="0.667" y="0" fill="#AE1C28"/>'
                f'<rect width="3" height="0.667" y="1.333" fill="#21468B"/></svg>')
    # United States: 13 stripes + blue canton with a star field (stylized)
    stripes = "".join(
        f'<rect y="{i*(h/13):.2f}" width="{w}" height="{h/13:.2f}" '
        f'fill="{"#B22234" if i%2==0 else "#fff"}"/>' for i in range(13))
    canton_w, canton_h = w * 0.42, h * 7 / 13
    stars = ""
    for r in range(3):
        for c in range(4):
            cx = canton_w * (c + 1) / 5
            cy = canton_h * (r + 1) / 4
            stars += f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="0.9" fill="#fff"/>'
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'style="border:1px solid #d0d5dd;border-radius:3px;vertical-align:middle">'
            f'{stripes}<rect width="{canton_w:.2f}" height="{canton_h:.2f}" fill="#3C3B6E"/>'
            f'{stars}</svg>')


def plant_banner(country, title, subtitle):
    """A colored header bar identifying which plant the student is working in."""
    accent = "#21468B" if country == "NL" else "#B22234"
    tint = "rgba(33,70,139,.08)" if country == "NL" else "rgba(178,34,52,.08)"
    tag = "🇳🇱 Netherlands" if country == "NL" else "🇺🇸 United States"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;background:{tint};'
        f'border-left:6px solid {accent};border-radius:10px;padding:10px 14px;margin:2px 0 10px">'
        f'{_flag_svg(country)}'
        f'<div><div style="font-weight:800;font-size:1.05rem;color:#1f2733">{title}</div>'
        f'<div style="font-size:.82rem;color:#5b6472">{tag} · {subtitle}</div></div></div>',
        unsafe_allow_html=True)


def _mini_bottle(color):
    """A tiny bottle for the conveyor belt in the HUD."""
    return ('<svg width="13" height="26" viewBox="0 0 13 26">'
            '<rect x="4.5" y="1" width="4" height="3" rx="1" fill="#cbd5e1"/>'
            '<rect x="2.5" y="4" width="8" height="20" rx="3" fill="#eef2f7" stroke="#cbd5e1"/>'
            f'<rect x="2.5" y="11" width="8" height="13" rx="3" fill="{color}"/></svg>')


def factory_hud(plant, lot, shift_label):
    """Persistent status bar: brand, a running conveyor, product SKU, lot, shift."""
    p = PRODUCTS[plant]
    belt = "".join(_mini_bottle(p["color"]) for _ in range(16))
    st.markdown(
        '<div class="hud">'
        f'<div class="hud-brand">🧃<span class="hud-name">{BRAND}</span>'
        f'<span class="hud-tag">{BRAND_TAG}</span></div>'
        f'<div class="hud-belt"><div class="hud-row">{belt}{belt}</div></div>'
        '<div class="hud-meta">'
        f'<span class="chip"><i style="background:{p["color"]}"></i>{p["name"]} · '
        f'{int(TARGET_FILL)} mL</span>'
        f'<span class="chip">Lot #{lot}</span>'
        f'<span class="chip">🕐 {shift_label}</span></div></div>',
        unsafe_allow_html=True)


def mentor_note(text, name, emoji, accent="#21468B"):
    """An in-character line from a mentor/boss to wrap the pedagogy in story."""
    st.markdown(
        f'<div style="display:flex;gap:12px;align-items:flex-start;background:#fbfcfe;'
        f'border:1px solid #e5e9f0;border-left:5px solid {accent};border-radius:12px;'
        f'padding:11px 14px;margin:6px 0 12px">'
        f'<div style="font-size:1.9rem;line-height:1;flex:none">{emoji}</div>'
        f'<div><div style="font-weight:800;color:{accent};font-size:.9rem">{name}</div>'
        f'<div style="color:#2f3742;font-style:italic;margin-top:2px">\u201c{text}\u201d</div>'
        f'</div></div>', unsafe_allow_html=True)


def _line_bottle(defect):
    """A small bottle for the inspection scene; defect draws a visible fault."""
    cap = '<rect x="6" y="0" width="4" height="3" rx="1" fill="#c7ced8"/>'
    body = '<rect x="3" y="3" width="10" height="33" rx="3" fill="#f2f5f9" stroke="#c7ced8"/>'
    if defect == "underfill":
        juice = '<rect x="3" y="29" width="10" height="7" rx="3" fill="#ff7a00"/>'
        extra = ''
    elif defect == "crooked":
        juice = '<rect x="3" y="13" width="10" height="23" rx="3" fill="#ff7a00"/>'
        extra = ('<rect x="1" y="17" width="14" height="7" rx="1" fill="#fff" '
                 'stroke="#c0392b" transform="rotate(14 8 20)"/>')
    elif defect == "leaky":
        juice = '<rect x="3" y="13" width="10" height="23" rx="3" fill="#ff7a00"/>'
        extra = '<circle cx="8" cy="6" r="1.6" fill="#ff7a00"/><circle cx="8" cy="10" r="1.1" fill="#ff7a00"/>'
    else:
        juice = '<rect x="3" y="13" width="10" height="23" rx="3" fill="#ff7a00"/>'
        extra = ''
    ring = ('' if defect is None else
            '<rect x="0.5" y="0.5" width="15" height="37" rx="4" fill="none" '
            'stroke="#2ecc71" stroke-width="1.5" stroke-dasharray="3 2"/>')
    return cap + body + juice + extra + ring


def inspection_scene_svg(n_inspected, n_defective):
    """A conveyor of bottles passing an inspector; defective ones pulled to a reject bin."""
    n_def = int(n_defective)
    rej_n = min(n_def, 5)
    belt = '<rect x="8" y="42" width="404" height="24" rx="4" fill="#e9edf3" stroke="#cbd5e1"/>'
    rollers = ''.join(f'<circle cx="{cx}" cy="54" r="7" fill="#cbd5e1"/>'
                      for cx in (16, 116, 216, 316, 404))
    goods = ''.join(f'<g transform="translate({22 + i*46},8)">{_line_bottle(None)}</g>'
                    for i in range(8))
    inspector = ('<g transform="translate(378,2)">'
                 '<circle cx="16" cy="16" r="10" fill="none" stroke="#2c3e50" stroke-width="3"/>'
                 '<line x1="23" y1="23" x2="33" y2="33" stroke="#2c3e50" stroke-width="3"/>'
                 '<text x="17" y="-1" font-size="9" text-anchor="middle" fill="#2c3e50">Inspector</text></g>')
    chute = ('<path d="M300 66 L300 92 L120 92 L120 116" fill="none" stroke="#c0392b" '
             'stroke-dasharray="4 3" stroke-width="1.5"/>')
    binbox = '<rect x="8" y="114" width="240" height="46" rx="6" fill="#fdecea" stroke="#e6b0aa"/>'
    binlabel = '<text x="14" y="110" font-size="9" fill="#c0392b" font-weight="700">REJECTED</text>'
    defects = ["underfill", "crooked", "leaky"]
    rejects = ''.join(f'<g transform="translate({22 + i*44},120)">{_line_bottle(defects[i % 3])}</g>'
                      for i in range(rej_n))
    more = (f'<text x="{26 + rej_n*44}" y="142" font-size="10" fill="#c0392b">+{n_def - rej_n} more</text>'
            if n_def > rej_n else '')
    svg = (f'<svg width="100%" viewBox="0 0 420 164">{belt}{rollers}{goods}{inspector}'
           f'{chute}{binbox}{binlabel}{rejects}{more}</svg>')
    cap = (f'<div style="color:#8a8f98;font-size:.78rem;text-align:center">Inspecting '
           f'{n_inspected} bottles/shift · {n_def} pulled off the line '
           f'(🟢 defective: underfill, crooked label, leaky cap)</div>')
    return svg + cap


# --- Root-cause diagrams: which machine part caused each signal --------------
_PART_ART = {
    "nozzle": ('<rect x="78" y="8" width="44" height="26" rx="3" fill="#cbd5e1"/>'
               '<path d="M84 34 L116 34 L106 66 L94 66 Z" fill="#aeb8c4"/>'
               '<rect x="94" y="66" width="12" height="10" fill="#c0392b"/>'
               '<circle cx="100" cy="88" r="5" fill="#ff7a00"/>'
               '<text x="128" y="72" font-size="10" fill="#c0392b">worn tip</text>', "Fill nozzle"),
    "pump": ('<circle cx="86" cy="55" r="30" fill="#e9edf3" stroke="#9aa6b2" stroke-width="3"/>'
             '<circle cx="86" cy="55" r="10" fill="#aeb8c4"/>'
             '<circle cx="86" cy="55" r="30" fill="none" stroke="#c0392b" stroke-width="3" stroke-dasharray="5 4"/>'
             '<rect x="116" y="50" width="42" height="10" fill="#aeb8c4"/>'
             '<text x="56" y="98" font-size="10" fill="#c0392b">worn seal</text>', "Filler pump &amp; seal"),
    "tank": ('<rect x="58" y="18" width="74" height="66" rx="8" fill="#eef2f7" stroke="#9aa6b2" stroke-width="2"/>'
             '<rect x="58" y="52" width="74" height="32" rx="6" fill="#ffb347"/>'
             '<rect x="88" y="6" width="14" height="14" fill="#cbd5e1"/>'
             '<text x="66" y="44" font-size="9" fill="#c0392b">off-spec batch</text>', "Concentrate tank"),
    "conveyor": (''.join(f'<circle cx="{cx}" cy="58" r="12" fill="#cbd5e1" stroke="#9aa6b2"/>' for cx in (48, 100, 152))
                 + '<rect x="36" y="44" width="128" height="4" fill="#aeb8c4"/>'
                 + '<path d="M36 74 Q100 86 164 74" fill="none" stroke="#c0392b" stroke-width="2"/>'
                 + '<text x="70" y="100" font-size="10" fill="#c0392b">vibration</text>', "Conveyor line"),
    "capper": ('<rect x="78" y="8" width="44" height="18" fill="#aeb8c4"/>'
               '<rect x="92" y="26" width="16" height="8" fill="#c0392b"/>'
               '<rect x="86" y="34" width="28" height="54" rx="6" fill="#eef2f7" stroke="#9aa6b2"/>'
               '<rect x="86" y="56" width="28" height="32" rx="6" fill="#ff7a00"/>'
               '<text x="120" y="32" font-size="10" fill="#c0392b">dry seal</text>', "Bottle capper"),
    "labeler": ('<circle cx="52" cy="48" r="22" fill="#eef2f7" stroke="#9aa6b2"/>'
                '<circle cx="52" cy="48" r="6" fill="#aeb8c4"/>'
                '<rect x="98" y="26" width="30" height="60" rx="6" fill="#eef2f7" stroke="#9aa6b2"/>'
                '<rect x="98" y="52" width="30" height="34" rx="6" fill="#ff7a00"/>'
                '<rect x="95" y="50" width="26" height="12" fill="#fff" stroke="#c0392b" transform="rotate(12 108 56)"/>'
                '<text x="60" y="100" font-size="10" fill="#c0392b">misfeed</text>', "Label applicator"),
    "sensor": ('<rect x="26" y="36" width="40" height="30" rx="4" fill="#2c3e50"/>'
               '<circle cx="66" cy="51" r="8" fill="#5b6472"/>'
               '<path d="M74 51 L118 43 M74 51 L118 59" stroke="#c0392b" stroke-dasharray="3 3"/>'
               '<rect x="118" y="30" width="26" height="52" rx="6" fill="#eef2f7" stroke="#9aa6b2"/>'
               '<rect x="118" y="52" width="26" height="30" rx="6" fill="#ff7a00"/>'
               '<text x="30" y="94" font-size="10" fill="#c0392b">flaky sensor</text>', "Vision sensor"),
}
PART_FOR = {
    ("x", "beyond_limits"): "nozzle", ("x", "run"): "tank", ("x", "trend"): "pump",
    ("x", "near_limit"): "nozzle", ("x", "combo"): "pump",
    ("r", "beyond_limits"): "nozzle", ("r", "run"): "conveyor", ("r", "trend"): "nozzle",
    ("r", "near_limit"): "nozzle", ("r", "combo"): "nozzle",
    ("p", "beyond_limits"): "tank", ("p", "run"): "labeler", ("p", "trend"): "capper",
    ("p", "near_limit"): "sensor", ("p", "combo"): "capper",
}


def part_diagram_svg(part):
    art, label = _PART_ART[part]
    return ('<div style="text-align:center;background:#fbfcfe;border:1px solid #e5e9f0;'
            'border-radius:10px;padding:6px 4px">'
            f'<svg width="100%" viewBox="0 0 200 110" style="max-height:130px">{art}</svg>'
            f'<div style="font-size:.78rem;font-weight:700;color:#2c3e50">{label}</div></div>')


def completion_code(name, score, weeks):
    """Deterministic, checksummed code for LMS submission (verifiable with the salt)."""
    key = f"{name.strip().lower()}|{int(score)}|{int(weeks)}|{COMPLETION_SALT}"
    h = hashlib.sha256(key.encode()).hexdigest()[:6].upper()
    return f"SQZ-{int(weeks):02d}-{int(score):04d}-{h}"


def pnl_cards(shipped_bad, stopped_good):
    """Turn the two error tallies into dollars: recalls (Type II) & line stops (Type I)."""
    recall = shipped_bad * COST_RECALL
    stops = stopped_good * COST_LINESTOP
    total = recall + stops

    def card(emoji, label, amount, sub, color):
        return (f'<div style="background:#f8fafc;border:1px solid #e5e9f0;border-radius:12px;'
                f'padding:10px 12px;margin-bottom:8px">'
                f'<div style="font-size:.78rem;color:#5b6472">{emoji} {label}</div>'
                f'<div style="font-size:1.35rem;font-weight:800;color:{color}">${amount:,.0f}</div>'
                f'<div style="font-size:.72rem;color:#8a8f98">{sub}</div></div>')
    st.markdown(
        card("🚨", "Recalls · shipped bad juice", recall,
             f"{shipped_bad} missed × ${COST_RECALL:,} (Type II)", "#c0392b")
        + card("🛑", "Lost production · line stops", stops,
               f"{stopped_good} false alarms × ${COST_LINESTOP:,} (Type I)", "#e67e22")
        + f'<div style="text-align:center;font-weight:800;color:#2c3e50;margin-top:2px">'
          f'Quality cost to date: ${total:,.0f}</div>',
        unsafe_allow_html=True)


def consequence_cards(shipped_bad, stopped_good, cap=8):
    """Readable HTML stat-cards for the two error tallies."""
    def card(emoji, label, value, color):
        pct = min(value / cap, 1.0) * 100 if cap else 0
        return (
            f'<div style="background:#f8fafc;border:1px solid #e5e9f0;border-radius:12px;'
            f'padding:11px 13px;margin-bottom:9px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<span style="font-size:.8rem;color:#5b6472">{emoji} {label}</span>'
            f'<span style="font-size:1.5rem;font-weight:800;color:{color}">{value}</span></div>'
            f'<div style="height:9px;background:#e9edf3;border-radius:6px;margin-top:7px;overflow:hidden">'
            f'<div style="height:100%;width:{pct:.0f}%;background:{color};border-radius:6px"></div></div>'
            f'</div>')
    st.markdown(
        card("🧴", "Bad juice shipped", shipped_bad, "#c0392b") +
        card("🛑", "Needless line stops", stopped_good, "#e67e22"),
        unsafe_allow_html=True)


def bottle_svg(frac):
    frac = max(0.0, min(1.0, frac))
    bh, bt = 150, 45
    jh = bh * frac
    jy = bt + (bh - jh)
    return f"""<div style="text-align:center"><svg width="120" height="230" viewBox="0 0 120 230">
      <defs><linearGradient id="j" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffb347"/><stop offset="100%" stop-color="#ff7a00"/></linearGradient></defs>
      <rect x="50" y="12" width="20" height="20" rx="3" fill="#cbd5e1"/>
      <path d="M45 32 h30 v13 h-30 z" fill="#e2e8f0"/>
      <rect x="30" y="{bt}" width="60" height="{bh}" rx="16" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="2"/>
      <clipPath id="c"><rect x="30" y="{bt}" width="60" height="{bh}" rx="16"/></clipPath>
      <rect x="30" y="{jy:.1f}" width="60" height="{jh:.1f}" fill="url(#j)" clip-path="url(#c)"/>
      <rect x="38" y="{bt+12}" width="8" height="{bh-24}" rx="4" fill="rgba(255,255,255,.35)"/></svg>
      <div style="color:#8a8f98;font-size:.85rem">filling sample bottles…</div></div>"""


def inspection_grid_svg(n_show, n_bad, cols=15):
    n_bad = int(max(0, min(n_show, n_bad)))
    bad = set(int(v) for v in np.linspace(0, n_show - 1, n_bad)) if n_bad else set()
    r, gap = 5, 3
    step = 2 * r + gap
    rows = -(-n_show // cols)
    dots = []
    for idx in range(n_show):
        cx = (idx % cols) * step + r + 2
        cy = (idx // cols) * step + r + 2
        color = BAD_COLOR if idx in bad else GOOD_COLOR
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
    w, h = cols * step + 4, rows * step + 4
    return (f'<svg width="100%" viewBox="0 0 {w} {h}">{"".join(dots)}</svg>'
            f'<div style="color:#8a8f98;font-size:.78rem;text-align:center">'
            f'🟠 good · 🟢 defective (showing {n_show} of {P_INSPECT})</div>')


def nk_diagram_svg(n=SUBGROUP_N, k=N_BASELINE, show_rows=4):
    """Teaching graphic: separates sample size n (across) from #samples k (down)."""
    r, gap = 9, 8
    step = 2 * r + gap
    x0, y0 = 118, 34
    dots = []
    for row in range(show_rows):
        for col in range(n):
            cx = x0 + col * step + r
            cy = y0 + row * step + r
            dots.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffb347" '
                        f'stroke="#ff7a00" stroke-width="1.5"/>')
    grid_w = n * step
    grid_bottom = y0 + show_rows * step
    ell_y = grid_bottom + 6
    # vertical brace (k = number of samples)
    bx = x0 - 16
    kbrace = (f'<path d="M{bx} {y0} h-6 V{ell_y+18} h6" fill="none" '
              f'stroke="#2c3e50" stroke-width="2"/>')
    klabel = (f'<text x="14" y="{(y0+ell_y)/2-8}" font-size="15" font-weight="700" '
              f'fill="#2c3e50">k = {k}</text>'
              f'<text x="14" y="{(y0+ell_y)/2+10}" font-size="11" fill="#5b6472">number of</text>'
              f'<text x="14" y="{(y0+ell_y)/2+24}" font-size="11" fill="#5b6472">samples</text>'
              f'<text x="14" y="{(y0+ell_y)/2+38}" font-size="11" fill="#5b6472">(shifts)</text>')
    # horizontal brace (n = sample size)
    by = y0 - 12
    nbrace = (f'<path d="M{x0} {by} v-6 H{x0+grid_w} v6" fill="none" '
              f'stroke="#ff7a00" stroke-width="2"/>')
    nlabel = (f'<text x="{x0+grid_w/2}" y="{by-12}" font-size="15" font-weight="700" '
              f'fill="#ff7a00" text-anchor="middle">n = {n}  (sample size — bottles per shift)</text>')
    ellipsis = (f'<text x="{x0+grid_w/2}" y="{ell_y+14}" font-size="20" fill="#c9ced6" '
                f'text-anchor="middle">⋮  (rows 5 … {k})</text>')
    h = ell_y + 30
    return (f'<div style="text-align:center;margin:6px 0">'
            f'<svg width="100%" viewBox="0 0 {x0+grid_w+30} {h}" style="max-height:260px">'
            f'{kbrace}{klabel}{nbrace}{nlabel}{"".join(dots)}{ellipsis}</svg></div>')


# -----------------------------------------------------------------------------
# 7. CHART FIGURES
# -----------------------------------------------------------------------------
def single_chart(values, center, ucl, lcl, title, yaxis, sigma=None,
                 flagged=None, marker=NAVY):
    """A standalone control chart (used for the Act-2 baseline views)."""
    flagged = flagged or set()
    x = list(range(1, len(values) + 1))
    fig = go.Figure()
    if sigma:
        fig.add_hrect(y0=center + 2 * sigma, y1=ucl, line_width=0, fillcolor="rgba(255,170,0,.10)")
        fig.add_hrect(y0=center - 2 * sigma, y1=lcl, line_width=0, fillcolor="rgba(255,170,0,.10)")
    fig.add_hline(y=ucl, line=dict(color="#d33", dash="dash"), annotation_text="UCL")
    fig.add_hline(y=lcl, line=dict(color="#d33", dash="dash"), annotation_text="LCL")
    fig.add_hline(y=center, line=dict(color="#2a2", dash="dot"), annotation_text="CL")
    colors = [FLAG_COLOR if i in flagged else marker for i in range(len(values))]
    fig.add_trace(go.Scatter(x=x, y=values, mode="lines+markers", line=dict(color="#7f8c8d"),
                             marker=dict(size=10, color=colors, line=dict(width=1, color="white"))))
    fig.update_layout(title=title, xaxis_title="Subgroup", yaxis_title=yaxis, height=320,
                      margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


def p_chart_fig(counts, pbar, ucl, lcl, n_inspect=P_INSPECT, neutral=False,
                title="p-chart — fraction defective"):
    p = np.asarray(counts) / n_inspect
    x = list(range(1, len(p) + 1))
    colors = [GOOD_COLOR if neutral or not (v > ucl or v < lcl) else BAD_COLOR for v in p]
    fig = go.Figure()
    fig.add_hline(y=ucl, line=dict(color="#d33", dash="dash"), annotation_text="UCL")
    fig.add_hline(y=pbar, line=dict(color="#888", dash="dot"), annotation_text="p̄")
    if lcl > 0:
        fig.add_hline(y=lcl, line=dict(color="#d33", dash="dash"), annotation_text="LCL")
    fig.add_trace(go.Scatter(x=x, y=p, mode="lines+markers", line=dict(color="#c9ced6"),
                             marker=dict(size=10, color=colors, line=dict(width=1, color="white"))))
    fig.update_layout(title=title, height=300, showlegend=False, xaxis_title="Shift",
                      yaxis_title="Fraction defective", margin=dict(l=10, r=10, t=40, b=10))
    return fig


def week_figure(means, ranges, fracs, lim, plim, upto, flags=None, reveal=False):
    """One stacked figure with the three charts, drawn up to `upto` points."""
    flags = flags or {"x": set(), "r": set(), "p": set()}
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                        subplot_titles=("X-bar — mean fill (mL)", "R — range (mL)",
                                        "p — fraction defective"))
    x = list(range(1, upto + 1))

    N = len(means)

    def hline(row, y, color, dash):
        fig.add_trace(go.Scatter(x=[0, N + 1], y=[y, y], mode="lines",
                                 line=dict(color=color, dash=dash, width=1.6),
                                 hoverinfo="skip", showlegend=False), row=row, col=1)

    def hlabel(row, y, text, color):
        fig.add_annotation(x=N + 0.6, y=y, text=text, showarrow=False, xanchor="left",
                           font=dict(size=11, color=color),
                           bgcolor="rgba(255,255,255,.8)", row=row, col=1)

    # X-bar (row 1) — control limits + centerline as line traces (always render)
    for y, c, d, lbl in [(lim["ucl_x"], "#d33", "dash", f"UCL {lim['ucl_x']:.2f}"),
                         (lim["xbarbar"], "#2a2", "dot", f"CL {lim['xbarbar']:.2f}"),
                         (lim["lcl_x"], "#d33", "dash", f"LCL {lim['lcl_x']:.2f}")]:
        hline(1, y, c, d); hlabel(1, y, lbl, c)
    xc = [FLAG_COLOR if (reveal and i in flags["x"]) else NAVY for i in range(upto)]
    xsz = [15 if (reveal and i in flags["x"]) else 9 for i in range(upto)]
    fig.add_trace(go.Scatter(x=x, y=means[:upto], mode="lines+markers", line=dict(color="#7f8c8d"),
                             marker=dict(size=xsz, color=xc, line=dict(width=1, color="white")),
                             showlegend=False), row=1, col=1)

    # R (row 2)
    for y, c, d, lbl in [(lim["ucl_r"], "#d33", "dash", f"UCL {lim['ucl_r']:.2f}"),
                         (lim["rbar"], "#2a2", "dot", f"CL {lim['rbar']:.2f}"),
                         (lim["lcl_r"], "#d33", "dash", f"LCL {lim['lcl_r']:.2f}")]:
        hline(2, y, c, d); hlabel(2, y, lbl, c)
    rc = [FLAG_COLOR if (reveal and i in flags["r"]) else NAVY for i in range(upto)]
    rsz = [15 if (reveal and i in flags["r"]) else 9 for i in range(upto)]
    fig.add_trace(go.Scatter(x=x, y=ranges[:upto], mode="lines+markers", line=dict(color="#7f8c8d"),
                             marker=dict(size=rsz, color=rc, line=dict(width=1, color="white")),
                             showlegend=False), row=2, col=1)

    # p (row 3) — orange good / green defective; red ring on any flagged point
    for y, c, d, lbl in [(plim["ucl"], "#d33", "dash", f"UCL {plim['ucl']:.3f}"),
                         (plim["pbar"], "#888", "dot", f"p̄ {plim['pbar']:.3f}"),
                         (plim["lcl"], "#d33", "dash", f"LCL {plim['lcl']:.3f}")]:
        hline(3, y, c, d); hlabel(3, y, lbl, c)
    pv = fracs[:upto]
    pfill = [BAD_COLOR if (reveal and (v > plim["ucl"] or v < plim["lcl"])) else GOOD_COLOR for v in pv]
    pline = [FLAG_COLOR if (reveal and i in flags["p"]) else "white" for i in range(upto)]
    pwid = [2 if (reveal and i in flags["p"]) else 1 for i in range(upto)]
    psz = [16 if (reveal and i in flags["p"]) else 10 for i in range(upto)]
    fig.add_trace(go.Scatter(x=x, y=pv, mode="lines+markers", line=dict(color="#c9ced6"),
                             marker=dict(size=psz, color=pfill, line=dict(color=pline, width=pwid)),
                             showlegend=False), row=3, col=1)

    fig.update_xaxes(range=[0, len(means) + 1], row=3, col=1, title_text="Shift")
    for r in (1, 2, 3):
        fig.update_xaxes(range=[0, len(means) + 1], row=r, col=1)
    # Pin y-ranges so the UCL/CL/LCL lines stay on-screen through the whole
    # animation (otherwise auto-scaling to the few streamed points hides them).
    def yr(lo, hi):
        pad = (hi - lo) * 0.12 + 1e-6
        return [lo - pad, hi + pad]
    xlo = min(lim["lcl_x"], float(np.min(means))); xhi = max(lim["ucl_x"], float(np.max(means)))
    rlo = min(lim["lcl_r"], float(np.min(ranges))); rhi = max(lim["ucl_r"], float(np.max(ranges)))
    plo = min(plim["lcl"], float(np.min(fracs))); phi = max(plim["ucl"], float(np.max(fracs)))
    fig.update_yaxes(range=yr(xlo, xhi), row=1, col=1)
    fig.update_yaxes(range=yr(rlo, rhi), row=2, col=1)
    fig.update_yaxes(range=yr(plo, phi), row=3, col=1)
    fig.update_layout(height=740, showlegend=False, margin=dict(l=10, r=64, t=34, b=10))
    return fig


def funnel_fig(you, leave, sigma, show_you=True):
    """Tampering demo: your (adjusting) line vs the leave-alone line on shared noise."""
    fig = go.Figure()
    n = max(len(you), len(leave), 1)
    fig.add_hrect(y0=TARGET_FILL - 3 * sigma, y1=TARGET_FILL + 3 * sigma, line_width=0,
                  fillcolor="rgba(46,204,113,.08)")
    fig.add_hline(y=TARGET_FILL, line=dict(color="#2a2", dash="dot"), annotation_text="target")
    for y in (TARGET_FILL + 3 * sigma, TARGET_FILL - 3 * sigma):
        fig.add_hline(y=y, line=dict(color="#bbb", dash="dash"))
    if leave:
        fig.add_trace(go.Scatter(x=list(range(1, len(leave) + 1)), y=leave,
                                 mode="lines+markers", name="Leave alone (thin green)",
                                 line=dict(color="#27ae60", width=2),
                                 marker=dict(size=6, color="#27ae60", symbol="circle")))
    if show_you and you:
        fig.add_trace(go.Scatter(x=list(range(1, len(you) + 1)), y=you,
                                 mode="lines+markers", name="Adjust each shift (bold red)",
                                 line=dict(color=FLAG_COLOR, width=5),
                                 marker=dict(size=11, color=FLAG_COLOR, symbol="diamond",
                                             line=dict(width=1, color="white"))))
    fig.update_layout(height=360, title="Funnel experiment — same noise, two policies",
                      xaxis_title="Shift", yaxis_title="Fill (mL)",
                      xaxis=dict(range=[0, n + 1]),
                      legend=dict(orientation="h", y=1.12), margin=dict(l=10, r=10, t=54, b=10))
    return fig


# -----------------------------------------------------------------------------
# 8. ANIMATION
# -----------------------------------------------------------------------------
def animate_collection(chart_ph, bottle_ph, grid_ph, data, pcounts, delay, p_inspect=P_INSPECT):
    means = data.mean(axis=1)
    n = len(means)
    xr, yr = [0, n + 1], [means.min() - 7, means.max() + 7]
    frames = [n] if delay <= 0 else range(1, n + 1)
    for i in frames:
        bottle_ph.markdown(bottle_svg(i / n), unsafe_allow_html=True)
        grid_ph.markdown(inspection_scene_svg(p_inspect, int(pcounts[i - 1])),
                         unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_hline(y=TARGET_FILL, line=dict(color="#2a2", dash="dot"), annotation_text="target")
        fig.add_trace(go.Scatter(x=list(range(1, i + 1)), y=means[:i], mode="lines+markers",
                                 line=dict(color=GOOD_COLOR),
                                 marker=dict(size=9, color=GOOD_COLOR, line=dict(width=1, color="white"))))
        fig.update_layout(height=340, showlegend=False, title="Rotterdam — live sampling",
                          xaxis_title="Shift", yaxis_title="Mean fill (mL)",
                          margin=dict(l=10, r=10, t=40, b=10))
        fig.update_xaxes(range=xr); fig.update_yaxes(range=yr)
        chart_ph.plotly_chart(fig, use_container_width=True, key=f"col_{i}")
        if delay > 0:
            time.sleep(delay)


def animate_week(ph, means, ranges, fracs, lim, plim, flags, delay, reveal, tag):
    n = len(means)
    if delay <= 0:
        ph.plotly_chart(week_figure(means, ranges, fracs, lim, plim, n, flags, reveal),
                        use_container_width=True, key=f"wk_{tag}_final")
        return
    for i in range(1, n + 1):
        fl = {c: {k for k in flags[c] if k < i} for c in flags} if reveal else flags
        ph.plotly_chart(week_figure(means, ranges, fracs, lim, plim, i, fl, reveal),
                        use_container_width=True, key=f"wk_{tag}_{i}")
        time.sleep(delay)


# -----------------------------------------------------------------------------
# 9. GAME STATE & ROUND GENERATION
# -----------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    rng = np.random.default_rng(SEED)                       # Director seed → reproducible
    lot_rng = np.random.default_rng(None if SEED is None else SEED + 7)
    if RANDOMIZE_SAMPLING:                                   # per-student n & n_p (seeded)
        sub_n = int(rng.integers(5, 8))                     # 5, 6, or 7
        p_inspect = int(rng.choice([200, 210, 220, 230, 240, 250]))
    else:
        sub_n, p_inspect = SUBGROUP_N, P_INSPECT            # instructor-configured
    d = dict(phase=1, rng=rng, baseline=None, p_baseline=None,
             limits=None, p_limits=None, score=0, rounds_played=0,
             us_sub=None, us_counts=None, us_plan=None,
             answered=False, stream_done=False, reveal_pending=False, ocap_scored=False,
             shipped_bad=0, stopped_good=0, speed_label="Normal",
             funnel_noise=None, funnel_i=0, funnel_setting=TARGET_FILL,
             funnel_you=[], funnel_adjusts=0, funnel_pending=False, funnel_last_e=0.0,
             target_weeks=10, picks={"x": set(), "r": set(), "p": set()},
             total_signals=0, total_caught=0, total_false=0,
             week_missed=0, week_false=0,
             lot_base=int(lot_rng.integers(120, 880)),
             sub_n=sub_n, p_inspect=p_inspect)
    for k, v in d.items():
        ss.setdefault(k, v)


# -----------------------------------------------------------------------------
# 1b. PERSISTENCE — save/restore student progress (safe no-op when unconfigured)
# -----------------------------------------------------------------------------
PROGRESS_KEYS = [
    "phase", "baseline", "p_baseline", "limits", "p_limits", "score", "rounds_played",
    "us_sub", "us_counts", "us_plan",
    "answered", "stream_done", "reveal_pending", "ocap_scored",
    "shipped_bad", "stopped_good", "speed_label",
    "funnel_noise", "funnel_i", "funnel_setting", "funnel_you", "funnel_adjusts",
    "funnel_pending", "funnel_last_e",
    "target_weeks", "picks", "total_signals", "total_caught", "total_false",
    "week_missed", "week_false", "lot_base", "sub_n", "p_inspect",
]
_ARRAY_KEYS = {"baseline", "p_baseline", "us_sub", "us_counts", "funnel_noise"}


def _json_safe(v):
    """Convert numpy arrays/scalars, sets, and nested containers to plain JSON."""
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, set):
        return sorted(v)
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def _restore_value(k, v):
    """Rebuild numpy arrays / sets that JSON flattened to lists."""
    if v is None:
        return None
    if k in _ARRAY_KEYS:
        return np.array(v)
    if k == "picks":
        return {kk: set(vv) for kk, vv in v.items()}
    if k in ("limits", "p_limits"):
        return {kk: (np.array(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()}
    return v


def progress_snapshot():
    """A plain-JSON snapshot of just the progress keys (no figures/RNG/widgets)."""
    ss = st.session_state
    return {k: _json_safe(ss[k]) for k in PROGRESS_KEYS if k in ss}


def autosave():
    """Persist progress after a meaningful step. Best-effort; never crashes the lab."""
    if store.enabled() and SID:
        try:
            store.save(GAME, SID, progress_snapshot())
        except Exception:
            pass


def restore_progress():
    """Copy saved progress back into session_state, once per session."""
    ss = st.session_state
    if not (store.enabled() and SID) or ss.get("_restored"):
        return
    ss["_restored"] = True
    try:
        saved = store.load(GAME, SID)
    except Exception:
        saved = {}
    for k in PROGRESS_KEYS:
        if k in saved:
            ss[k] = _restore_value(k, saved[k])


def new_us_round():
    ss = st.session_state
    lim, plim = ss.limits, ss.p_limits
    xbb, sx = lim["xbarbar"], lim["sigma_xbar"]
    su_x = sx
    su_r, sd_r = sigma_updn(lim["rbar"], lim["ucl_r"], lim["lcl_r"])
    su_p, sd_p = sigma_updn(plim["pbar"], plim["ucl"], plim["lcl"])

    # Pick the week's plan ONCE (so every signal type gets balanced exposure),
    # then resample the DATA until each chart reads cleanly as intended. Because
    # a 5-in-a-row run fires often on random data, this resampling is what keeps
    # in-control weeks looking in control and signal weeks looking crisp.
    if ss.rng.random() < 0.20:
        plan = {"x": "none", "r": "none", "p": "none"}
    else:
        charts = ["x", "r", "p"]
        k = 1 if ss.rng.random() < 0.7 else 2          # 1 or 2 charts carry signals
        chosen = set(np.random.default_rng(ss.rng.integers(1 << 30)).choice(
            charts, size=k, replace=False).tolist())
        plan = {c: (str(ss.rng.choice(SIGNAL_POOL)) if c in chosen else "none")
                for c in charts}

    last = None
    sn, pn = ss.sub_n, ss.p_inspect
    for _ in range(1500):
        sub = make_subgroups(N_BASELINE, n=sn, rng=ss.rng)
        if plan["x"] != "none":
            sub = inject_xbar(sub, plan["x"], xbb, sx, ss.rng, n=sn)
        if plan["r"] != "none":
            sub = inject_range(sub, plan["r"], xbb, sx, lim["rbar"], lim["ucl_r"], ss.rng, n=sn)
        counts = make_defects(N_BASELINE, P_BASELINE_RATE, ss.rng, n_inspect=pn)
        if plan["p"] != "none":
            counts = inject_pcounts(counts, plan["p"], plim["pbar"], plim["ucl"], pn, ss.rng)

        means = sub.mean(1); ranges = sub.max(1) - sub.min(1); fracs = counts / pn
        dx = detect_violations(means, xbb, lim["ucl_x"], lim["lcl_x"], su_x, su_x)
        dr = detect_violations(ranges, lim["rbar"], lim["ucl_r"], lim["lcl_r"], su_r, sd_r,
                               check_lower_near=False)
        dp = detect_violations(fracs, plim["pbar"], plim["ucl"], plim["lcl"], su_p, sd_p,
                               check_lower_near=False)
        last = (sub, counts, plan)
        if (expected_ok(plan["x"], dx) and expected_ok(plan["r"], dr)
                and expected_ok(plan["p"], dp)):
            break

    ss.us_sub, ss.us_counts, ss.us_plan = last
    ss.answered = False
    ss.stream_done = False
    ss.reveal_pending = False
    ss.ocap_scored = False


def us_detection():
    """Recompute the three detections for the current US week."""
    ss = st.session_state
    lim, plim = ss.limits, ss.p_limits
    means = ss.us_sub.mean(1)
    ranges = ss.us_sub.max(1) - ss.us_sub.min(1)
    fracs = ss.us_counts / ss.p_inspect
    su_x = lim["sigma_xbar"]
    su_r, sd_r = sigma_updn(lim["rbar"], lim["ucl_r"], lim["lcl_r"])
    su_p, sd_p = sigma_updn(plim["pbar"], plim["ucl"], plim["lcl"])
    dx = detect_violations(means, lim["xbarbar"], lim["ucl_x"], lim["lcl_x"], su_x, su_x)
    dr = detect_violations(ranges, lim["rbar"], lim["ucl_r"], lim["lcl_r"], su_r, sd_r,
                           check_lower_near=False)
    dp = detect_violations(fracs, plim["pbar"], plim["ucl"], plim["lcl"], su_p, sd_p,
                           check_lower_near=False)
    return means, ranges, fracs, dx, dr, dp


# -----------------------------------------------------------------------------
# 10. UI
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Juicetification: Squeeze Control", page_icon="🧃", layout="wide")

    # Student sign-in gate — only when storage is configured (else behave as today).
    if store.enabled() and SID is None:
        st.markdown("## 🧃 Juicetification: Squeeze Control")
        st.write("You'll get the same scenario every time you return, and your progress "
                 "is saved automatically.")
        entered = st.text_input("Enter your student ID to begin", key="_sid_entry")
        if st.button("Start", type="primary"):
            if entered.strip():
                store.set_student_id(entered.strip())
                st.rerun()
            else:
                st.warning("Please enter a student ID.")
        st.stop()

    init_state()
    inject_theme()
    ss = st.session_state

    restore_progress()          # copy any saved progress back into session_state

    # Persistent factory HUD — brand, running line, product SKU, lot, shift.
    if ss.phase == 4:
        hud_plant, hud_lot = "US", f'{PRODUCTS["US"]["lot"]}-{ss.lot_base + ss.rounds_played:04d}'
        hud_shift = f"Week {ss.rounds_played + 1}"
    elif ss.phase == 5:
        hud_plant = "US"
        hud_lot = f'{PRODUCTS["US"]["lot"]}-{ss.lot_base + max(ss.rounds_played - 1, 0):04d}'
        hud_shift = "Shift report"
    else:
        hud_plant, hud_lot = "NL", f'{PRODUCTS["NL"]["lot"]}-{ss.lot_base:04d}'
        hud_shift = "Baseline run" if ss.phase == 1 else "Day shift"
    factory_hud(hud_plant, hud_lot, hud_shift)
    st.caption("Juicetification: Squeeze Control — Statistical Process Control, "
               "one bottling line at a time.")
    if store.enabled() and SID:
        st.caption(f"Signed in as {SID} · progress saved automatically")

    with st.sidebar:
        st.header("Career status")
        a, b = st.columns(2)
        a.metric("Score", ss.score); b.metric("Weeks", ss.rounds_played)
        st.progress(min(ss.phase / N_PHASES, 1.0), text=PHASE_LABELS[ss.phase])
        ss.speed_label = st.select_slider("Simulation speed", options=list(SPEEDS.keys()),
                                          value=ss.speed_label)
        if ss.phase == 4:
            ss.target_weeks = st.number_input("Weeks to diagnose", min_value=3, max_value=30,
                                              value=ss.target_weeks, step=1,
                                              help="How many weeks you'll diagnose before finishing")
            st.caption("Cost of your calls (P&L)")
            pnl_cards(ss.shipped_bad, ss.stopped_good)
        if st.button("↺ Restart game"):
            st.session_state.clear(); st.rerun()

    delay = SPEEDS[ss.speed_label]

    # ------------------------------------------------------------------ ACT 1
    if ss.phase == 1:
        st.subheader("Act 1 · Rotterdam — establish the baseline")
        plant_banner("NL", "Rotterdam Bottling Plant",
                     "flagship Valencia Orange · 300 mL · your in-control home line")
        mentor_note("Welcome to Rotterdam. Before you touch a single dial, you'll learn what "
                    "'normal' looks like on our Valencia Orange line. Collect a full baseline "
                    "first — limits built on guesswork are worse than none.", **MARGIT)
        st.write(f"Your Dutch plant is **in control**. Each shift you record {ss.sub_n} fill "
                 f"volumes (X-bar & R) and inspect {ss.p_inspect} bottles for defects (p). "
                 f"Collect **{N_BASELINE} subgroups** before building charts.")
        cc, cs = st.columns([3, 1])
        chart_ph, bottle_ph, grid_ph = cc.empty(), cs.empty(), cs.empty()

        if st.button(f"🏭 Run {N_BASELINE} production shifts & sample"):
            ss.baseline = make_subgroups(N_BASELINE, n=ss.sub_n, rng=ss.rng)
            ss.p_baseline = make_defects(N_BASELINE, P_BASELINE_RATE, ss.rng, n_inspect=ss.p_inspect)
            animate_collection(chart_ph, bottle_ph, grid_ph, ss.baseline, ss.p_baseline,
                               delay, p_inspect=ss.p_inspect)
            autosave()

        if ss.baseline is not None:
            means = ss.baseline.mean(axis=1)
            fig = go.Figure()
            fig.add_hline(y=TARGET_FILL, line=dict(color="#2a2", dash="dot"), annotation_text="target")
            fig.add_trace(go.Scatter(x=list(range(1, N_BASELINE + 1)), y=means, mode="lines+markers",
                                     line=dict(color=GOOD_COLOR),
                                     marker=dict(size=9, color=GOOD_COLOR, line=dict(width=1, color="white"))))
            fig.update_layout(height=340, showlegend=False, title="Rotterdam baseline (in control)",
                              xaxis_title="Shift", yaxis_title="Mean fill (mL)",
                              margin=dict(l=10, r=10, t=40, b=10))
            chart_ph.plotly_chart(fig, use_container_width=True, key="a1_final")
            bottle_ph.markdown(bottle_svg(1.0), unsafe_allow_html=True)
            grid_ph.markdown(inspection_scene_svg(ss.p_inspect, int(ss.p_baseline[-1])),
                             unsafe_allow_html=True)
            st.markdown(f'<div class="okbox">✅ Collected {N_BASELINE} subgroups · grand mean ≈ '
                        f'{means.mean():.2f} mL · avg defects/shift ≈ {ss.p_baseline.mean():.1f}</div>',
                        unsafe_allow_html=True)
            if st.button("➡️ Next: a quick experiment before we build charts"):
                ss.phase = 2; autosave(); st.rerun()

    # ---------------------------------------------------- INTERLUDE · FUNNEL
    elif ss.phase == 2:
        st.subheader("Interlude · The Funnel — should you 'correct' the process?")
        plant_banner("NL", "Rotterdam Bottling Plant", "still in the Netherlands · a thought experiment")
        mentor_note("Never touch a stable filler — I'll show you why. New operators always want "
                    "to 'correct' every high or low shift. Try it here first, before it costs us "
                    "real juice.", **MARGIT)
        st.write("Rotterdam is **in control**: every wobble you just saw is *common "
                 "cause* — ordinary noise with no assignable reason. Your instinct is "
                 "to nudge the filler back toward target after a high or low shift. "
                 "Let's test that instinct before you trust a chart.")

        if ss.funnel_noise is None:
            fseed = SEED if SEED is not None else 20260706
            ss.funnel_noise = np.random.default_rng(fseed).normal(0, WITHIN_SIGMA, 60)
        noise = ss.funnel_noise

        pred = st.radio("**Predict:** if you nudge the filler toward target after "
                        "*every* shift, the output will be…",
                        ["More consistent", "No different", "Less consistent"],
                        index=None, key="funnel_predict_w")

        if pred is not None:
            n_noise = len(noise)
            def drop_next():
                if ss.funnel_pending or ss.funnel_i >= n_noise:
                    return
                e = float(noise[ss.funnel_i])
                ss.funnel_you.append(ss.funnel_setting + e)
                ss.funnel_last_e = e
                ss.funnel_i += 1
                ss.funnel_pending = True

            def decide(adjust):
                if not ss.funnel_pending:
                    return
                if adjust:
                    ss.funnel_setting = TARGET_FILL - ss.funnel_last_e   # Deming rule 2
                    ss.funnel_adjusts += 1
                ss.funnel_pending = False

            def auto(adjust, count):
                for _ in range(count):
                    if ss.funnel_i >= n_noise:
                        break
                    e = float(noise[ss.funnel_i])
                    ss.funnel_you.append(ss.funnel_setting + e)
                    ss.funnel_i += 1
                    if adjust:
                        ss.funnel_setting = TARGET_FILL - e
                        ss.funnel_adjusts += 1
                    if delay > 0:                       # animate the line growing
                        render_funnel(key=f"funnel_anim_{ss.funnel_i}")
                        time.sleep(delay)
                ss.funnel_pending = False

            st.caption("Run the plant one shift at a time. You **see the result first**, "
                       "then decide whether to adjust the filler — exactly like reacting to "
                       "a real reading. The **thin green** line is 'leave alone'; the **bold "
                       "red** line is your adjusting policy, both on the identical noise.")

            # Chart into a placeholder so auto-run can animate it growing.
            funnel_ph = st.empty()
            def render_funnel(key="funnel_chart"):
                mm = ss.funnel_i
                yy = ss.funnel_you
                lv = [TARGET_FILL + float(noise[j]) for j in range(mm)]
                funnel_ph.plotly_chart(funnel_fig(yy, lv, WITHIN_SIGMA, show_you=mm > 0),
                                       use_container_width=True, key=key)
            render_funnel()
            m = ss.funnel_i
            you = ss.funnel_you
            leave = [TARGET_FILL + float(noise[j]) for j in range(m)]

            if ss.funnel_pending:
                res, e = ss.funnel_you[-1], ss.funnel_last_e
                st.markdown(f'<div class="alertbox">Shift {ss.funnel_i} filled at '
                            f'<b>{res:.1f} mL</b> — that is {e:+.1f} mL off the 300 mL target. '
                            f'What do you do about the filler?</div>', unsafe_allow_html=True)
                d1, d2 = st.columns(2)
                if d1.button("🔧 Adjust the funnel toward target"):
                    decide(True); st.rerun()
                if d2.button("✋ Leave it alone"):
                    decide(False); st.rerun()
            else:
                b1, b2, b3, b4 = st.columns(4)
                if b1.button("▶️ Run next shift"):
                    drop_next(); st.rerun()
                if b2.button("⏩ Auto-run 10 (adjust each)"):
                    auto(True, 10); st.rerun()
                if b3.button("⏩ Auto-run 10 (leave each)"):
                    auto(False, 10); st.rerun()
                if b4.button("↺ Reset"):
                    ss.funnel_i = 0; ss.funnel_setting = TARGET_FILL
                    ss.funnel_you = []; ss.funnel_adjusts = 0; ss.funnel_pending = False
                    st.rerun()

            if m >= 4:
                sd_you, sd_leave = float(np.std(you)), float(np.std(leave))
                band = 3 * WITHIN_SIGMA
                br_you = sum(abs(v - TARGET_FILL) > band for v in you)
                br_leave = sum(abs(v - TARGET_FILL) > band for v in leave)
                c1, c2, c3 = st.columns(3)
                c1.metric("Shifts run", m)
                c2.metric("SD · leave alone", f"{sd_leave:.2f} mL")
                c3.metric("SD · your policy", f"{sd_you:.2f} mL",
                          delta=f"{sd_you - sd_leave:+.2f}", delta_color="inverse")
                if ss.funnel_adjusts == 0:
                    st.markdown('<div class="okbox">You left it alone every time — your '
                                'spread matches the process\'s natural noise. That is the '
                                'disciplined SPC response to common-cause variation.</div>',
                                unsafe_allow_html=True)
                else:
                    parts = [f"You adjusted {ss.funnel_adjusts} time(s)."]
                    if sd_you > sd_leave + 1e-9:
                        parts.append(f" Reacting to noise <b>widened</b> the spread to "
                                     f"{sd_you:.2f} mL (vs {sd_leave:.2f} leaving alone).")
                    else:
                        parts.append(f" Spread so far is {sd_you:.2f} mL vs {sd_leave:.2f} "
                                     f"leaving alone — keep going (try “Auto-run 10 adjust”) "
                                     f"and watch it widen.")
                    if br_you > br_leave:
                        extra = f" (vs {br_leave} left alone)" if br_leave else ""
                        parts.append(f" It even pushed <b>{br_you} point(s)</b> past the ±3σ "
                                     f"band{extra} — tampering manufactures its own "
                                     f"out-of-control signals.")
                    else:
                        parts.append(" Run more shifts to watch that widening spread start "
                                     "breaking the ±3σ band.")
                    st.markdown('<div class="alertbox">' + "".join(parts) + '</div>',
                                unsafe_allow_html=True)
                st.caption("Deming's funnel: compensating for the last error turns one "
                           "unit of noise into two (variance roughly doubles). The lesson "
                           "for Act 3 — **act only on signals the chart flags, never on "
                           "ordinary wobble.**")

            if m >= 6 and not ss.funnel_pending:
                mentor_note("Now you've felt it. The chart's job is to tell you when a wobble is "
                            "really a signal — so you act on causes, not on noise. Let's build "
                            "those charts.", **MARGIT)
                if st.button("➡️ Proceed to build the charts"):
                    ss.phase = 3; autosave(); st.rerun()

    # ------------------------------------------------------------------ ACT 2
    elif ss.phase == 3:
        st.subheader("Act 2 · Blueprints — build your control charts")
        plant_banner("NL", "Rotterdam Bottling Plant",
                     "building charts from the Netherlands baseline data")
        mentor_note("Here's the real skill: turning that baseline into limits. Do the math "
                    "yourself — pick the right chart, mind your sample sizes, and compute every "
                    "limit. You'll trust a chart you built.", **MARGIT)
        lim = xbar_r_limits(ss.baseline)
        plim = p_chart_limits(ss.p_baseline, n_inspect=ss.p_inspect)
        n, k = ss.sub_n, N_BASELINE
        kf = SPC_CONSTANTS[n]

        # ---- Step 1: choose the right chart for each data type -------------
        st.markdown("#### Step 1 · Which chart fits which data?")
        st.caption("**Variables** data is *measured* on a scale; **attributes** data "
                   "is *counted*. The data type picks the chart.")
        s1a = st.radio("Fill volume — a continuous measurement in mL:",
                       ["X-bar & R chart", "p-chart", "a chart"], index=None, key="sel_var")
        s1b = st.radio("Defective bottles — pass/fail counts per shift:",
                       ["X-bar & R chart", "p-chart", "a chart"], index=None, key="sel_att")
        sel_ok = (s1a == "X-bar & R chart" and s1b == "p-chart")
        if not sel_ok:
            if None not in (s1a, s1b):
                st.error("Not quite. Measured on a scale → **X-bar & R** (variables). "
                         "Pass/fail of each unit → **p-chart** (attributes).")
            st.stop()
        st.success("Right — measurements use X-bar & R; pass/fail uses the p-chart.")

        # ---- Step 2: sample size (n) vs number of samples (k) --------------
        st.markdown("#### Step 2 · Two numbers people mix up")
        st.markdown(nk_diagram_svg(n, k), unsafe_allow_html=True)
        st.caption("You collected the same data two ways at once: **across** each shift "
                   "(bottles in one sample) and **down** the shifts (how many samples).")
        n_opt, k_opt = f"{n} bottles per shift", f"{k} shifts"
        c1, c2 = st.columns(2)
        q_n = c1.radio("**Sample size (n)** for fill is…", [k_opt, n_opt], index=None, key="q_n")
        q_k = c2.radio("**Number of samples (k)** is…", [k_opt, n_opt], index=None, key="q_k")
        if not (q_n == n_opt and q_k == k_opt):
            if q_n is not None and q_k is not None:
                st.error(f"Not quite. **n** counts the items *inside* one sample ({n} bottles). "
                         f"**k** counts how many samples you took ({k} shifts).")
            st.stop()
        st.success(f"Right. n = {n} (items per sample), k = {k} (samples taken).")

        # ---- Step 2b: the DEFECT sample size is different ------------------
        st.markdown("#### Step 3 · The defect sample size is different")
        st.caption("Fill volume and defects were **not** sampled the same way. Check the "
                   "data-collection totals below.")
        st.markdown(f"- Fill: **{n}** bottles *measured* per shift.\n"
                    f"- Defects: **{ss.p_inspect}** bottles *inspected* per shift.")
        np_opt = str(ss.p_inspect)
        q_np = st.radio("What is the **sample size for the p-chart** (bottles inspected per shift)?",
                        [str(n), str(k), np_opt], index=None, key="q_np")
        if q_np != np_opt:
            if q_np is not None:
                st.error("Re-read the totals — the p-chart's sample size is the number of "
                         f"bottles **inspected** each shift, not the {n} measured for fill.")
            st.stop()
        st.success(f"Right — the p-chart sample size is n_p = {ss.p_inspect} bottles per shift.")
        st.info("**Why different?** Measuring exact fill volume is slow and costly, so you "
                f"measure just {n} bottles. A defective/OK check is a fast pass/fail, "
                f"so you can inspect many more ({ss.p_inspect}). Attribute data also carries less "
                "information per bottle — only 0 or 1 — and defects are rare (~4%), so a large "
                "sample is needed to estimate the defect rate reliably. That larger n_p is why "
                "the p-chart limits sit closer to p̄ than you might expect.")

        # ---- Step 4: centerlines FROM the Netherlands data ----------------
        st.markdown("#### Step 4 · Calculate the centerlines from the data")
        st.caption(f"These {N_BASELINE} shifts set every centerline: X̄̄ is the mean of the shift "
                   "means, R̄ the mean of the ranges, p̄ the total defects over all bottles inspected.")
        sub, pc = ss.baseline, ss.p_baseline
        table = {"Shift": list(range(1, N_BASELINE + 1))}
        for b in range(n):
            table[f"Bottle {b+1}"] = [round(float(sub[i, b]), 1) for i in range(N_BASELINE)]
        table["Mean X̄"] = [round(float(sub[i].mean()), 2) for i in range(N_BASELINE)]
        table["Range R"] = [round(float(sub[i].max() - sub[i].min()), 2) for i in range(N_BASELINE)]
        table["Defects"] = [int(pc[i]) for i in range(N_BASELINE)]
        st.dataframe(table, use_container_width=True, hide_index=True, height=240)
        st.caption(f"Totals: {N_BASELINE} shifts · {n} bottles/shift measured for fill "
                   f"· {ss.p_inspect} bottles/shift inspected ({N_BASELINE*ss.p_inspect:,} inspected, "
                   f"{int(pc.sum())} defective).")
        z1, z2, z3 = st.columns(3)
        cl_x = z1.number_input("X̄̄ — grand mean (mL)", value=None, step=0.01, format="%.2f", key="cl_x")
        cl_r = z2.number_input("R̄ — mean range (mL)", value=None, step=0.01, format="%.2f", key="cl_r")
        cl_p = z3.number_input("p̄ — mean fraction defective", value=None, step=0.001, format="%.3f", key="cl_p")
        cl_fields = [("X̄̄", cl_x, lim["xbarbar"], 0.15),
                     ("R̄", cl_r, lim["rbar"], 0.15),
                     ("p̄", cl_p, plim["pbar"], 0.003)]
        cl_wrong = [(nm, v) for nm, v, t, tol in cl_fields if v is not None and abs(v - t) > tol]
        cl_ok = all(v is not None and abs(v - t) <= tol for _, v, t, tol in cl_fields)
        for nm, v in cl_wrong:
            st.warning(f"**{nm}** isn't right yet — "
                       + centerline_hint(nm, v, lim["xbarbar"], lim["rbar"], plim["pbar"],
                                         p_inspect=ss.p_inspect))
        with st.expander("🆘 Stuck? Formulas & a divisor check", expanded=bool(cl_wrong)):
            st.markdown("The centerlines are plain averages. Standard formulas:")
            st.latex(r"\bar{\bar X}=\frac{\sum_{i=1}^{k}\bar X_i}{k}\qquad "
                     r"\bar R=\frac{\sum_{i=1}^{k} R_i}{k}\qquad "
                     r"\bar p=\frac{\sum_{i=1}^{k} d_i}{k\,n_p}")
            st.markdown("Sum the matching column, then divide. Confirm the divisors you'll use "
                        "(this flags the common mistake — it won't compute the averages for you):")
            dd1, dd2 = st.columns(2)
            vk = dd1.number_input("k (number of samples) =", value=None, step=1, format="%d", key="h_k")
            vtot = dd2.number_input("divisor for p̄  (total bottles inspected) =", value=None,
                                    step=1, format="%d", key="h_tot")
            dbad = []
            if vk is not None and int(vk) != N_BASELINE:
                dbad.append("k should be the number of shifts")
            if vtot is not None and int(vtot) != N_BASELINE * ss.p_inspect:
                dbad.append("for p̄ the divisor is k × n_p (total bottles inspected), not k")
            if dbad:
                st.warning("Check: " + "; ".join(dbad) + ".")
            elif vk is not None or vtot is not None:
                st.success("Right divisors — now sum each column and divide.")
        if not cl_ok:
            st.stop()
        st.success(f"Centerlines set — X̄̄ = {lim['xbarbar']:.2f} mL, R̄ = {lim['rbar']:.2f} mL, "
                   f"p̄ = {plim['pbar']:.3f}.")

        # ---- Step 5: select the constants from the table ------------------
        st.markdown("#### Step 5 · Select the constants from the table")
        st.caption(f"The constants depend on the **sample size n** (of the fill data), not the "
                   f"number of samples k — read the row for n = {n}.")
        tbl = {"n": [], "A₂": [], "D₃": [], "D₄": []}
        for nn in sorted(SPC_CONSTANTS):
            kk = SPC_CONSTANTS[nn]
            tbl["n"].append(nn); tbl["A₂"].append(kk["A2"])
            tbl["D₃"].append(kk["D3"]); tbl["D₄"].append(kk["D4"])
        st.dataframe(tbl, use_container_width=True, hide_index=True)
        fmt = lambda v: "—" if v is None else f"{v:.3f}"
        a2o = [None] + sorted({SPC_CONSTANTS[i]["A2"] for i in SPC_CONSTANTS})
        d3o = [None] + sorted({SPC_CONSTANTS[i]["D3"] for i in SPC_CONSTANTS})
        d4o = [None] + sorted({SPC_CONSTANTS[i]["D4"] for i in SPC_CONSTANTS})
        s1, s2, s3 = st.columns(3)
        sa2 = s1.selectbox(f"A₂ for n = {n}", a2o, format_func=fmt, key="sel_a2")
        sd3 = s2.selectbox(f"D₃ for n = {n}", d3o, format_func=fmt, key="sel_d3")
        sd4 = s3.selectbox(f"D₄ for n = {n}", d4o, format_func=fmt, key="sel_d4")
        const_ok = (sa2 == kf["A2"] and sd3 == kf["D3"] and sd4 == kf["D4"])
        if not const_ok:
            if any(v is not None for v in (sa2, sd3, sd4)):
                st.warning(f"Not the n = {n} row yet — line each value up with n = {n}.")
            st.stop()
        st.success(f"Correct — for n = {n}: A₂ = {kf['A2']}, D₃ = {kf['D3']}, D₄ = {kf['D4']}.")

        # ---- Step 6: calculate EVERY control limit ------------------------
        st.markdown("#### Step 6 · Now calculate every control limit")
        st.latex(r"\bar{\bar X}=%.2f\ \text{mL}\quad \bar R=%.2f\ \text{mL}\quad \bar p=%.3f"
                 % (lim["xbarbar"], lim["rbar"], plim["pbar"]))
        st.latex(r"A_2=%.3f,\ D_3=%.3f,\ D_4=%.3f\qquad n_p=%d"
                 % (kf["A2"], kf["D3"], kf["D4"], ss.p_inspect))
        cX, cR, cP = st.columns(3)
        cX.markdown("**X̄ chart (mL)**")
        ax_u = cX.number_input("UCL X̄", value=None, step=0.01, format="%.2f", key="c_ux")
        ax_l = cX.number_input("LCL X̄", value=None, step=0.01, format="%.2f", key="c_lx")
        cR.markdown("**R chart (mL)**")
        ar_u = cR.number_input("UCL R", value=None, step=0.01, format="%.2f", key="c_ur")
        ar_l = cR.number_input("LCL R", value=None, step=0.01, format="%.2f", key="c_lr")
        cP.markdown("**p chart (fraction)**")
        ap_u = cP.number_input("UCL p", value=None, step=0.001, format="%.3f", key="c_up")
        ap_l = cP.number_input("LCL p", value=None, step=0.001, format="%.3f", key="c_lp")

        fields = [("UCL X̄", ax_u, lim["ucl_x"], 0.3), ("LCL X̄", ax_l, lim["lcl_x"], 0.3),
                  ("UCL R", ar_u, lim["ucl_r"], 0.3), ("LCL R", ar_l, lim["lcl_r"], 0.3),
                  ("UCL p", ap_u, plim["ucl"], 0.004), ("LCL p", ap_l, plim["lcl"], 0.004)]
        n_ok = sum(v is not None and abs(v - t) <= tol for _, v, t, tol in fields)
        wrong = [(nm, v) for nm, v, t, tol in fields if v is not None and abs(v - t) > tol]
        all_ok = n_ok == 6
        st.caption(f"Correct so far: **{n_ok} / 6**")
        ctx = dict(xbb=lim["xbarbar"], rbar=lim["rbar"], pbar=plim["pbar"],
                   a2=kf["A2"], d3=kf["D3"], d4=kf["D4"], ucl_x=lim["ucl_x"], lcl_x=lim["lcl_x"],
                   ucl_r=lim["ucl_r"], lcl_r=lim["lcl_r"], ucl_p=plim["ucl"], lcl_p=plim["lcl"],
                   np=ss.p_inspect, fill_n=n)
        for nm, v in wrong:
            st.warning(f"**{nm}** isn't right yet — " + limit_hint(nm, v, ctx))
        with st.expander("🆘 Stuck? Formulas & a variable check", expanded=bool(wrong)):
            st.markdown("The standard formulas are below. Enter the **value of each variable** — "
                        "the check flags any that are wrong. It won't compute the limits; that "
                        "last multiply-and-add step is yours.")
            st.latex(r"UCL_{\bar X}=\bar{\bar X}+A_2\bar R \qquad LCL_{\bar X}=\bar{\bar X}-A_2\bar R")
            st.latex(r"UCL_R=D_4\bar R \qquad LCL_R=D_3\bar R")
            st.latex(r"UCL_p=\bar p+3\sqrt{\tfrac{\bar p(1-\bar p)}{n_p}} \qquad "
                     r"LCL_p=\max\!\left(0,\ \bar p-3\sqrt{\tfrac{\bar p(1-\bar p)}{n_p}}\right)")
            hv = {}
            hc = st.columns(4)
            hv["X̄̄"] = hc[0].number_input("X̄̄ =", value=None, step=0.01, format="%.2f", key="h_xbb")
            hv["R̄"] = hc[1].number_input("R̄ =", value=None, step=0.01, format="%.2f", key="h_rbar")
            hv["p̄"] = hc[2].number_input("p̄ =", value=None, step=0.001, format="%.3f", key="h_pbar")
            hv["n_p"] = hc[3].number_input("n_p =", value=None, step=1, format="%d", key="h_np")
            hc2 = st.columns(3)
            hv["A₂"] = hc2[0].number_input("A₂ =", value=None, step=0.001, format="%.3f", key="h_a2")
            hv["D₃"] = hc2[1].number_input("D₃ =", value=None, step=0.001, format="%.3f", key="h_d3")
            hv["D₄"] = hc2[2].number_input("D₄ =", value=None, step=0.001, format="%.3f", key="h_d4")
            vt = {"X̄̄": (lim["xbarbar"], 0.05), "R̄": (lim["rbar"], 0.05), "p̄": (plim["pbar"], 0.002),
                  "n_p": (ss.p_inspect, 0.5), "A₂": (kf["A2"], 0.001), "D₃": (kf["D3"], 0.001),
                  "D₄": (kf["D4"], 0.001)}
            vbad = [nm for nm, (t, tol) in vt.items() if hv[nm] is not None and abs(hv[nm] - t) > tol]
            if vbad:
                st.warning("These variable values look wrong: **" + ", ".join(vbad) + "**. "
                           "Recheck them against Steps 4–5, then apply the formulas.")
            elif any(hv[nm] is not None for nm in vt):
                st.success("Those variable values are correct — now plug them into the formulas "
                           "and compute each limit.")
        if not all_ok:
            st.stop()
        st.success("All six correct — you built every limit yourself. 🎉")
        with st.expander("See the worked calculation"):
            st.latex(r"UCL_{\bar X}=%.2f+%.3f\times%.2f=%.2f"
                     % (lim["xbarbar"], kf["A2"], lim["rbar"], lim["ucl_x"]))
            st.latex(r"LCL_{\bar X}=%.2f-%.3f\times%.2f=%.2f"
                     % (lim["xbarbar"], kf["A2"], lim["rbar"], lim["lcl_x"]))
            st.latex(r"UCL_R=%.3f\times%.2f=%.2f\qquad LCL_R=%.3f\times%.2f=%.2f"
                     % (kf["D4"], lim["rbar"], lim["ucl_r"], kf["D3"], lim["rbar"], lim["lcl_r"]))
            st.latex(r"UCL_p=%.3f+3\sqrt{\tfrac{%.3f(1-%.3f)}{%d}}=%.3f"
                     % (plim["pbar"], plim["pbar"], plim["pbar"], ss.p_inspect, plim["ucl"]))
            st.latex(r"LCL_p=\max\!\left(0,\;%.3f-3\sqrt{\tfrac{%.3f(1-%.3f)}{%d}}\right)=%.3f"
                     % (plim["pbar"], plim["pbar"], plim["pbar"], ss.p_inspect, plim["lcl"]))

        c1, c2 = st.columns(2)
        c1.plotly_chart(single_chart(lim["means"], lim["xbarbar"], lim["ucl_x"], lim["lcl_x"],
                        "X-bar (baseline)", "Mean fill (mL)", sigma=lim["sigma_xbar"]),
                        use_container_width=True, key="a2_x")
        c2.plotly_chart(single_chart(lim["ranges"], lim["rbar"], lim["ucl_r"], lim["lcl_r"],
                        "R (baseline)", "Range (mL)"), use_container_width=True, key="a2_r")
        st.plotly_chart(p_chart_fig(ss.p_baseline, plim["pbar"], plim["ucl"], plim["lcl"],
                        n_inspect=ss.p_inspect, neutral=True, title="p-chart (baseline)"),
                        use_container_width=True, key="a2_p")
        if st.button("✅ Certify charts & open the US franchise"):
            ss.limits, ss.p_limits, ss.phase = lim, plim, 4
            new_us_round(); autosave(); st.rerun()

    # ------------------------------------------------------------------ ACT 3
    elif ss.phase == 4:
        st.subheader("Act 3 · Route 66 — police the franchise")
        plant_banner("US", "Route 66 Bottling Plant",
                     "launching Route 66 Mango · 300 mL · same certified limits from Rotterdam")
        if ss.rounds_played == 0:
            mentor_note("Rotterdam's certified — congratulations. We're opening a franchise on "
                        "Route 66 in the States, launching Mango. Same charts, new line. Go make "
                        "sure it runs clean.", **HQ)
            mentor_note("Watch all three charts every week. When one signals, find the cause "
                        "before you touch anything — remember the funnel. Call me if a capper "
                        "acts up.", **MARGIT)
        st.write("Any of the three charts may go out of control this week, and one "
                 "chart can show more than one signal. **Diagnose each chart.**")
        lim, plim = ss.limits, ss.p_limits

        # Certified control limits carried over from Rotterdam — shown explicitly.
        def _lim_cell(label, lcl, cl, ucl, fmt):
            return (f'<div style="flex:1;min-width:150px;background:#f8fafc;border:1px solid '
                    f'#e5e9f0;border-radius:10px;padding:8px 12px;margin:4px">'
                    f'<div style="font-weight:700;color:#1f2733;font-size:.85rem">{label}</div>'
                    f'<div style="font-size:.8rem;color:#5b6472">'
                    f'UCL {ucl:{fmt}} · CL {cl:{fmt}} · LCL {lcl:{fmt}}</div></div>')
        st.markdown(
            '<div style="display:flex;flex-wrap:wrap;margin:2px 0 8px">'
            + _lim_cell("X̄ chart (mL)", lim["lcl_x"], lim["xbarbar"], lim["ucl_x"], ".2f")
            + _lim_cell("R chart (mL)", lim["lcl_r"], lim["rbar"], lim["ucl_r"], ".2f")
            + _lim_cell("p chart (fraction)", plim["lcl"], plim["pbar"], plim["ucl"], ".3f")
            + '</div>', unsafe_allow_html=True)

        means, ranges, fracs, dx, dr, dp = us_detection()
        flags = {"x": set().union(*dx.values()) if dx else set(),
                 "r": set().union(*dr.values()) if dr else set(),
                 "p": set().union(*dp.values()) if dp else set()}
        truth = {"x": set(dx), "r": set(dr), "p": set(dp)}

        with st.expander("📋 Signal reference card"):
            st.markdown(
                f"- **Beyond the limits** — a point past a red UCL/LCL line.\n"
                f"- **Run** — {RUN_LEN}+ points in a row on one side of the centerline.\n"
                f"- **Trend** — {TREND_LEN}+ points steadily rising or falling.\n"
                f"- **Two near a limit** — 2 points in a row inside the shaded 2σ zone.")

        chart_ph = st.empty()

        if not ss.answered:
            if not ss.stream_done:
                animate_week(chart_ph, means, ranges, fracs, lim, plim, flags, delay,
                             reveal=False, tag="pre")
                ss.stream_done = True
            else:
                chart_ph.plotly_chart(week_figure(means, ranges, fracs, lim, plim, len(means),
                                      flags, reveal=False), use_container_width=True, key="wk_pre_static")

            st.write("**Diagnose each chart** — leave a box on **Process in control** if that "
                     "chart shows no signal:")
            cx, cr, cp = st.columns(3)
            px = cx.multiselect("X-bar signals", list(RULE_LABELS), key="pick_x",
                                placeholder="Process in control",
                                format_func=lambda k: RULE_LABELS[k])
            pr = cr.multiselect("R signals", list(RULE_LABELS), key="pick_r",
                                placeholder="Process in control",
                                format_func=lambda k: RULE_LABELS[k])
            pp = cp.multiselect("p signals", list(RULE_LABELS), key="pick_p",
                                placeholder="Process in control",
                                format_func=lambda k: RULE_LABELS[k])
            if st.button("🔍 Submit analysis"):
                picks = {"x": set(px), "r": set(pr), "p": set(pp)}
                total_missed = total_false = total_hits = total_sig = 0
                for c in ("x", "r", "p"):
                    t, p = truth[c], picks[c]
                    hits, missed, false = p & t, t - p, p - t
                    if not t and not p:
                        ss.score += 5
                    else:
                        ss.score += max(0, 5 * len(hits) - 3 * len(false))
                    total_missed += len(missed); total_false += len(false)
                    total_hits += len(hits); total_sig += len(t)
                ss.picks = picks
                ss.shipped_bad += total_missed
                ss.stopped_good += total_false
                ss.week_missed = total_missed
                ss.week_false = total_false
                ss.total_caught += total_hits
                ss.total_signals += total_sig
                ss.total_false += total_false
                ss.rounds_played += 1
                ss.answered = True
                ss.reveal_pending = True
                autosave()
                st.rerun()
        else:
            if ss.reveal_pending:
                animate_week(chart_ph, means, ranges, fracs, lim, plim, flags, delay,
                             reveal=True, tag="rev")
                ss.reveal_pending = False
            else:
                chart_ph.plotly_chart(week_figure(means, ranges, fracs, lim, plim, len(means),
                                      flags, reveal=True), use_container_width=True, key="wk_rev_static")

            any_signal = any(truth.values())
            names = {"x": "X-bar", "r": "R", "p": "p"}
            if any_signal:
                parts = [f'{names[c]}: ' + ", ".join(RULE_LABELS[s] for s in truth[c])
                         for c in ("x", "r", "p") if truth[c]]
                st.markdown('<div class="alertbox">🚨 OUT OF CONTROL — ' +
                            " · ".join(parts) + '</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="okbox">✅ All three charts in control this week.</div>',
                            unsafe_allow_html=True)

            plan = ss.us_plan
            cause_parts = []
            for c in ("x", "r", "p"):
                if truth[c]:
                    sig = plan[c] if plan[c] != "none" else "combo"
                    st.write(f"**{names[c]} root cause:** " + CAUSES[c].get(sig, ""))
                    cause_parts.append(PART_FOR.get((c, sig)))
            cause_parts = [p for p in dict.fromkeys(cause_parts) if p]  # dedupe, keep order
            if cause_parts:
                st.caption("The culprit part:")
                pcols = st.columns(len(cause_parts))
                for col, part in zip(pcols, cause_parts):
                    col.markdown(part_diagram_svg(part), unsafe_allow_html=True)

            # ---- Clear right/wrong breakdown of the diagnosis --------------
            st.markdown("**How your diagnosis scored:**")
            picks = ss.picks
            rows = ""
            for c in ("x", "r", "p"):
                t, p = truth[c], picks[c]
                hit, miss, fa = p & t, t - p, p - t
                cells = []
                for s in hit:
                    cells.append(f'<span style="color:#1e8449">✓ {RULE_LABELS[s]}</span>')
                for s in miss:
                    cells.append(f'<span style="color:#c0392b">✗ missed {RULE_LABELS[s]}</span>')
                for s in fa:
                    cells.append(f'<span style="color:#e67e22">⚠ false alarm: {RULE_LABELS[s]}</span>')
                if not t and not p:
                    cells.append('<span style="color:#1e8449">✓ correctly called in control</span>')
                if not cells:
                    cells.append('<span style="color:#8a8f98">—</span>')
                rows += (f'<tr><td style="padding:4px 10px;font-weight:700;color:#1f2733">'
                         f'{names[c]}</td><td style="padding:4px 10px">'
                         + " · ".join(cells) + '</td></tr>')
            st.markdown(
                '<table style="border-collapse:collapse;width:100%;background:#f8fafc;'
                'border:1px solid #e5e9f0;border-radius:10px">' + rows + '</table>'
                '<div style="font-size:.8rem;color:#5b6472;margin-top:4px">'
                '✓ correct · ✗ missed (ships bad juice) · ⚠ false alarm (needless line stop)</div>',
                unsafe_allow_html=True)

            # This week's dollar impact — ties the decision to the P&L
            wr = ss.week_missed * COST_RECALL
            wf = ss.week_false * COST_LINESTOP
            if wr or wf:
                bits = []
                if wr:
                    bits.append(f"${wr:,.0f} in recalls ({ss.week_missed} missed)")
                if wf:
                    bits.append(f"${wf:,.0f} in lost production ({ss.week_false} false alarm"
                                f"{'s' if ss.week_false != 1 else ''})")
                st.markdown(f'<div class="alertbox">💸 This week cost ' + " + ".join(bits)
                            + f' = <b>${wr + wf:,.0f}</b>.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="okbox">💰 Clean, accurate week — $0 in quality costs, '
                            'full production shipped.</div>', unsafe_allow_html=True)

            # ---- OCAP: what do you actually DO about it? --------------------
            st.markdown("**Out-of-control action plan — your first move:**")
            if any_signal:
                opts = ["🔎 Investigate — find the assignable cause, then fix that",
                        "🔧 Adjust the filler back toward target now",
                        "🤷 Ignore it and keep running"]
            else:
                opts = ["✋ Leave the process alone — no action needed",
                        "🔧 Adjust the filler toward target to be safe",
                        "🛑 Stop the line to investigate"]
            correct = opts[0]
            choice = st.radio("Choose one:", opts, index=None, key=f"ocap_{ss.rounds_played}")
            if choice is not None:
                if not ss.ocap_scored:
                    if choice == correct:
                        ss.score += 4
                    ss.ocap_scored = True
                if choice == correct:
                    st.success("Right first move. Confirm the cause before you touch the "
                               "process — reacting blindly is how tampering starts."
                               if any_signal else
                               "Right — a stable process needs no action. Adjusting it would "
                               "only add variation. That's the funnel lesson in practice.")
                elif "Adjust" in choice:
                    st.warning("That's tampering. Changing the process before you know the "
                               "cause chases noise and *adds* variation — exactly what the "
                               "funnel showed. Investigate first."
                               if any_signal else
                               "That's tampering — the process was in control, so adjusting "
                               "only adds variation (remember the funnel).")
                elif "Ignore" in choice:
                    st.warning("Ignoring a real signal ships defective juice — the assignable "
                               "cause keeps producing bad product until you act on it.")
                else:
                    st.warning("Stopping a stable line is a false alarm — a needless line stop "
                               "that costs output for no reason.")
                if st.button("▶️ Next production week"):
                    new_us_round(); autosave(); st.rerun()

        # ---- Progress toward the diagnosis goal & finish -------------------
        st.divider()
        done, goal = ss.rounds_played, ss.target_weeks
        st.progress(min(done / goal, 1.0), text=f"Weeks diagnosed: {done} / {goal}")
        if done >= goal:
            if st.button("🏁 Finish & view your results", type="primary"):
                ss.phase = 5; autosave(); st.rerun()
        else:
            st.caption(f"Diagnose {goal - done} more week(s) to finish "
                       "(adjust the goal in the sidebar).")

    # ------------------------------------------------------------------ RESULTS
    elif ss.phase == 5:
        st.subheader("🏁 Results — Juicetification Inc.")
        mentor_note("Good work running Route 66. You collected a baseline, built the charts, "
                    "and told real signals from noise. That's process control. Send HQ your code "
                    "and take the win.", **MARGIT)
        weeks = ss.rounds_played
        caught, sig = ss.total_caught, ss.total_signals
        recall = (caught / sig * 100) if sig else 100.0
        m1, m2, m3 = st.columns(3)
        m1.metric("Final score", ss.score)
        m2.metric("Weeks diagnosed", weeks)
        m3.metric("Signals caught", f"{caught}/{sig}" if sig else "—",
                  help="Share of real out-of-control signals you detected")
        n1, n2, n3 = st.columns(3)
        n1.metric("Detection rate", f"{recall:.0f}%")
        n2.metric("Bad juice shipped", ss.shipped_bad,
                  help="Missed signals (Type II errors)")
        n3.metric("Needless line stops", ss.stopped_good,
                  help="False alarms (Type I errors)")

        # ---- Plant P&L: the dollar cost of quality decisions ----
        recall_cost = ss.shipped_bad * COST_RECALL
        stop_cost = ss.stopped_good * COST_LINESTOP
        total_cost = recall_cost + stop_cost
        per_week = total_cost / weeks if weeks else 0
        st.markdown("#### Plant P&L — the cost of your quality decisions")
        p1, p2, p3 = st.columns(3)
        p1.metric("Recalls (Type II)", f"${recall_cost:,.0f}",
                  f"{ss.shipped_bad} missed × ${COST_RECALL:,}", delta_color="off")
        p2.metric("Lost production (Type I)", f"${stop_cost:,.0f}",
                  f"{ss.stopped_good} stops × ${COST_LINESTOP:,}", delta_color="off")
        p3.metric("Total quality cost", f"${total_cost:,.0f}", f"${per_week:,.0f}/week",
                  delta_color="off")
        if total_cost == 0:
            st.markdown('<div class="okbox">💰 Zero quality cost — every call was accurate. '
                        'That is what SPC is worth to the business.</div>', unsafe_allow_html=True)
        elif recall_cost > stop_cost:
            st.markdown(f'<div class="alertbox">Most of your ${total_cost:,.0f} loss came from '
                        f'<b>recalls</b> — missed signals shipped bad juice. Look at the control '
                        f'chart more carefully before finalizing your diagnosis.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="alertbox">Most of your ${total_cost:,.0f} loss came from '
                        f'<b>line stops</b> — false alarms halted good production. Don\'t react '
                        f'to ordinary wobble (remember the funnel).</div>', unsafe_allow_html=True)

        # Customer trust drops with recalls (shipped defects hurt reputation)
        rate = ss.shipped_bad / weeks if weeks else 0
        stars = 5 if ss.shipped_bad == 0 else max(1, int(round(5 - rate * 3)))
        st.caption("Customer trust: " + "★" * stars + "☆" * (5 - stars)
                   + ("  (spotless record)" if stars == 5 else "  (recalls erode trust)"))

        if ss.shipped_bad > ss.stopped_good + 1:
            tendency = ("You tend to **under-call** — a few real signals slipped through. "
                        "Look one more beat before clearing a chart.")
        elif ss.stopped_good > ss.shipped_bad + 1:
            tendency = ("You tend to **over-call** — some calls were false alarms. Remember "
                        "the funnel: don't react to ordinary wobble.")
        else:
            tendency = "You balanced misses and false alarms well — a steady hand on the line."
        st.markdown(f'<div class="okbox">{tendency}</div>', unsafe_allow_html=True)

        st.markdown("#### Submit to your LMS")
        st.write("Enter your name or student ID to generate a completion code, then paste "
                 "it into your assignment.")
        nm = st.text_input("Name or student ID", key="lms_name")
        if nm.strip():
            code = completion_code(nm, ss.score, weeks)
            st.code(code, language=None)
            st.caption("This code encodes your name, weeks played, and score with a checksum "
                       "your instructor can verify — it can't be guessed or reused by someone "
                       "else. Copy it into the LMS submission box.")
            if store.enabled() and SID and not ss.get("_completion_recorded"):
                try:
                    store.record_completion(GAME, SID, completion_code=code, score=ss.score)
                    ss["_completion_recorded"] = True
                except Exception:
                    pass

        c1, c2 = st.columns(2)
        if c1.button("▶️ Diagnose more weeks"):
            ss.phase = 4; new_us_round(); autosave(); st.rerun()
        if c2.button("↺ Restart game"):
            st.session_state.clear(); st.rerun()


if __name__ == "__main__":
    main()
