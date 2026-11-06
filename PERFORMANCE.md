# Performance optimization — Streamlit Community Cloud, 30–40 concurrent students

Branch `perf/community-cloud-optimization` · audited at commit `ed1720e` · tested on Streamlit 1.67.0, Python 3.13.

## A. Executive summary

This app is limited by **CPU, not memory**. Under simulated class load (one CPU core, students playing the full game at the same time), the original version kept the server CPU pegged from about 20 students upward. As a result, the weekly Act 3 chart animation, which takes about 3 seconds for a single student, stretched to **16 seconds at 20 students and 36 seconds at 40**. Act 2 answers also lagged, because every answer waited for its progress save to reach Dropbox.

There were four root causes:

1. **The weekly three-chart figure was rebuilt from scratch for each of 24 animation frames**, twice per week, for every student. This was the biggest single cost in the app's own code.
2. **Streamlit forced a full Python garbage collection after every page update** (`runner.postScriptGC`, on by default). Profiling showed this taking **about one-third of all server CPU**.
3. **Progress was saved to Dropbox synchronously**, and Act 2 saves on every answer. Each answer therefore waited a full network round trip, even when nothing had changed.
4. **Redundant reruns and rebuilds.** Picking signals in Act 3 reran the whole page on every selection, and the Excel download was regenerated on every rerun, even inside a collapsed expander.

All four are fixed without removing any feature or changing what students see or download. At 40 students the median Act 3 animation dropped from **36.1 s to 6.0 s** and the median Act 2 answer from **0.82 s to 0.08 s**. At 20 students, Act 3 is back to near its single-student time (3.6 s, of which about 2.6 s is the intended animation delay).

**Bottom line:** 30–40 students is now workable. The app was stable with no errors at 40, but expect some sluggishness at peak (slowest 5% of Act 2 answers ≈ 2–3 s at 30–40 students on one core). The remaining limit is mainly Streamlit's own cost of sending each animation frame on a single Python process. That is a platform limit, covered in section F.

## B. Optimization results

All figures are **measured** with the local load test (`tools/loadtest/`), median / 95th percentile, 40 simulated students, unless noted. "Not measured" means no direct measurement exists.

| Component | Problem identified | Modification | Measured improvement |
|---|---|---|---|
| Application startup | Imports (~0.45 s) happen once per server process | None needed | No change (server ready in ~1 s locally; Community Cloud wake-from-sleep not measured) |
| Page loading | First render competes for CPU with everyone else's animations | Indirect, via the CPU savings below | 1.58 s → 1.02 s median (p95 ≈ 4.1 → 4.6 s, noisy) |
| Session management | Dropbox upload blocked every Act 2 answer; identical snapshots re-uploaded | Background write-behind queue (`write_behind.py`); skip unchanged snapshots | Act 2 answer 816 ms → 80 ms median; 4.6 s → 3.1 s p95. Dropbox uploads 1,000 → 725 per run |
| CPU utilization | Forced full garbage collection after every script run (~33% of CPU) | `.streamlit/config.toml`: `runner.postScriptGC = false` | Server CPU-saturated time 92% → 70% (40 students); 77% → 21% (20 students) |
| CPU utilization | Week figure rebuilt per animation frame (~25 ms × 48 frames per week) | Build once, update only the 3 data traces per frame | Act 3 animation 36.1 s → 6.0 s median; 41.1 s → 8.0 s p95 |
| Memory consumption | No problem found (no leak; flat across the run) | Verified that turning off forced GC does not grow memory | Peak RSS 280 MB → 242 MB |
| File uploads | **The app has no file uploads** | N/A | N/A |
| File downloads | Excel rebuilt by openpyxl on every rerun; each download click reran the whole page | Content-keyed `st.cache_data` for CSV/Excel bytes; `on_click="ignore"` | Download fetch 67 → 25 ms median; build cost removed from every Act 2/3 rerun (≈4 ms each) |
| Caching | No caching in the app | `st.cache_data` (exports, bounded and content-keyed), `st.cache_resource` (save queue), per-session cache of the finished week figure | Included in the rows above |
| Concurrent users | Act 3 multiselects reran the page on every pick | `st.form`: picks only submit with the button | 240 page reruns removed per 40-student run; 0 errors at every level tested |

### Full before/after (median / p95, milliseconds)

| Students | Act 2 answer | Act 3 week animation\* | Act 1 animation\* | Funnel auto-run\* | Server CPU ≥90% busy |
|---|---|---|---|---|---|
| 1 | 362/402 → **21/134** | 3,786 → **2,832** | 3,264 → 3,049 | 1,305 → 1,259 | 0% → 0% |
| 10 | 375/742 → **27/143** | 7,824 → **3,116** | 3,631 → 3,124 | 1,681 → 1,496 | 35% → 1% |
| 20 | 402/2,094 → **29/1,233** | 15,780 → **3,562** | 4,654 → 3,742 | 2,869 → 1,988 | 77% → 21% |
| 30 | 491/3,342 → **48/1,942** | 25,974 → **4,632** | 5,804 → 4,681 | 4,970 → 2,970 | 88% → 57% |
| 40 | 816/4,615 → **80/3,073** | 36,063 → **6,020** | 7,330 → 5,902 | 6,640 → 3,658 | 92% → 70% |

\* Animations include their intentional delay at "Normal" speed (week chart: 24 × 0.11 s ≈ 2.6 s; funnel: 10 × 0.11 s ≈ 1.1 s), so ~2.6 s is the best possible week-chart time.

