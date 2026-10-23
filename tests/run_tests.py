"""
run_tests.py - asks the chatbot every question in test_questions.yaml and saves a results table.

Usage (from the project folder):
    python tests/run_tests.py                    # uses the brain from .env (or offline)
    python tests/run_tests.py --backend offline  # force offline mode
    python tests/run_tests.py --before           # the FIRST naive version (no rules, no fact-check)

Output: tests/results/results_<brain>.csv  and  results_<brain>.md
Fill in the "Notes" column yourselves after reading the answers - that's your test documentation!
"""
import argparse
import time
import csv
import sys
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from bot import RocketBot  # noqa: E402

ADMITS = ["don't know", "do not know", "not recorded", "aren't recorded", "isn't recorded", "haven't", "have not",
          "hasn't", "not logged", "no record", "don't have", "do not have", "not something i have", "not sure",
          "not in my", "unknown", "won't guess", "not yet", "no data", "can't say"]
REDIRECTS = ["rocket", "flight path", "launch", "outside", "off-topic", "stick to", "ask me", "instead"]


def check(t: dict, answer: str) -> tuple[str, str]:
    a = answer.lower().replace("’", "'")   # treat curly apostrophes like normal ones
    if t["type"] == "unknown":
        ok = any(p in a for p in ADMITS)
        return ("PASS" if ok else "FAIL",
                "Admitted it doesn't know" if ok else "Did NOT admit it doesn't know - possible made-up fact")
    if t["type"] == "offtopic":
        ok = any(p in a for p in REDIRECTS)
        return ("PASS" if ok else "CHECK", "Redirected to rocket topics" if ok else "Check: may have answered off-topic")
    hits = [k for k in t["expect_any"] if k.lower() in a]
    return ("PASS", "Mentions: " + ", ".join(hits)) if hits else ("CHECK", "Expected one of: " + ", ".join(t["expect_any"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None, help="gemini | groq | ollama | offline (default: from .env)")
    ap.add_argument("--before", action="store_true", help="test the naive first version")
    ap.add_argument("--rescore", metavar="CSV",
                    help="re-check answers already saved in a results CSV (no AI calls - saves your free quota)")
    ap.add_argument("--delay", type=float, default=None,
                    help="seconds to wait between questions (default 5 for online brains, to stay inside free-tier limits)")
    args = ap.parse_args()

    bot = RocketBot(backend=args.backend, strict=not args.before)
    tests = yaml.safe_load(open(HERE / "test_questions.yaml", encoding="utf-8"))
    label = bot.backend + ("_before" if args.before else "")
    saved = {}
    if args.rescore:
        with open(args.rescore, encoding="utf-8") as f:
            saved = {int(r["#"]): r for r in csv.DictReader(f)}
        label = Path(args.rescore).stem.replace("results_", "")
    print(f"Testing {bot.name} with brain = {label} ({len(tests)} questions)\n")

    delay = args.delay if args.delay is not None else (0 if bot.backend == "offline" else 5)
    rows = []
    for i, t in enumerate(tests):
        if t["id"] in saved:
            answer, used = saved[t["id"]]["Answer"], saved[t["id"]]["Brain"]
        else:
            if i and delay:
                time.sleep(delay)
            answer, used = bot.reply(t["question"])
        result, auto_note = check(t, answer)
        if "fallback" in used:
            auto_note += " (answered by the offline backup - the online brain failed)"
        rows.append({"#": t["id"], "Area": t["area"], "Question": t["question"], "Answer": answer,
                     "Brain": used, "Result": result, "Auto-check": auto_note, "Notes": ""})
        print(f"[{result:5}] Q{t['id']:>2} {t['question']}")

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    with open(out / f"results_{label}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    passed = sum(r["Result"] == "PASS" for r in rows)
    def cell(s):
        return str(s).replace("|", "/").replace("\n", "<br>")
    md = [f"# Test results - {bot.name} (brain: {label})", "",
          f"Run on {datetime.now():%Y-%m-%d %H:%M}. Auto-check passed {passed}/{len(rows)}.", "",
          "| # | Area | Question | Answer | Result | Auto-check | Notes |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['#']} | {cell(r['Area'])} | {cell(r['Question'])} | {cell(r['Answer'])} | {r['Result']} | {cell(r['Auto-check'])} | |"
           for r in rows]
    (out / f"results_{label}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nPassed {passed}/{len(rows)}. Saved tests/results/results_{label}.csv and .md")


if __name__ == "__main__":
    main()
