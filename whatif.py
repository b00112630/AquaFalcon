"""
whatif.py - the "what if" calculator.

Ask "what if we used 70 psi?", "what if 400 mL of water?" or "what about 30 degrees?" and the bot answers
with a prediction COMPUTED HERE in Python from the test_results rows in rocket_info.yaml - the AI never
invents these numbers. Replace the YAML rows with your real launches and every estimate updates by itself.

The model (simple on purpose, so you can explain it in the presentation):
  * Pressure: a straight-line fit of distance vs pressure, using the launches at our usual water and angle.
  * Water:    every launch is first scaled to our usual pressure (with the line above), then a curve
              (parabola) is fitted through distance vs water. Its peak is the best amount of water.
  * Angle:    projectile physics - range is proportional to sin(2 x angle) - scaled to our measured
              distance at the angle we tested.
  * Anything outside the values we actually tested is flagged as a rough guess.
"""
import re

from knowledge import load_facts, measurements

AR = re.compile(r"[\u0600-\u06FF]")
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")

# words that make a question a "what if" (English + Arabic, typo-tolerant-ish)
TRIGGER = re.compile(
    r"what\s*if|wh?at\s+about|what\s+happens?\s+(if|at|with)|how\s+about|suppose|imagine|predict|"
    r"\bestimate\b|\bif\s+(we|you|i|u)\b|\bwould\b|\bcould\b|"
    r"\bhow\s+far\b.*\b(at|with)\b|"
    r"ماذا\s*لو|شو\s*لو|وش\s*لو|شو\s*بصير|ايش\s*بصير|إيش\s*بصير|لو\s|افرض|إفرض|نفرض|توقع|كم\s*بتطير|كم\s*رح",
    re.I)

# unit words -> parameter (English + Arabic)
P_UNITS = r"psi|بي\s*اس\s*اي|باي|bar|بار"
W_UNITS = r"m\s*l|ml|millilit(?:re|er)s?|mls|مل|ملل|مللي|ميلي|مليلتر|مل\s*لتر|l|lit(?:re|er)s?|لتر"
A_UNITS = r"°|degrees?|degs?|deg|درجة|درجات|درجه"
NUM = r"(\d+(?:\.\d+)?)"
KEYWORDS = {"pressure": r"pressure|psi|pump|ضغط", "water": r"water|ماء|مي|مية|موية|ميه",
            "angle": r"angle|tilt|زاوية|زاويه"}


def _num(q):
    return q.translate(AR_DIGITS)


def parse(question: str) -> dict:
    """{'pressure': psi, 'water': mL, 'angle': degrees} for every value named in the question."""
    q = _num(question)
    out = {}
    for n, u in re.findall(rf"{NUM}\s*({P_UNITS})(?![a-z])", q, re.I):
        out["pressure"] = float(n) * (14.5038 if u.lower() in ("bar", "بار") else 1)
    for n, u in re.findall(rf"{NUM}\s*({W_UNITS})(?![a-z])", q, re.I):
        lit = re.fullmatch(r"l|lit(?:re|er)s?|لتر", u.strip(), re.I)
        out["water"] = float(n) * (1000 if lit else 1)
    for n, _ in re.findall(rf"{NUM}\s*({A_UNITS})", q, re.I):
        out["angle"] = float(n)
    # a bare number next to a keyword: "what if the pressure was 70", "angle of 30", "water 400"
    for key, kw in KEYWORDS.items():
        if key in out:
            continue
        m = re.search(rf"(?:{kw})\D{{0,25}}?{NUM}(?!\s*(?:{P_UNITS}|{W_UNITS}|{A_UNITS}|%))", q, re.I) or \
            re.search(rf"{NUM}\s*(?:of\s+)?(?:{kw})", q, re.I)
        if m:
            out[key] = float(m.group(1))
    if "water" in out and out["water"] < 5 and re.search(r"\d\s*(l|lit|لتر)", q, re.I) is None:
        out["water"] *= 1000   # "1.5 water" etc. - assume litres when tiny
    return out


SAFETY = re.compile(r"\bsafe|danger|burst|explod|blow\s*up|آمن|امان|أمان|خطر|ينفجر|تنفجر", re.I)


