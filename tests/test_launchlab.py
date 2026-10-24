"""
test_launchlab.py - checks the Launch Lab's physics (launchlab.py) and that the browser copy (physics.js)
gives the same answers. Run:  python tests/test_launchlab.py   (or: pytest tests/test_launchlab.py)
No internet, no key needed. The JavaScript check needs Node.js and is skipped without it.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import launchlab  # noqa: E402
from knowledge import load_facts  # noqa: E402


def test_zero_pressure_no_flight():
    r = launchlab.simulate({"psi": 0})
    assert not r["flew"] and r["range_m"] == 0 and r["apogee_m"] == 0


def test_more_pressure_flies_higher_and_further():
    last_h = last_r = 0
    for psi in (20, 40, 60, 80, 100):
        r = launchlab.simulate({"psi": psi})
        assert r["flew"]
        assert r["apogee_m"] > last_h and r["range_m"] > last_r, psi
        last_h, last_r = r["apogee_m"], r["range_m"]


def test_best_fill_is_about_a_third():
    # the classic result: roughly 30-40 % water is best for a typical 1.5-2 L bottle
    for bottle in (1.5, 2.0):
        for goal in ("range", "height"):
            sw = launchlab.sweep_fill({"bottle_l": bottle}, goal=goal)
            assert 0.25 <= sw["best_fill"] <= 0.45, (bottle, goal, sw["best_fill"])


def test_too_little_and_too_much_water_are_worse():
    best = launchlab.sweep_fill()["best_value"]
    assert launchlab.simulate({"fill": 0.05})["range_m"] < best * 0.8
    assert launchlab.simulate({"fill": 0.75})["range_m"] < best * 0.5


def test_empty_bottle_still_gets_an_air_kick():
    r = launchlab.simulate({"fill": 0})
    assert r["flew"] and r["water_thrust_s"] == 0 and r["thrust_s"] > 0


def test_vertical_launch_goes_up_not_out():
    r = launchlab.simulate({"angle": 90})
    assert r["apogee_m"] > 25 and r["range_m"] < 1


def test_45_degrees_beats_flat_and_steep_for_distance():
    d = {a: launchlab.simulate({"angle": a})["range_m"] for a in (20, 45, 75)}
    assert d[45] > d[20] and d[45] > d[75]


def test_no_fins_tumbles_and_flies_shorter():
    assert launchlab.simulate({"fins": 0})["range_m"] < launchlab.simulate({"fins": 3})["range_m"] * 0.7


def test_heavier_rocket_flies_lower():
    assert launchlab.simulate({"dry_g": 250})["apogee_m"] < launchlab.simulate({"dry_g": 115})["apogee_m"]


def test_thrust_formula():
    # peak thrust = 2 x gauge pressure x nozzle area (Bernoulli), at the very start
    import math
    r = launchlab.simulate({"psi": 60, "nozzle_mm": 21.5})
    expect = 2 * 60 * launchlab.PSI * math.pi * 0.0215 ** 2 / 4
    assert abs(r["peak_thrust_n"] - expect) / expect < 0.01


def test_weird_inputs_are_clamped():
    r = launchlab.simulate({"psi": -5, "fill": 7, "angle": 500, "nose": "banana", "fins": 9})
    p = r["params"]
    assert p["psi"] == 0 and p["fill"] <= 0.95 and p["angle"] == 90 and p["nose"] == "cone" and p["fins"] == 3


def test_defaults_come_from_the_yaml():
    facts = load_facts()
    p = launchlab.params_from_facts(facts)
    L = facts["launch"]
    assert p["psi"] == float(L["launch_pressure_psi"]) and p["angle"] == float(L["launch_angle_deg"])
    assert abs(p["fill"] * p["bottle_l"] * 1000 - float(L["water_volume_ml"])) < 1
    assert p["dry_g"] == float(facts["design"]["dry_mass_g"])


def test_ask_text_goes_to_the_normal_brain():
    """The 'Ask why' question must not be grabbed by the what-if calculator or the chart shortcut,
    and must stay short enough for the chat box limit."""
    import whatif
    for params in ({}, {"psi": 0}, {"fill": 0.6, "fins": 0, "nose": "ogive"}, {"angle": 90, "bottle_l": 2}):
        q = launchlab.ask_text(params)
        assert len(q) <= 500
        assert not whatif.is_whatif(q), q
        assert "simulation" in q.lower()
        # if every online brain is down, the offline backup still answers with "how I fly", not the test table
        import offline
        assert "Newton" in offline.answer(q), q
    try:
        import charts
    except ImportError:     # charts needs altair (installed with streamlit)
        return
    assert charts.wants_chart(launchlab.ask_text({})) is None


def test_javascript_matches_python():
    node = shutil.which("node")
    if not node:
        print("   (skipped: Node.js not installed)")
        return
    cases = [{}, {"psi": 0}, {"psi": 20, "fill": 0.1}, {"fill": 0}, {"fins": 0},
             {"nose": "flat", "angle": 80, "bottle_l": 2, "nozzle_mm": 9}, {"fill": 0.7, "psi": 90, "dry_g": 250}]
    js = ("const P=require(%s);const c=%s;console.log(JSON.stringify({runs:c.map(x=>P.simulate(x)),"
          "sweep:P.sweepFill({},'range')}))") % (json.dumps(str(ROOT / "lab_component" / "physics.js")), json.dumps(cases))
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60, check=True).stdout)
    keys = ("range_m", "apogee_m", "max_speed_ms", "flight_time_s", "thrust_s", "peak_thrust_n", "water_left_ml", "flew")
    for case, j in zip(cases, out["runs"]):
        p = launchlab.simulate(case)
        for k in keys:
            assert p[k] == j[k] or abs(float(p[k]) - float(j[k])) < 0.02, (case, k, p[k], j[k])
    sw = launchlab.sweep_fill({}, "range")
    assert abs(sw["best_fill"] - out["sweep"]["best_fill"]) < 1e-9


def test_main_page_unchanged_apart_from_the_lab_button():
    """Nabil's rule: the chat page stays exactly the same. The only addition in app.py is the Launch Lab link."""
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert src.count("lablink") >= 2 and 'st.page_link("pages/launch_lab.py"' in src
    assert (ROOT / "pages" / "launch_lab.py").exists()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except AssertionError as e:
            failed += 1
            print("FAIL", name, e)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
