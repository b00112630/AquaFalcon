"""
test_regressions.py - checks for the bugs found in the QA inspection, so they never come back.

Run (from the project folder, no internet or key needed):
    python tests/test_regressions.py          (or:  pytest tests/test_regressions.py)
Add --live to also ask the real AI brain from .env the three "made-up fact" questions.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import offline  # noqa: E402
from bot import VOICE_STYLE, clean_question, fact_check, system_prompt  # noqa: E402
from knowledge import derived_facts, load_facts  # noqa: E402

ADMITS = ("didn't measure", "did not measure", "not measured", "wasn't measured", "isn't recorded", "not recorded",
          "haven't", "hasn't", "don't know", "won't guess", "not yet")


# ---------- 1. the fact-checker: a number only counts with what it measures
def test_height_range_is_flagged():
    # "10" and "15" appear in the notes ("10-15 launches", "15 November") - that must NOT make "10 to 15 m" OK
    note = fact_check("My exact max height isn't recorded yet, but likely around 10 to 15 meters up!", "how high did it fly?")
    assert "10 meters" in note and "15 meters" in note


def test_competition_pressure_claim_is_flagged():
    note = fact_check("I launched at 60 psi, set using the competition's electric pump on launch day.",
                      "what pressure did you launch at?")
    assert "competition hasn't happened" in note


def test_real_numbers_pass():
    best = load_facts()["best_result"]["distance_m"]
    assert fact_check(f"My best flight was {best} m with 500 mL of water at 60 psi and 45 degrees. "
                      "Everyone stays 4.6 m (15 ft) back. 60 psi is about 4.1 bar.", "best flight?") == ""
    assert fact_check("At the competition I must fly at least 6 m.", "what is the minimum?") == ""


def test_labelled_height_estimate_passes():
    h = derived_facts()["theoretical_max_height_m"]
    assert fact_check(f"In theory the maximum height is about {h} m (not measured).", "estimate the height") == ""


def test_invented_speed_is_flagged():
    assert "30 m/s" in fact_check("I leave the pad at 30 m/s!", "how fast?")


# ---------- 2. the AI's instructions
def test_prompt_rules():
    p = system_prompt("how high did it fly?")
    assert "NOT measured" in p and "Give NO height number" in p            # height: say not measured
    assert "THEORETICAL" in system_prompt("can you estimate the max height?")   # estimate only when asked
    assert "has NOT happened yet" in p                                      # no competition-day facts
    assert "did NOT compare angles" in p                                    # 45 degrees wasn't proven best
    assert "plans for next time" in p                                       # improvements are not done
    assert "أربعين" not in VOICE_STYLE                                      # no "forty metres" seed


# ---------- 3. the offline backup brain
def test_offline_height():
    a = offline.answer("how high did it fly?").lower()
    assert any(p in a for p in ADMITS)
    assert not re.search(r"\b(10|15)\b", a)


def test_offline_height_estimate_only_when_asked():
    h = str(derived_facts()["theoretical_max_height_m"])
    assert h not in offline.answer("how high did it go?")
    a = offline.answer("can you estimate how high it went?")
    assert h in a and "theoretical" in a.lower()


def test_offline_pressure_not_competition():
    a = offline.answer("what pressure did you launch at?").lower()
    assert "test" in a and "don't know that value yet" in a


def test_offline_angle_not_proven():
    a = offline.answer("what launch angle did you use and why?").lower()
    assert "haven't compared" in a


# ---------- 4. blank messages
def test_whitespace_input_is_ignored():
    for blank in ("", "   ", "\n\t  ", None):
        assert clean_question(blank) is None
    assert clean_question("  how far did you fly?  ") == "how far did you fly?"


# ---------- 5. data / greetings / packaging
def test_no_future_test_dates():
    assert all("date" not in row for row in load_facts()["test_results"])


def test_greetings():
    js = (ROOT / "voice_component" / "voice.js").read_text(encoding="utf-8")
    greetings = js[js.index("var GREETINGS = ["):js.index("];", js.index("var GREETINGS = ["))]
    assert "how high" not in greetings.lower() and "hey" not in greetings.lower()
    assert "Team 7" not in js        # team name comes from rocket_info.yaml


def test_requirements_clean():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "fastapi" not in req and "uvicorn" not in req


# ---------- 5. the "what if" calculator (whatif.py) and auto charts (charts.py)
import whatif  # noqa: E402


def _est(text):
    return float(re.search(r"\*\*(\d+(?:\.\d+)?) (?:m|م)\*\*", text).group(1))


def test_whatif_pressure_inside_range():
    r = whatif.answer("what if we used 50 psi?")
    assert r and "Estimate from our test data" in r["text"] and "Assumption:" in r["text"]
    assert "rough guess" not in r["text"]
    m = whatif.Model()
    assert abs(_est(r["text"]) - round(m.predict(p=50), 1)) < 0.05
    assert _est(whatif.answer("what if 40 psi")["text"]) < _est(r["text"])   # more pressure, further


def test_whatif_pressure_outside_range():
    t = whatif.answer("what if we used 70 psi?")["text"]
    assert "outside what we tested" in t and "rough guess" in t and "burst limit" in t
    assert _est(t) > load_facts()["best_result"]["distance_m"] - 1
    assert "won't put a number" in whatif.answer("what if we pumped it to 150 psi")["text"]


def test_whatif_water_and_optimum():
    t = whatif.answer("what if 400 mL water?")["text"]
    assert "Estimate" in t and "peaks around" in t and "third" in t
    assert _est(t) < whatif.Model().base_d          # 400 mL is off the ~1/3-bottle peak
    assert "outside what we tested" in whatif.answer("what if we only used 100 ml")["text"]
    assert "only holds" in whatif.answer("what if 1.5 L of water")["text"]


def test_whatif_angle():
    import math
    m = whatif.Model()
    t = whatif.answer("what about 30 degrees?")["text"]
    assert "only launched at 45°" in t and "sin 2θ" in t
    assert abs(_est(t) - round(m.base_d * math.sin(math.radians(60)))) < 0.6


def test_whatif_exact_test_is_a_measurement():
    t = whatif.answer("what about 700 mL at 60 psi?")["text"]
    assert "actually tested" in t and "17 m" in t


def test_whatif_recomputes_from_yaml():
    f = load_facts()
    before = _est(whatif.answer("what if we used 50 psi?", facts=f)["text"])
    for row in f["test_results"]:
        row["distance_m"] *= 2                      # pretend Nabil pasted in new real data
    after = _est(whatif.answer("what if we used 50 psi?", facts=f)["text"])
    assert abs(after - 2 * before) < 0.3


def test_whatif_arabic():
    t = whatif.answer("شو لو استخدمنا 70 psi؟")["text"]
    assert "تقدير من بيانات تجاربنا" in t and "تخمين تقريبي" in t
    assert whatif.answer("لو حطينا ٤٠٠ مل مي؟")["text"].count("400") >= 1


def test_whatif_voice_is_short_and_plain():
    t = whatif.answer("what if we used 70 psi?", voice=True)["text"]
    assert len(t.split()) < 40 and "*" not in t and "rough guess" in t and not t.lower().startswith("hey")


def test_not_whatif():
    for q in ("how far did you fly?", "what if it rains?", "would 70 psi be safe?", "why 45 degrees?"):
        assert whatif.answer(q) is None, q


def test_whatif_through_bot_offline_no_factcheck_flag():
    from bot import RocketBot
    bot = RocketBot(backend="offline")
    a, brain = bot.reply("what if we used 70 psi?")
    assert brain == "calculator" and "Fact-check" not in a and bot.chart and bot.chart["first"] == "pressure"
    # the AI repeating the calculator's number in a follow-up is not flagged either
    nums = whatif.answer("what if we used 70 psi?")["numbers"]
    assert fact_check(f"At 70 psi I'd fly roughly {_est(a):g} m, but that's a guess.", "why?", nums) == ""
    assert "Fact-check" in fact_check("At 70 psi I'd fly roughly 31 m.", "why?", nums)


def test_chart_trigger():
    import charts
    assert charts.wants_chart("show me a graph") == "explicit"
    assert charts.wants_chart("Show me your test results") == "results"
    assert charts.wants_chart("ورجيني رسم بياني للنتائج") == "explicit"
    assert charts.first_tab("graph distance vs pressure") == "pressure"
    assert charts.wants_chart("tell me about the fins") is None
    from bot import RocketBot
    bot = RocketBot(backend="offline")
    a, brain = bot.reply("show me a graph of your tests")
    assert bot.chart and brain == "test data" and str(load_facts()["best_result"]["distance_m"]) in a
    a, _ = bot.reply("Show me your test results")
    assert bot.chart and "|" in a                   # the table answer + a chart under it
    assert "chart in the chat" in "".join(bot.stream("show me a graph", voice=True))


def test_charts_build_from_yaml():
    import charts
    n = len(load_facts()["test_results"])
    for kind in ("tests", "pressure", "water"):
        spec = charts.build(kind).to_dict()
        assert spec, kind
    assert len(charts._rows()) == n
    assert charts.build("pressure", point={"x": 70, "y": 26}).to_dict()


def live():
    from bot import RocketBot
    bot = RocketBot()
    bad = 0
    for q, must_not in [("how high did it fly?", r"\d+(\.\d+)?\s*(m|meters|metres)\b(?! with| at)(?<!22\.5 m)"),
                        ("what pressure did you launch at?", r"competition.{0,60}(60 psi)|(60 psi).{0,80}competition"),
                        ("what launch angle did you use and why?", r"tests? (showed|proved|confirmed)|matches our test")]:
        a, brain = bot.reply(q)
        ok = not re.search(must_not, a, re.I | re.S) and "Fact-check" not in a
        bad += not ok
        print(("PASS" if ok else "FAIL"), f"[{brain}]", q, "->", a.replace("\n", " ")[:400])
    return bad


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, f in tests:
        try:
            f()
            print("PASS", name)
        except AssertionError as e:
            failed += 1
            print("FAIL", name, e)
    if "--live" in sys.argv:
        failed += live()
    print(f"\nall {len(tests)} offline checks passed" + (" + live checks" if "--live" in sys.argv else "")
          if not failed else f"\n{failed} FAILED")
    sys.exit(1 if failed else 0)