def is_whatif(question: str) -> bool:
    """A what-if with at least one value we can compute (safety questions go to the normal brain)."""
    return bool(question and TRIGGER.search(_num(question)) and not SAFETY.search(question) and parse(question))


# ------------------------------------------------------------------ the model (all from the YAML)
def _mode(values):
    values = [v for v in values if v is not None]
    return max(set(values), key=lambda v: (values.count(v), v)) if values else None


def _lstsq_line(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def _parabola(xs, ys):
    """Least-squares y = a x^2 + b x + c (3x3 normal equations, no numpy needed)."""
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum(y * x ** k for x, y in zip(xs, ys)) for k in range(3)]
    m = [[s[4], s[3], s[2], t[2]], [s[3], s[2], s[1], t[1]], [s[2], s[1], s[0], t[0]]]
    for i in range(3):                               # Gauss-Jordan
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            return None
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [a - f * b for a, b in zip(m[r], m[i])]
    return tuple(m[i][3] / m[i][i] for i in range(3))


def _sin2(deg):
    import math
    return max(0.0, math.sin(math.radians(2 * deg)))


class Model:
    def __init__(self, facts=None):
        f = facts or load_facts()
        rows = [r for r in (f.get("test_results") or [])
                if all(isinstance(r.get(k), (int, float)) for k in ("water_ml", "pressure_psi", "angle_deg", "distance_m"))]
        if not rows:
            raise ValueError("no test rows")
        L = f.get("launch") or {}
        self.rows = rows
        num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        self.ref_w = num(L.get("water_volume_ml")) or _mode([r["water_ml"] for r in rows])
        self.ref_p = num(L.get("launch_pressure_psi")) or _mode([r["pressure_psi"] for r in rows])
        self.ref_a = num(L.get("launch_angle_deg")) or _mode([r["angle_deg"] for r in rows])
        bottle = measurements(str((f.get("design") or {}).get("bottle", "")))
        vols = [v for _, _, k, v in bottle if k == "volume"]
        self.bottle_ml = vols[0] if vols else None

        # 1) pressure line, from launches at our usual angle (and usual water if there are 2+ pressures there)
        at_a = [r for r in rows if r["angle_deg"] == self.ref_a] or rows
        at_wa = [r for r in at_a if r["water_ml"] == self.ref_w]
        base = at_wa if len({r["pressure_psi"] for r in at_wa}) >= 2 else at_a
        ps = [r["pressure_psi"] for r in base]
        self.p_range = (min(ps), max(ps))
        self.p_rows = base
        if len(set(ps)) >= 2:
            self.slope, self.icpt = _lstsq_line(ps, [r["distance_m"] for r in base])
            self.p_kind = "line"
        else:                                         # one pressure only: distance proportional to pressure
            self.slope, self.icpt = sum(r["distance_m"] for r in base) / sum(ps), 0.0
            self.p_kind = "proportional"
        if self.slope <= 0:                           # data says nothing sensible: fall back to physics
            self.slope, self.icpt, self.p_kind = sum(r["distance_m"] for r in base) / sum(ps), 0.0, "proportional"

        # 2) water curve: scale every launch (at our angle) to our usual pressure, then fit
        pts = {}
        for r in at_a:
            fp = self.f_p(r["pressure_psi"])
            if fp > 0:
                pts.setdefault(r["water_ml"], []).append(r["distance_m"] * self.f_p(self.ref_p) / fp)
        self.w_pts = sorted((w, sum(v) / len(v)) for w, v in pts.items())
        ws = [w for w, _ in self.w_pts]
        self.w_range = (min(ws), max(ws))
        self.w_fit = None
        if len(ws) >= 3:
            fit = _parabola(ws, [d for _, d in self.w_pts])
            if fit and fit[0] < 0:
                self.w_fit = fit
        if self.w_fit:
            a, b, _ = self.w_fit
            self.w_best = -b / (2 * a)
        else:
            self.w_best = max(self.w_pts, key=lambda t: t[1])[0]

        # 3) the measured distance at our usual settings (average of repeats), for the angle scaling
        same = [r["distance_m"] for r in rows if (r["water_ml"], r["pressure_psi"], r["angle_deg"]) ==
                (self.ref_w, self.ref_p, self.ref_a)]
        self.base_d = sum(same) / len(same) if same else self.predict_raw(self.ref_p, self.ref_w)
        self.a_tested = sorted({r["angle_deg"] for r in rows})

    def f_p(self, p):
        return max(0.0, self.slope * p + self.icpt)

    def g_w(self, w):
        if w <= 0:
            return 0.0
        pts = self.w_pts
        if len(pts) == 1:
            return pts[0][1]
        if w < pts[0][0] or w > pts[-1][0]:   # outside what we tested: carry on in a straight line from the edge
            (x0, y0), (x1, y1) = (pts[0], pts[1]) if w < pts[0][0] else (pts[-2], pts[-1])
            edge = (x0, y0) if w < pts[0][0] else (x1, y1)
            ey = self.g_w(edge[0])
            return max(0.0, ey + (y1 - y0) / (x1 - x0) * (w - edge[0])) if x1 != x0 else ey
        if self.w_fit:
            a, b, c = self.w_fit
            return max(0.0, a * w * w + b * w + c)
        i = max(k for k in range(len(pts)) if pts[k][0] <= w)
        (x0, y0), (x1, y1) = pts[i], pts[min(i + 1, len(pts) - 1)]
        if x1 == x0:
            return y0
        return max(0.0, y0 + (y1 - y0) * (w - x0) / (x1 - x0))

    def predict_raw(self, p, w):
        ref = self.g_w(self.ref_w) or 1.0
        return self.f_p(p) * self.g_w(w) / ref

    def predict(self, p=None, w=None, a=None) -> float:
        p = self.ref_p if p is None else p
        w = self.ref_w if w is None else w
        a = self.ref_a if a is None else a
        if (p, w) == (self.ref_p, self.ref_w):
            d = self.base_d
        else:
            d = self.predict_raw(p, w) * (self.base_d / (self.predict_raw(self.ref_p, self.ref_w) or self.base_d))
        s_ref = _sin2(self.ref_a) or 1.0
        return max(0.0, d * _sin2(a) / s_ref)


