"""
launchlab.py - the physics behind the Launch Lab (the interactive flight simulator in the app).

The browser runs the SAME model in lab_component/physics.js (so sliders feel instant); this Python copy is
what the chatbot uses when you press "Ask AquaFalcon why" (it re-computes the flight itself, so the AI
only ever explains numbers we calculated), and what tests/test_launchlab.py checks.

The model (simple enough to explain in the presentation):
  1. WATER THRUST. The compressed air pushes water out of the nozzle.
       exhaust speed  u = sqrt(2 * (p_air - p_atm) / rho_water)        (Bernoulli)
       thrust         F = 2 * A_nozzle * (p_air - p_atm)                (= mass flow x u)
     As water leaves, the air expands and its pressure drops:  p * V^1.4 = constant   (adiabatic expansion)
  2. AIR BLAST. If air pressure is left when the water is gone, the air itself rushes out
     (compressible nozzle flow, choked while p > 1.89 x p_atm). Short, but it adds a kick.
  3. COAST. Only gravity and air drag:  D = 0.5 * rho_air * Cd * A * v^2.
     A rocket with fins turns into the wind (flies nose-first); with no fins it tumbles (much more drag).
  The rocket slides up a short launch rail first, so it leaves the pad at the launch angle.

It is an IDEAL model: no wobble, no wind, no leaks, perfect nozzle. Real launches fly shorter.
All starting values are the EXAMPLE numbers from rocket_info.yaml until the team adds real ones.
"""
import math

G = 9.81
RHO_W = 1000.0          # water, kg/m^3
RHO_AIR = 1.2           # outside air, kg/m^3
P_ATM = 101325.0        # Pa
GAMMA = 1.4             # air
R_AIR = 287.05          # J/(kg K)
T0 = 293.15             # 20 C
PSI = 6894.757
RAIL_M = 0.6            # launch rail / tube length
DT_THRUST = 1e-4
DT_COAST = 2e-3
T_MAX = 60.0

NOSE_CD = {"cone": 0.34, "ogive": 0.30, "flat": 0.55}
FIN_CD = {0: 0.0, 3: 0.04, 4: 0.06}
TUMBLE_CD = 1.1          # no fins: the rocket tumbles
TUMBLE_THRUST = 0.7      # ...and part of the push goes sideways
STABILITY_CAL = {0: -0.5, 3: 1.5, 4: 1.8}   # rough static margin in body diameters (calibres)

DEFAULTS = {"bottle_l": 1.5, "fill": 1 / 3, "psi": 60.0, "angle": 45.0, "dry_g": 115.0,
            "nose": "cone", "fins": 3, "nozzle_mm": 21.5}


def params_from_facts(facts: dict | None) -> dict:
    """Starting values for the sliders from rocket_info.yaml (EXAMPLE values until the team edits them)."""
    p = dict(DEFAULTS)
    facts = facts or {}
    d, L = facts.get("design") or {}, facts.get("launch") or {}

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*L\b", str(d.get("bottle", "")))
    if m and 0.3 <= float(m.group(1)) <= 3:
        p["bottle_l"] = float(m.group(1))
    if num(d.get("dry_mass_g")):
        p["dry_g"] = num(d["dry_mass_g"])
    if num(L.get("water_volume_ml")):
        p["fill"] = min(0.9, num(L["water_volume_ml"]) / (p["bottle_l"] * 1000))
    if num(L.get("launch_pressure_psi")) is not None:
        p["psi"] = num(L["launch_pressure_psi"])
    if num(L.get("launch_angle_deg")):
        p["angle"] = num(L["launch_angle_deg"])
    fins = re.search(r"\b([034])\b|\b(three|four)\b", str(d.get("fins", "")), re.I)
    if fins:
        p["fins"] = int(fins.group(1)) if fins.group(1) else {"three": 3, "four": 4}[fins.group(2).lower()]
    return p


def clean(params: dict | None) -> dict:
    """Clamp every input to a sane range (so a weird value can't break the maths)."""
    p = dict(DEFAULTS)
    p.update({k: v for k, v in (params or {}).items() if k in DEFAULTS and v is not None})
    p["bottle_l"] = min(3.0, max(0.3, float(p["bottle_l"])))
    p["fill"] = min(0.95, max(0.0, float(p["fill"])))
    p["psi"] = min(150.0, max(0.0, float(p["psi"])))
    p["angle"] = min(90.0, max(5.0, float(p["angle"])))
    p["dry_g"] = min(2000.0, max(20.0, float(p["dry_g"])))
    p["nozzle_mm"] = min(30.0, max(3.0, float(p["nozzle_mm"])))
    p["nose"] = p["nose"] if p["nose"] in NOSE_CD else "cone"
    p["fins"] = int(p["fins"]) if int(p["fins"]) in FIN_CD else 3
    return p


def body_diameter(bottle_l: float) -> float:
    """A 1.5 L bottle is about 9 cm wide; other sizes scale with the cube root of the volume."""
    return 0.09 * (bottle_l / 1.5) ** (1 / 3)


