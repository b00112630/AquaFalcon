"""
charts.py - charts that pop up inside the chat bubble.

Ask "show me a graph", "chart the results" or "show me your test results" and the answer gets a chart drawn
straight from test_results in rocket_info.yaml (so it updates by itself when you put in your real launches):
  * Distance per test   * Distance vs pressure   * Distance vs water
What-if answers get the matching chart with the estimate marked on it.
Colours match the app (deep navy accent, soft greys) and the charts stretch to the bubble width on phones.
"""
import re

import altair as alt
import pandas as pd

from knowledge import load_facts

NAVY, SKY, GREY, INK, MUTED, LINE = "#1e3a8a", "#0ea5e9", "#94a3b8", "#0f172a", "#64748b", "#e5e7eb"
AR = re.compile(r"[\u0600-\u06FF]")

CHART_WORDS = re.compile(r"\b(graphs?|charts?|plots?|visuali[sz]e|visual|curve)\b|رسم\s*بياني|رسمة|رسم|مخطط|جراف|غراف|منحنى", re.I)
RESULT_WORDS = re.compile(
    r"test\s*results?|\bresults?\b|flight\s*log|test\s*data|\b(your|the|all)\s+tests\b|test\s*launches|"
    r"how\s+did\s+(the|your)\s+(tests?|launches)\s+go|نتائج|نتايج|نتيجة|تجاربكم|التجارب", re.I)
PRESSURE_WORDS = re.compile(r"pressure|psi|ضغط", re.I)
WATER_WORDS = re.compile(r"water|\bml\b|ماء|مي\b|مية|موية", re.I)
TABS = {"tests": ("Per test", "كل تجربة"), "pressure": ("vs pressure", "مع الضغط"), "water": ("vs water", "مع الماء")}


def wants_chart(question: str) -> str | None:
    """'explicit' (asked for a graph), 'results' (asked about test results) or None."""
    q = question or ""
    if CHART_WORDS.search(q) and (RESULT_WORDS.search(q) or PRESSURE_WORDS.search(q) or WATER_WORDS.search(q)
                                  or re.search(r"distance|flight|launch|test|data|مسافة|تجارب|تجربة|بيانات", q, re.I)
                                  or len(q.split()) <= 6):
        return "explicit"
    if RESULT_WORDS.search(q):
        return "results"
    return None


def first_tab(question: str) -> str:
    q = question or ""
    if PRESSURE_WORDS.search(q) and not WATER_WORDS.search(q):
        return "pressure"
    if WATER_WORDS.search(q) and not PRESSURE_WORDS.search(q):
        return "water"
    return "tests"


def spec_for(question: str) -> dict | None:
    """What to draw for this question (stored with the message), or None."""
    if not wants_chart(question):
        return None
    return {"first": first_tab(question), "ar": bool(AR.search(question))}


def _rows():
    rows = [r for r in (load_facts().get("test_results") or [])
            if isinstance(r.get("distance_m"), (int, float))]
    return pd.DataFrame(rows)


def _style(ch, height=230):
    return (ch.properties(height=height, width="container")
            .configure(background="transparent", font="Inter")
            .configure_view(stroke=None)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=LINE, domainColor=LINE, tickColor=LINE,
                            labelFontSize=11, titleFontSize=11.5, titleFontWeight=500)
            .configure_legend(labelColor=MUTED, titleColor=MUTED, orient="bottom", labelFontSize=11, titleFontSize=11))


def per_test(df, ar=False):
    best = df["distance_m"].max()
    df = df.assign(label=df["test"].map(lambda t: f"#{t}"), best=df["distance_m"] == best,
                   txt=df["distance_m"].map(lambda d: f"{d:g} m"))
    x = alt.X("label:N", sort=None, title="التجربة" if ar else "Test", axis=alt.Axis(labelAngle=0))
    y = alt.Y("distance_m:Q", title="المسافة (م)" if ar else "Distance (m)")
    tip = [alt.Tooltip("test:N", title="Test"), alt.Tooltip("water_ml:Q", title="Water (mL)"),
           alt.Tooltip("pressure_psi:Q", title="Pressure (psi)"), alt.Tooltip("angle_deg:Q", title="Angle (°)"),
           alt.Tooltip("distance_m:Q", title="Distance (m)")]
    bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=x, y=y, tooltip=tip,
        color=alt.condition("datum.best", alt.value(SKY), alt.value(NAVY)))
    text = alt.Chart(df).mark_text(dy=-7, fontSize=11, fontWeight=600, color=INK).encode(x=x, y=y, text="txt:N")
    return _style(bars + text)


def _model_line(kind):
    try:
        from whatif import Model
        m = Model()
    except Exception:
        return None, None
    if kind == "pressure":
        lo, hi = m.p_range
        xs = [lo + (hi - lo) * i / 20 for i in range(21)]
        return m, pd.DataFrame({"x": xs, "y": [m.predict(p=x) for x in xs]})
    lo, hi = m.w_range
    xs = [lo + (hi - lo) * i / 30 for i in range(31)]
    return m, pd.DataFrame({"x": xs, "y": [m.predict(w=x) for x in xs]})


