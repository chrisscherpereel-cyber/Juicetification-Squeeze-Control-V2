"""The optimizations must not change anything a student sees or downloads."""
import io

import numpy as np
import pandas as pd
import plotly.io as pio
import pytest

import juicetification as J
from _reference_original import week_figure_original


def _week(seed, signal_plan=None):
    rng = np.random.default_rng(seed)
    sub, pc = J.clean_baseline(5, 200, rng)
    lim, plim = J.xbar_r_limits(sub), J.p_chart_limits(pc, 200)
    wsub = J.make_subgroups(24, n=5, rng=rng)
    if signal_plan:
        wsub = J.inject_xbar(wsub, signal_plan, lim["xbarbar"], lim["sigma_xbar"], rng, n=5)
    wc = J.make_defects(24, 0.04, rng, n_inspect=200)
    means, ranges, fracs = wsub.mean(1), wsub.max(1) - wsub.min(1), wc / 200
    return means, ranges, fracs, lim, plim


def _json(fig):
    return pio.to_json(fig, validate=False)


@pytest.mark.parametrize("seed", [1, 7, 42, 1234])
@pytest.mark.parametrize("reveal", [False, True])
def test_week_figure_identical_to_original(seed, reveal):
    means, ranges, fracs, lim, plim = _week(seed, "beyond_limits")
    flags = {"x": {3, 10}, "r": {5}, "p": {0, 23}}
    for upto in (0, 1, 12, 24):
        assert _json(J.week_figure(means, ranges, fracs, lim, plim, upto, flags, reveal)) == \
               _json(week_figure_original(means, ranges, fracs, lim, plim, upto, flags, reveal))


@pytest.mark.parametrize("reveal", [False, True])
def test_animation_frames_identical_to_original(reveal):
    """animate_week now mutates ONE figure frame by frame; every frame must equal
    the figure the original code rebuilt from scratch for that frame."""
    means, ranges, fracs, lim, plim = _week(99, "trend")
    flags = {"x": {4, 5, 6, 7, 8}, "r": set(), "p": {20}}
    fig = J._week_base_figure(means, ranges, fracs, lim, plim)
    for i in range(1, len(means) + 1):
        fl = {c: {k for k in flags[c] if k < i} for c in flags} if reveal else flags
        J._set_week_frame(fig, means, ranges, fracs, plim, i, fl, reveal)
        assert _json(fig) == _json(week_figure_original(means, ranges, fracs, lim, plim, i, fl, reveal))


def test_zero_defect_baseline_still_matches():
    """p̄ = 0 (instructor sets defect rate 0) removes the p warning zone; the data
    traces are located by mode, not by a hard-coded index, so this must still work."""
    means, ranges, fracs, lim, _ = _week(3)
    plim = J.p_chart_limits(np.zeros(24, int), 200)
    fracs = np.zeros(24)
    assert _json(J.week_figure(means, ranges, fracs, lim, plim, 24, None, True)) == \
           _json(week_figure_original(means, ranges, fracs, lim, plim, 24, None, True))


def _export_original(df):
    csv = df.to_csv(index=False).encode("utf-8-sig")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df.to_excel(xl, index=False, sheet_name="Data")
    return csv, buf.getvalue()


def test_downloads_identical_content():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"Shift": range(1, 25),
                       **{f"Bottle_{b}_mL": np.round(rng.normal(300, 2, 24), 1) for b in range(1, 6)},
                       "Defects": rng.binomial(200, .04, 24), "Inspected": [200] * 24})
    csv_new, xlsx_new = J._export_bytes.__wrapped__(df)
    csv_old, xlsx_old = _export_original(df)
    assert csv_new == csv_old
    # xlsx bytes embed a creation timestamp, so compare the workbook contents.
    pd.testing.assert_frame_equal(pd.read_excel(io.BytesIO(xlsx_new)), pd.read_excel(io.BytesIO(xlsx_old)))
    assert pd.read_excel(io.BytesIO(xlsx_new), sheet_name=None).keys() == {"Data"}


def test_export_cache_is_content_keyed():
    """Two different students' tables can never share cached bytes."""
    a = pd.DataFrame({"x": [1.0, 2.0]})
    b = pd.DataFrame({"x": [1.0, 2.5]})
    assert J._export_bytes(a)[0] != J._export_bytes(b)[0]
    assert J._export_bytes(a)[0] == a.to_csv(index=False).encode("utf-8-sig")