# ------------------------------------------------------------------ answer text
def _fmt(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _r(x, rough):
    """Round a prediction: 1 decimal inside the tested range, whole metres for a rough guess."""
    return _fmt(round(x)) if rough else _fmt(round(x, 1))


def _chart(p, w, a, dist):
    """One knob changed (pressure or water): show the estimate on the matching chart."""
    if (p is not None) != (w is not None) and a is None:
        return {"first": "pressure" if p is not None else "water",
                "point": {"x": p if p is not None else w, "y": float(dist)}}
    return None


def answer(question: str, voice: bool = False, facts=None) -> dict | None:
    """The calculator's reply, or None if this isn't a what-if we can compute.
    Returns {'text': ..., 'numbers': [(kind, value), ...]} - numbers are whitelisted for the fact-checker."""
    if not is_whatif(question):
        return None
    try:
        m = Model(facts)
    except Exception:
        return None
    asked = parse(question)
    ar = bool(AR.search(question))
    p, w, a = asked.get("pressure"), asked.get("water"), asked.get("angle")
    P, W, A = (m.ref_p if p is None else p), (m.ref_w if w is None else w), (m.ref_a if a is None else a)
    numbers = [("pressure", P), ("volume", W), ("angle", A)]

    # --- things we refuse to put a number on (safety / impossible)
    max_p = m.p_range[1]
    if p is not None and (p > 100 or p > 2 * max_p):
        txt = (f"⚠️ {_fmt(p)} psi هو كتير فوق اللي جربناه (لحد {_fmt(max_p)} psi)، وما قسنا حد انفجار القنينة، "
               f"فما رح أعطي رقم لهيك ضغط. السلامة أول! 🥽") if ar else (
               f"⚠️ {_fmt(p)} psi is way beyond anything we tested (max {_fmt(max_p)} psi), and we never measured "
               f"the bottle's burst limit, so I won't put a number on it. A PET bottle can burst - safety first! 🥽")
        if voice:
            txt = (f"{_fmt(p)} PSI كتير فوق اللي جربناه، وما قسنا حد انفجار القنينة، فما رح أخمّن. السلامة أول."
                   if ar else f"{_fmt(p)} PSI is way beyond what we tested, and we never measured the bottle's "
                              f"burst limit, so I won't guess. Safety first.")
        return {"text": txt, "numbers": numbers}
    if m.bottle_ml and w is not None and w >= m.bottle_ml:
        txt = (f"القنينة سعتها {_fmt(m.bottle_ml)} مل بس، فما في مكان لـ {_fmt(w)} مل ماء وهوا مضغوط 😅"
               if ar else f"My bottle only holds {_fmt(m.bottle_ml)} mL, so {_fmt(w)} mL of water leaves no room "
                          f"for the compressed air - I wouldn't fly at all 😅")
        return {"text": txt, "numbers": numbers + [("volume", m.bottle_ml)]}

    # --- did we actually test exactly this?
    exact = [r for r in m.rows if (r["pressure_psi"], r["water_ml"], r["angle_deg"]) == (P, W, A)]
    d = m.predict(P, W, A)
    out_p = p is not None and not (m.p_range[0] <= p <= m.p_range[1])
    out_w = w is not None and not (m.w_range[0] <= w <= m.w_range[1])
    out_a = a is not None and a not in m.a_tested
    rough = out_p or out_w or out_a
    dist = _r(d, rough)
    numbers.append(("length", float(dist)))
    setting = f"{_fmt(W)} mL water, {_fmt(P)} psi, {_fmt(A)}°"
    setting_ar = f"{_fmt(W)} مل ماء، {_fmt(P)} psi، زاوية {_fmt(A)}°"

    if exact:
        ds = [r["distance_m"] for r in exact]
        tests = ", ".join(str(r.get("test", "?")) for r in exact)
        numbers += [("length", float(x)) for x in ds]
        joined = " and ".join(f"{_fmt(x)} m" for x in ds)
        if voice:
            return {"numbers": numbers, "text": (
                f"جربنا هالإعدادات فعلاً، وطرت {' و '.join(_fmt(x) + ' متر' for x in ds)}." if ar else
                f"We actually tested that one: I flew {' and '.join(_fmt(x) + ' metres' for x in ds)}.")}
        return {"numbers": numbers, "text": (
            f"✅ هاي جربناها فعلاً ({setting_ar}): طرت **{' و '.join(_fmt(x) + ' م' for x in ds)}** (تجربة {tests}). "
            f"هذا قياس حقيقي، مش تقدير." if ar else
            f"✅ We actually tested that ({setting}): I flew **{joined}** (test {tests}). "
            f"That's a real measurement, not an estimate.")}

    # --- assumption line: name each effect that was asked about
    parts, parts_ar = [], []
    if p is not None or (w is None and a is None):
        how = "in a straight line" if m.p_kind == "line" else "in proportion"
        parts.append(f"distance grows {how} with pressure, fitted to our {_fmt(m.ref_w)} mL launches at "
                     f"{_fmt(m.p_range[0])}–{_fmt(m.p_range[1])} psi")
        parts_ar.append(f"المسافة بتزيد بخط مستقيم مع الضغط، حسب تجاربنا على {_fmt(m.ref_w)} مل بين "
                        f"{_fmt(m.p_range[0])} و{_fmt(m.p_range[1])} psi")
    if w is not None:
        pct = m.w_best / m.bottle_ml * 100 if m.bottle_ml else None
        third = pct is not None and 27 <= pct <= 40
        frac = (f" (~{pct:.0f}% of the bottle{', about a third' if third else ''})" if pct else "")
        frac_ar = (f" (حوالي {pct:.0f}% من القنينة{'، يعني تقريباً الثلث' if third else ''})" if pct else "")
        parts.append(f"a curve through our launches (scaled to {_fmt(m.ref_p)} psi) that peaks around "
                     f"{_fmt(round(m.w_best, -1))} mL{frac}")
        parts_ar.append(f"منحنى من تجاربنا (محسوبة على {_fmt(m.ref_p)} psi)، وأفضل كمية فيه حوالي "
                        f"{_fmt(round(m.w_best, -1))} مل{frac_ar}")
        numbers.append(("volume", round(m.w_best, -1)))
    if a is not None:
        parts.append(f"projectile physics (range ∝ sin 2θ) scaled from our {_fmt(round(m.base_d, 1))} m average at "
                     f"{_fmt(m.ref_a)}°, ignoring drag")
        parts_ar.append(f"فيزياء المقذوفات (المدى ∝ sin 2θ) محسوبة من معدل {_fmt(round(m.base_d, 1))} م عند "
                        f"{_fmt(m.ref_a)}°، بدون مقاومة الهوا")
        if a >= 80:
            parts.append("near straight up it comes back down close to the pad")
            parts_ar.append("قريب من العمودي بيرجع ينزل جنب منصة الإطلاق")
        elif a <= 10:
            parts.append("that flat it skims into the ground almost straight away")
            parts_ar.append("بهالزاوية المنخفضة بيضرب الأرض تقريباً فوراً")
    assume, assume_ar = "; ".join(parts), "؛ ".join(parts_ar)
    numbers.append(("length", round(m.base_d, 1)))

    flags, flags_ar = [], []
    if out_p:
        flags.append(f"{_fmt(p)} psi is outside what we tested ({_fmt(m.p_range[0])}–{_fmt(m.p_range[1])} psi)")
        flags_ar.append(f"{_fmt(p)} psi برا اللي جربناه ({_fmt(m.p_range[0])}–{_fmt(m.p_range[1])} psi)")
    if out_w:
        flags.append(f"{_fmt(w)} mL is outside what we tested ({_fmt(m.w_range[0])}–{_fmt(m.w_range[1])} mL)")
        flags_ar.append(f"{_fmt(w)} مل برا اللي جربناه ({_fmt(m.w_range[0])}–{_fmt(m.w_range[1])} مل)")
    if out_a:
        tested = "/".join(_fmt(x) + "°" for x in m.a_tested)
        flags.append(f"we only launched at {tested}")
        flags_ar.append(f"جربنا بس على {tested}")
    safety = p is not None and p > max_p

    if voice:   # short and natural, units in words
        if ar:
            s = f"تقديري من بيانات تجاربنا: حوالي {dist} متر."
            if rough:
                s += " بس هذا برا اللي جربناه، فهو تخمين تقريبي."
            if safety:
                s += " وما قسنا حد انفجار القنينة، فهذا مش اقتراح."
            return {"text": s, "numbers": numbers, "chart": _chart(p, w, a, dist)}
        what = (f"at {_fmt(p)} PSI" if p is not None and w is None and a is None else
                f"with {_fmt(w)} millilitres of water" if w is not None and p is None and a is None else
                f"at {_fmt(a)} degrees" if a is not None and p is None and w is None else "with those settings")
        s = f"From our test data, I'd estimate about {dist} metres {what}."
        if rough:
            s += " That's outside what we tested, so it's a rough guess."
        if safety:
            s += " We never measured the bottle's burst limit, so that's not a suggestion."
        return {"text": s, "numbers": numbers, "chart": _chart(p, w, a, dist)}

    chart = _chart(p, w, a, dist)
    if ar:
        txt = (f"🧮 **تقدير من بيانات تجاربنا:** حوالي **{dist} م** ({setting_ar}).\n\n"
               f"الافتراض: {assume_ar}.")
        if rough:
            txt += f"\n\n⚠️ {'، و'.join(flags_ar)}، فهذا تخمين تقريبي."
        if safety:
            txt += " وما قسنا حد انفجار القنينة، فهذا حساب على الورق مش اقتراح إنا نضخ لهالضغط."
        return {"text": txt, "numbers": numbers, "chart": chart}
    txt = (f"🧮 **Estimate from our test data:** {'basically' if float(dist) == 0 else 'about'} **{dist} m** ({setting}).\n\n"
           f"Assumption: {assume}.")
    if rough:
        txt += f"\n\n⚠️ {'; '.join(flags)}, so this is a rough guess."
    if safety:
        txt += " We never measured the bottle's burst limit, so it's a paper estimate, not a suggestion to pump that high."
    return {"text": txt, "numbers": numbers, "chart": chart}


if __name__ == "__main__":
    import sys
    for q in sys.argv[1:] or ["what if we used 70 psi?", "what if 400 mL water?", "what about 30 degrees?",
                               "what if we used 50 psi", "شو لو استخدمنا 70 psi؟"]:
        print(q, "->", (answer(q) or {}).get("text"), "\n")
