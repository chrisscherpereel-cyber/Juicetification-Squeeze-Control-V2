# 🧃 Juicetification: Squeeze Control

**A hands-on Statistical Process Control (SPC) simulation, disguised as running a juice-bottling company.**

Students step into the role of a quality engineer at *Juicetification Inc.* They collect baseline data on a stable bottling line, learn the counter-intuitive lesson that "correcting" a stable process makes it worse, build the X‑bar, R, and p control charts **by doing the math themselves**, then police a new franchise week after week — telling real out-of-control signals from ordinary noise while the plant P&L reacts to every call.

A one‑page visual quick-start is included: **[`instructions.pdf`](instructions.pdf)**.

---

## What students learn

- **Variables vs. attributes charts** — choosing X‑bar & R for measurements, a p‑chart for pass/fail counts.
- **Calculating control limits** from the data and the standard constants (A₂, D₃, D₄), including every UCL/LCL by hand.
- **Sample size (n) vs. number of samples (k)** — and why the fill chart and the defect chart use *different* sample sizes.
- **Common cause vs. special cause** — via a Deming funnel experiment that shows tampering roughly doubles variation.
- **Reading control charts** — points beyond limits, runs, trends, and two‑near‑a‑limit signals, on all three charts at once.
- **Type I vs. Type II errors** — false alarms (needless line stops) vs. missed signals (recalls), each with a dollar cost.
- **Out‑of‑control action plans (OCAP)** — investigate the assignable cause before touching the process.

## The five stages

| Stage | Setting | What you do |
|------|---------|-------------|
| **Act 1 · Rotterdam** | 🇳🇱 Netherlands | Run 24 shifts and collect a baseline (fill volumes + defect counts) from an in‑control line. |
| **Interlude · The Funnel** | 🇳🇱 Netherlands | Adjust vs. leave-alone, shift by shift, and watch tampering widen the spread. |
| **Act 2 · Blueprints** | 🇳🇱 Netherlands | Pick the right chart, separate n from k, compute the centerlines and **all** the control limits yourself. |
| **Act 3 · Route 66** | 🇺🇸 United States | Diagnose each week's three charts, choose an action plan, and watch the P&L. |
| **Results** | — | Score, detection rate, plant P&L, customer trust, and an LMS completion code. |

## Quick start

```bash
pip install -r requirements.txt
streamlit run juicetification.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`). Use the sidebar to set the **simulation speed** and the **number of weeks to diagnose**.

> **Note:** requires Streamlit **1.30+** (the calculation steps use empty‑by‑default number inputs).

## Every student gets a different problem

By default the app generates a **fresh in-control baseline on every session** from an unseeded random generator, so each student's centerlines and limits differ and exact answers can't be copied. Sample sizes are set by configuration (default fill `n = 5`, defect `nₚ = 200`) — see below to change them per class. (For `n = 7`, note `D₃ = 0.076`, so `LCL_R` is *not* zero — a nice check that students really computed it.)

Want to go further and give **each student a different sample size** too? Set `randomize_sampling` to `true` (Director param) and the app draws `n ∈ {5,6,7}` and `nₚ ∈ {200,210,…,250}` per session from the seeded stream — so it's random without a seed and reproducible with one.

Need a **reproducible** problem for grading or make-ups? Pass a seed in the URL (`?seed=42`) and the entire session — sample sizes (if randomized), baseline, weekly charts, and funnel — becomes deterministic.

## Instructor configuration (Juicetification Director)

The app ships with a tiny, dependency-free config layer (`juice_director.py` + `manifest.py`) so an instructor can tune it **from the URL** without editing code. With no config parameters present, the app runs on its built-in defaults, unchanged.

- **Discover the parameters:** open `…/?manifest=1` to print this app's parameter schema as JSON.
- **Configure via a self-contained link:** `…/?cfg=<base64 JSON>`, e.g. base64 of `{"target_fill_ml":250,"cost_recall":50000}` sets the fill target and recall cost.
- **Reproducible seed:** add `?seed=<int>`; optional `?sec=<section>` and `?game=<code>` are passed through as context.