## C. Code modifications

| File | Change |
|---|---|
| `juicetification.py` | Week figure split into a static scaffold built once (`_week_base_figure`) plus a per-frame trace update (`_set_week_frame`). The finished week figure is cached per session (`static_week_figure`). Autosave goes through a de-duplicating background queue; `save_now()` stays synchronous for the "Save progress" button; restart cancels queued saves first; resume waits for this student's queued save. CSV/Excel bytes are cached (`_export_bytes`) and downloads no longer rerun the page. Act 3 diagnosis is wrapped in `st.form`, with matching button CSS. All `use_container_width=True` → `width="stretch"`. |
| `write_behind.py` (new) | Thread pool that uploads the latest snapshot per student, in order, never two at once for the same student, with `cancel`/`flush` and failure tracking for retry. |
| `.streamlit/config.toml` (new) | `runner.postScriptGC = false`, `browser.gatherUsageStats = false`. |
| `requirements.txt` | `streamlit>=1.63` (was `>=1.39`). |
| `tests/` (new) | 24 regression tests (see D). |
| `tools/loadtest/` (new) | WebSocket-level load tester + simulated Dropbox (see its README). |

`student_store.py`, `juice_director.py` and `manifest.py` are **unchanged**, so the store stays identical to the Director's copy as its header requires.

**Compatibility.**
- `use_container_width` was deprecated with a 2025-12-31 removal date. Because `requirements.txt` didn't pin Streamlit, Community Cloud could have installed a version without it on the next redeploy and broken the app. This branch removes that risk.
- The full game test passes on Streamlit 1.63 and all 24 tests pass on 1.67. Streamlit 1.46 fails (missing `width="stretch"` support).
- On 1.50 and 1.58 the headless test harness doesn't register radio answers, so those versions are untested rather than known broken.

**Behavior differences** (intentional and small):
- An autosave now lands in Dropbox a fraction of a second *after* the page responds, instead of before. A student who refreshes is still guaranteed their latest state, because resume waits for their queued save. The only exposure is a server crash within that fraction of a second.
- Clicking a download no longer reloads the page.
- Act 3 signal picks are applied when "Submit analysis" is clicked, which was already the only time they were used.

## D. Testing results

- **Regression tests (`pytest tests`): 24 passed.**
  - Every animation frame and every static week chart is **byte-identical** (Plotly JSON) to the original code, including a zero-defect edge case.
  - CSV downloads are byte-identical and Excel workbooks have identical content.
  - The export cache is keyed by content, so one student can't get another's data.
  - The write-behind queue keeps per-student order, latest-wins, cancel-then-reset and error survival.
  - Headless play-throughs cover the full game (Act 1 → Results with a verified completion code), seeded reproducibility, save → resume in a new session, restart clearing stored progress, no re-upload of unchanged state, and two students' data staying separate.
- **Load test:** 1, 5, 10, 20, 30 and 40 simulated students each completed the whole game (3 Act 3 weeks each, with Excel downloads). **0 errors and 0 failed sessions at every level, before and after.**
- **Maximum concurrency tested:** 40 students on 1 CPU core. Peak memory ≈ 242 MB after (280 MB before).
- **Method and assumptions:**
  - Local server pinned to one core.
  - Real Streamlit WebSocket sessions, not plain HTTP requests.
  - Dropbox replaced by a stand-in with an **assumed 300 ms per call**; real Dropbox latency was not measured.
  - Think time between actions was 0.5–1.5 s, which is faster than real students. Treat the 40-student numbers as a stress case.
  - The production deployment was **not** load-tested.

## E. GitHub

Branch `perf/community-cloud-optimization`; pull request opened against `main`, **not merged**.

## F. Remaining constraints

**A. Code inefficiencies (fixed above).** Remaining smaller items:
- The Act 1 and funnel animations still rebuild small figures per frame (~2–10 ms each). Low priority.
- `new_us_round` re-samples until the week's chart signal is clean (median 6 ms, rare worst case ~0.1 s). Low priority.

**B. Configuration.**
- `runner.postScriptGC = false` is applied. If memory ever creeps up in "Manage app", set it back to `true`.
- Optional: pin an exact Streamlit version (Streamlit's own recommendation) so Community Cloud doesn't auto-upgrade under you. This was left as a floor (`>=1.63`) so you keep bug fixes.
- Optional: lowering the default simulation speed has the largest remaining effect on server load, because every animation frame costs server CPU. "Fast" sends the same frames in less wall time; "Instant" sends one frame. Not changed, because it alters the student experience.

**C. Platform limits (cannot be fixed in code).**
- Streamlit documents Community Cloud limits as approximately **0.078–2 CPU cores and 690 MB–2.7 GB memory (as of February 2024; "may change at any time without notice")**. The actual allocation for this app is **unknown**.
- All students share one Python process. Streamlit sends every animation frame from the server, so CPU work per frame can't be spread across cores.
- Apps sleep after 12 hours without traffic, so the first student to open a sleeping app waits for it to wake. Opening it a few minutes before class avoids that.
- Streamlit offers a resource boost request for educational use; that is the cheapest way to get more headroom without changing hosting.

**Is 30–40 realistic?** Yes, with caveats. Measured on one core, 30–40 simultaneous students complete the game with no errors. Typical interactions are fast, but the slowest few percent take 2–3 s at peak. Real classes rarely have every student animating at the same moment, so real load should be lighter than this test.
