"""Frozen copy of the ORIGINAL (pre-optimization) week_figure, used only by the
equivalence tests to prove the optimized animation draws byte-identical charts.
Copied verbatim from juicetification.py @ ed1720e."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

GOOD_COLOR = "#ff7a00"
BAD_COLOR = "#2ecc71"
FLAG_COLOR = "#c0392b"
NAVY = "#2c3e50"


def week_figure_original(means, ranges, fracs, lim, plim, upto, flags=None, reveal=False):
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

    def zone(row, y0, y1):
        """Shaded amber warning band (between 2σ and the control limit)."""
        if y1 <= y0:
            return
        fig.add_trace(go.Scatter(x=[0, N + 1, N + 1, 0], y=[y0, y0, y1, y1],
                                 fill="toself", fillcolor="rgba(255,170,0,.13)",
                                 line=dict(width=0), mode="lines",
                                 hoverinfo="skip", showlegend=False), row=row, col=1)

    # X-bar (row 1) — 2σ warning zones, then limits + centerline as line traces
    _sxu = (lim["ucl_x"] - lim["xbarbar"]) / 3.0
    _sxd = (lim["xbarbar"] - lim["lcl_x"]) / 3.0
    zone(1, lim["xbarbar"] + 2 * _sxu, lim["ucl_x"])
    zone(1, lim["lcl_x"], lim["xbarbar"] - 2 * _sxd)
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
    zone(2, lim["rbar"] + 2 * (lim["ucl_r"] - lim["rbar"]) / 3.0, lim["ucl_r"])
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
    zone(3, plim["pbar"] + 2 * (plim["ucl"] - plim["pbar"]) / 3.0, plim["ucl"])
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