Configurable parameters (defaults in parentheses): fill target mL (300), within-subgroup σ (2.0), spec low/high (294 / 306), subgroup size *n* (5; one of 2–7), baseline subgroups (24), bottles inspected/shift (200), in-control fraction defective (0.04), $ per missed signal / Type II (12000), $ per false alarm / Type I (3500), trend length (5), and the completion-code secret (`squeeze-control-2026`). Out-of-range or invalid values fall back to the default. The control-chart constants (A₂, D₃, D₄, d₂) are **not** configurable — they're fixed statistical constants keyed by subgroup size.

## Student progress & persistence (optional)

The app can save each student's progress and give them a **stable, unique scenario** that resumes across visits, via `student_store.py` (encrypted records in Dropbox). This is entirely optional: **when the storage secrets are not configured, every storage call is a safe no-op and the app behaves exactly as above.**

When it *is* configured (see the secrets below):

- Students are identified by `?sid=<student id>` (a one-field sign-in gate appears if it's missing). The scenario seed is derived deterministically from the student id, so the same student always gets the same baseline, limits, and first weeks.
- Progress autosaves after each meaningful step (baseline collected, each phase, every weekly submission, finishing). A refresh restores where they left off — the `?sid=` in the URL makes this automatic.
- On finish, a completion record (student, code, score) is written for the instructor roster.

Required secrets (environment variables or `.streamlit/secrets.toml`): `DB_ENCRYPTION_KEY`, plus either `DROPBOX_REFRESH_TOKEN` + `DROPBOX_APP_KEY` + `DROPBOX_APP_SECRET`, or `DROPBOX_ACCESS_TOKEN`. Optional: `PROGRESS_ROOT`, `GAMES_ROOT`. With storage enabled you must install the `dropbox` and `cryptography` packages (already in `requirements.txt`).

## Grading with the LMS completion code

When a student finishes, the Results page generates a code like `SQZ-12-0128-4913A0` encoding their **weeks played** and **score**, plus a checksum tied to their name and a secret salt.

Verify submissions with the included tool:

```bash
# one submission
python verify_code.py "Ada Lovelace" SQZ-12-0128-4913A0

# a whole class from a CSV with 'name' and 'code' columns
python verify_code.py --csv submissions.csv --out results.csv

# interactive
python verify_code.py
```

The verifier recomputes the checksum and reports **valid / invalid**, echoing the weeks and score. It rejects altered scores, wrong names, and forged codes.

> **Set your own secret.** Before distributing, change `COMPLETION_SALT` near the top of `juicetification.py` to your own string, and set the matching `SALT` in `verify_code.py` (or pass `--salt "your-secret"`). The salt ships in the source, so this is honor‑system‑plus, not server‑backed security — good enough to stop casual score‑editing.

## Configuration

The simplest way to configure the app is via the **Director** URL parameters above (no code changes). Every knob is also a plain default near the top of `juicetification.py` if you'd rather hard-code one:

| Parameter | Meaning | Default |
|----------|---------|---------|
| `target_fill_ml` | target fill volume (mL) | `300` |
| `within_sigma` | filler standard deviation (mL) | `2.0` |
| `spec_low` / `spec_high` | engineering spec (mL) | `294` / `306` |
| `subgroup_n` | fill subgroup size *n* | `5` |
| `n_baseline` | baseline subgroups collected | `24` |
| `p_inspect` | bottles inspected per shift | `200` |
| `randomize_sampling` | draw *n* & *nₚ* per student (overrides the two above) | `false` |
| `p_baseline_rate` | in‑control fraction defective | `0.04` |
| `cost_recall` / `cost_linestop` | $ per missed signal / false alarm | `12000` / `3500` |
| `trend_len` | points in a row that make a trend | `5` |
| `completion_salt` | secret for the completion code | *change me* |

## Files

```
juicetification-squeeze-control/
├── juicetification.py     # the Streamlit app (run this)
├── juice_director.py      # shared config loader (unchanged across apps)
├── manifest.py            # this app's configurable-parameter schema
├── student_store.py       # optional per-student progress persistence
├── verify_code.py         # instructor grading tool
├── requirements.txt       # Python dependencies
├── instructions.pdf       # one-page visual quick-start (for students)
├── README.md              # this file
└── LICENSE                # MIT
```

## License

Released under the MIT License — see [`LICENSE`](LICENSE). Built with [Streamlit](https://streamlit.io), [Plotly](https://plotly.com/python/), and [NumPy](https://numpy.org).