def simulate(params: dict | None = None, samples: bool = False) -> dict:
    p = clean(params)
    vb = p["bottle_l"] / 1000.0                          # m^3
    vw = vb * p["fill"]                                  # water volume, m^3
    va0 = vb - vw
    p0 = p["psi"] * PSI + P_ATM                           # absolute starting pressure
    an = math.pi * (p["nozzle_mm"] / 1000.0) ** 2 / 4
    ab = math.pi * body_diameter(p["bottle_l"]) ** 2 / 4
    m_dry = p["dry_g"] / 1000.0
    m_air = p0 * va0 / (R_AIR * T0) if va0 > 0 else 0.0
    stable = p["fins"] > 0
    cd = NOSE_CD[p["nose"]] + FIN_CD[p["fins"]]
    th = math.radians(p["angle"])
    ux, uy = math.cos(th), math.sin(th)

    x = y = vx = vy = t = 0.0
    s_rail = 0.0
    on_rail = True
    phase = "water" if vw > 0 else "air"
    p_air, t_air = p0, T0
    rho_end = None; p_end = None            # air state at the end of the water phase
    apogee, max_v, max_f, max_a = 0.0, 0.0, 0.0, 0.0
    t_water = t_air_end = None
    water_left = 0.0
    lifted = False
    pts = []
    next_sample = 0.0
    landed_x = None
    while t < T_MAX:
        # ---------- thrust force and mass flow
        f = 0.0
        if phase == "water":
            va = vb - vw
            p_air = p0 * (va0 / va) ** GAMMA if va0 > 0 else P_ATM
            dp = p_air - P_ATM
            if dp <= 0 or vw <= 0:
                water_left = max(vw, 0.0)
                t_water = t
                rho_end, p_end = m_air / vb, max(p_air, P_ATM)
                phase = "air" if dp > 0 and m_air > 0 else "coast"
                if phase == "air":
                    t_air = T0 * (va0 / max(va, 1e-12)) ** (GAMMA - 1)
                continue
            u = math.sqrt(2 * dp / RHO_W)
            q = an * u
            f = 2 * an * dp
            dt = DT_THRUST
            vw -= q * dt
            if vw < 0:
                vw = 0.0
        elif phase == "air":
            if rho_end is None:          # no water at all: the air blast starts straight away
                rho_end, p_end = m_air / vb, p0
            rho = m_air / vb
            p_air = p_end * (rho / rho_end) ** GAMMA if rho_end > 0 else P_ATM
            if p_air <= P_ATM * 1.001 or m_air <= 1e-7:
                phase = "coast"
                t_air_end = t
                continue
            t_air = p_air / (rho * R_AIR)
            if p_air / P_ATM > ((GAMMA + 1) / 2) ** (GAMMA / (GAMMA - 1)):      # choked
                mdot = an * p_air * math.sqrt(GAMMA / (R_AIR * t_air)) * \
                    (2 / (GAMMA + 1)) ** ((GAMMA + 1) / (2 * (GAMMA - 1)))
                te = t_air * 2 / (GAMMA + 1)
                pe = p_air * (2 / (GAMMA + 1)) ** (GAMMA / (GAMMA - 1))
                f = mdot * math.sqrt(GAMMA * R_AIR * te) + (pe - P_ATM) * an
            else:
                ve = math.sqrt(2 * GAMMA / (GAMMA - 1) * R_AIR * t_air *
                               (1 - (P_ATM / p_air) ** ((GAMMA - 1) / GAMMA)))
                mdot = rho * (P_ATM / p_air) ** (1 / GAMMA) * an * ve
                f = mdot * ve
            dt = DT_THRUST
            m_air = max(0.0, m_air - mdot * dt)
        else:
            dt = DT_COAST
        if not stable and not on_rail:
            f *= TUMBLE_THRUST
        m = m_dry + RHO_W * vw + m_air
        v = math.hypot(vx, vy)
        cd_now = cd if (stable or on_rail) else TUMBLE_CD
        drag = 0.5 * RHO_AIR * cd_now * ab * v * v
        max_f = max(max_f, f)
        if on_rail:
            a = (f - drag) / m - G * uy
            vr = vx * ux + vy * uy
            if vr <= 0 and a <= 0:
                a = 0.0
                if f <= 0 and phase == "coast":
                    break                       # never moved: no flight
            vr += a * dt
            vx, vy = vr * ux, vr * uy
            x += vx * dt
            y += vy * dt
            s_rail += vr * dt
            if s_rail >= RAIL_M:
                on_rail = False
            max_a = max(max_a, a)
        else:
            dx, dy = (vx / v, vy / v) if v > 1e-9 else (ux, uy)
            ax = (f - drag) / m * dx
            ay = (f - drag) / m * dy - G
            max_a = max(max_a, (f - drag) / m)
            vx += ax * dt
            vy += ay * dt
            nx, ny = x + vx * dt, y + vy * dt
            if ny < 0 and lifted:
                k = y / (y - ny) if y != ny else 1.0
                landed_x = x + (nx - x) * k
                t += dt * k
                x, y = landed_x, 0.0
                pts.append((round(t, 4), round(x, 3), 0.0, round(v, 3), round(f, 2), phase))
                break
            x, y = nx, ny
        if y > 0.05:
            lifted = True
        t += dt
        v = math.hypot(vx, vy)
        apogee = max(apogee, y)
        max_v = max(max_v, v)
        if samples and t >= next_sample:
            pts.append((round(t, 4), round(x, 3), round(y, 3), round(v, 3), round(f, 2), phase))
            next_sample = t + (0.002 if phase != "coast" else 0.02)
    flew = lifted and landed_x is not None
    return {
        "params": p,
        "flew": flew,
        "range_m": round(landed_x, 2) if flew else 0.0,
        "apogee_m": round(apogee, 2) if flew else 0.0,
        "flight_time_s": round(t, 2) if flew else 0.0,
        "max_speed_ms": round(max_v, 2),
        "peak_thrust_n": round(max_f, 1),
        "max_accel_g": round(max_a / G, 1),
        "water_thrust_s": round(t_water, 3) if t_water is not None else 0.0,
        "thrust_s": round(t_air_end if t_air_end is not None else (t_water or 0.0), 3),
        "water_left_ml": round(water_left * 1e6),
        "water_ml": round(vb * p["fill"] * 1e6),
        "stable": stable,
        "stability_cal": STABILITY_CAL[p["fins"]],
        "cd": round(cd if stable else TUMBLE_CD, 2),
        "samples": pts if samples else None,
    }