def versus(df, kind, ar=False, point=None):
    """Distance vs pressure (coloured by water) or vs water (coloured by pressure), with our fitted trend dashed
    and an optional what-if estimate marked."""
    xcol, other = ("pressure_psi", "water_ml") if kind == "pressure" else ("water_ml", "pressure_psi")
    xt = ("الضغط (psi)" if ar else "Pressure (psi)") if kind == "pressure" else ("الماء (مل)" if ar else "Water (mL)")
    ot = ("الماء (مل)" if ar else "Water (mL)") if kind == "pressure" else ("الضغط (psi)" if ar else "Pressure (psi)")
    yt = "المسافة (م)" if ar else "Distance (m)"
    lo = min(df[xcol].min(), point["x"] if point else df[xcol].min())
    hi = max(df[xcol].max(), point["x"] if point else df[xcol].max())
    pad = (hi - lo) * 0.12 or 10
    xs = alt.Scale(domain=[max(0, lo - pad), hi + pad], nice=False)
    ymax = max(df["distance_m"].max(), point["y"] if point else 0) * 1.18
    ys = alt.Scale(domain=[0, ymax], nice=False)
    pts = alt.Chart(df).mark_circle(size=110, opacity=.9, stroke="#fff", strokeWidth=1.5).encode(
        x=alt.X(f"{xcol}:Q", title=xt, scale=xs, axis=alt.Axis(tickCount=6)), y=alt.Y("distance_m:Q", title=yt, scale=ys),
        color=alt.Color(f"{other}:O", title=ot, scale=alt.Scale(range=[GREY, NAVY, SKY, "#1e40af", "#60a5fa"])),
        tooltip=[alt.Tooltip("test:N", title="Test"), alt.Tooltip(f"{xcol}:Q", title=xt),
                 alt.Tooltip(f"{other}:Q", title=ot), alt.Tooltip("distance_m:Q", title="Distance (m)")])
    layers = [pts]
    _, line = _model_line(kind)
    if line is not None and len(line):
        layers.insert(0, alt.Chart(line).mark_line(strokeDash=[5, 4], color=GREY, strokeWidth=2).encode(
            x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys)))
    m, _ = _model_line(kind)
    if point and m is not None:        # carry the trend on (dotted) from the tested range to the estimate
        lo_r, hi_r = m.p_range if kind == "pressure" else m.w_range
        edge = hi_r if point["x"] > hi_r else lo_r if point["x"] < lo_r else None
        if edge is not None:
            ey = m.predict(p=edge) if kind == "pressure" else m.predict(w=edge)
            ext = pd.DataFrame({"x": [edge, point["x"]], "y": [ey, point["y"]]})
            layers.insert(1, alt.Chart(ext).mark_line(strokeDash=[2, 3], color="#f59e0b", strokeWidth=2).encode(
                x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys)))
    if point:
        pd_pt = pd.DataFrame([{"x": point["x"], "y": point["y"],
                               "t": (f"تقدير {point['y']:g} م" if ar else f"estimate {point['y']:g} m")}])
        layers.append(alt.Chart(pd_pt).mark_point(shape="diamond", size=170, filled=True, color="#f59e0b",
                                                 stroke="#fff", strokeWidth=1.5).encode(
            x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys)))
        layers.append(alt.Chart(pd_pt).mark_text(dy=-14, fontSize=11, fontWeight=600, color="#b45309").encode(
            x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys), text="t:N"))
    return _style(alt.layer(*layers))


def build(kind, ar=False, point=None):
    df = _rows()
    if df.empty:
        return None
    if kind == "tests":
        return per_test(df, ar)
    return versus(df, kind, ar, point)


def render(spec: dict, key: str):
    """Draw the chart(s) for a stored spec inside the current bubble (Streamlit)."""
    import streamlit as st
    ar = bool(spec.get("ar"))
    alt_text = "Chart of our test launches from rocket_info.yaml"
    try:
        with st.container(key=f"chart{key}"):
            if spec.get("point"):          # what-if: one chart with the estimate marked
                ch = build(spec["first"], ar, spec["point"])
                if ch is not None:
                    st.altair_chart(ch, width="stretch", theme=None, key=f"c{key}")
                return
            order = [spec.get("first", "tests")] + [k for k in TABS if k != spec.get("first", "tests")]
            names = [TABS[k][1 if ar else 0] for k in order]
            for k, tab in zip(order, st.tabs(names, key=f"t{key}")):
                with tab:
                    ch = build(k, ar)
                    if ch is not None:
                        st.altair_chart(ch, width="stretch", theme=None, key=f"c{key}{k}")
            st.caption(("📈 من سجل تجاربنا · الخط المتقطع = الاتجاه المحسوب" if ar else
                        "📈 From our test log · dashed line = fitted trend"))
    except Exception as e:   # a chart must never break the chat
        print("[charts] could not draw:", e, flush=True)


def explicit_text(question: str, voice: bool = False) -> str:
    """Short deterministic caption for 'show me a graph' (no AI call - every number is from the YAML)."""
    f = load_facts()
    rows = [r for r in (f.get("test_results") or []) if isinstance(r.get("distance_m"), (int, float))]
    ar = bool(AR.search(question or ""))
    if not rows:
        return ("ما عنا نتائج تجارب مسجلة لسا." if ar else "We haven't recorded any test launches yet, so there's nothing to chart.")
    best = max(rows, key=lambda r: r["distance_m"])
    n = len(rows)
    if voice:
        return (f"هاي {n} تجارب إطلاق، وأحسن وحدة كانت {best['distance_m']:g} متر. حطيتلك رسم بياني بالمحادثة."
                if ar else f"Here are my {n} test launches; the best was {best['distance_m']:g} metres. "
                           f"I put a chart in the chat.")
    if ar:
        return (f"📊 هاي نتائج تجاربي ({n} إطلاقات). أحسن وحدة: **{best['distance_m']:g} م** "
                f"(تجربة {best.get('test')}: {best['water_ml']:g} مل، {best['pressure_psi']:g} psi، {best['angle_deg']:g}°).")
    return (f"📊 Here are my {n} test launches. Best flight: **{best['distance_m']:g} m** "
            f"(test {best.get('test')}: {best['water_ml']:g} mL, {best['pressure_psi']:g} psi, {best['angle_deg']:g}°).")