def score(result: dict, goal: str = "range") -> float:
    return result["apogee_m"] if goal == "height" else result["range_m"]


def sweep_fill(params: dict | None = None, goal: str = "range", lo: float = 0.02, hi: float = 0.8,
               step: float = 0.02) -> dict:
    """Try every water fill from lo to hi; return the curve and the best fill."""
    p = clean(params)
    curve = []
    f = lo
    while f <= hi + 1e-9:
        r = simulate(dict(p, fill=round(f, 4)))
        curve.append((round(f, 4), score(r, goal)))
        f += step
    best = max(curve, key=lambda c: c[1]) if curve else (p["fill"], 0.0)
    return {"curve": curve, "best_fill": best[0], "best_value": best[1], "goal": goal}


def summary(result: dict) -> str:
    """One line a person can read: the setup and what the simulation says."""
    p = result["params"]
    setup = (f"{p['bottle_l']:g} L bottle, {round(p['fill'] * 100)}% water ({result['water_ml']} mL), "
             f"{p['psi']:g} psi, {p['angle']:g}°, {p['dry_g']:g} g empty, {p['nose']} nose, {p['fins']} fins, "
             f"{p['nozzle_mm']:g} mm nozzle")
    if not result["flew"]:
        return setup + " → no lift-off in the simulation"
    return (setup + f" → simulated {result['range_m']:.1f} m range, {result['apogee_m']:.1f} m apogee, "
            f"{result['max_speed_ms']:.0f} m/s top speed")


def ask_text(params: dict | None) -> str:
    """The question the Launch Lab puts into the chat ("Ask AquaFalcon why"). Re-computed here in Python,
    so the chat only ever sees numbers our own model produced. Worded so the what-if calculator and the
    chart shortcut leave it alone, and so even the offline backup brain picks its "how do you fly" answer."""
    r = simulate(params)
    p = r["params"]
    extras = []
    if p["bottle_l"] != 1.5:
        extras.append(f"{p['bottle_l']:g} L bottle")
    if p["dry_g"] != DEFAULTS["dry_g"]:
        extras.append(f"{p['dry_g']:g} g empty")
    if p["fins"] != 3:
        extras.append(f"{p['fins'] if p['fins'] else 'no'} fins")
    if p["nose"] != "cone":
        extras.append({"ogive": "rounded", "flat": "flat"}[p["nose"]] + " nose")
    if p["nozzle_mm"] < 15:
        extras.append(f"{p['nozzle_mm']:g} mm nozzle")
    setup = (f"{round(p['fill'] * 100)}% water ({r['water_ml']} mL), {p['psi']:g} psi, {p['angle']:g}°"
             + "".join(", " + e for e in extras))
    if not r["flew"]:
        return (f"Launch Lab simulation: no lift-off with {setup}. "
                f"How does a water rocket fly, and why not this time? Explain the physics.")
    sw = sweep_fill(p)
    return (f"Launch Lab simulation → {r['range_m']:.1f} m distance, {r['apogee_m']:.1f} m high with {setup}. "
            f"Explain the physics: how does it fly like that, and what should we change? "
            f"(Lab's sweet spot here: {round(sw['best_fill'] * 100)}% water.)")
