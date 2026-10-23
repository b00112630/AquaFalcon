"""
knowledge.py - loads what the chatbot knows.

  * rocket_info.yaml     -> the team's facts (name, design, tests, safety ...)
  * knowledge/physics.md -> short physics notes (Newton's laws, CG/CP, ...)

Both are plain text files, so the team can edit them without touching code.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
FACTS_FILE = ROOT / "rocket_info.yaml"
PHYSICS_FILE = ROOT / "knowledge" / "physics.md"


def load_facts() -> dict:
    """Read rocket_info.yaml into a Python dictionary."""
    with open(FACTS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def facts_text() -> str:
    """The fact file as raw text (with comments)."""
    return FACTS_FILE.read_text(encoding="utf-8")


def compact_facts() -> str:
    """The fact file WITHOUT comments - this is what we paste into the AI's instructions.
    Smaller prompt = faster answers and fewer tokens used from the free quota."""
    return yaml.safe_dump(load_facts(), allow_unicode=True, sort_keys=False, width=200,
                          default_flow_style=None)


def relevant_physics(question: str, max_sections: int = 2) -> str:
    """Pick only the physics sections that match the question (keeps the prompt small)."""
    common = {"rocket", "rockets", "your", "what", "does", "doesn", "about", "with", "that", "this",
              "have", "from", "when", "there", "they", "tell", "much", "many"}
    words = {w for w in re.findall(r"[a-z]+", question.lower()) if len(w) > 3} - common
    scored = []
    for title, text in physics_sections().items():
        section_words = set(re.findall(r"[a-z]+", (title + " " + text).lower()))
        score = len(words & section_words) + 3 * len(words & set(re.findall(r"[a-z]+", title.lower())))
        if score:
            scored.append((score, title, text))
    scored.sort(reverse=True)
    return "\n\n".join(f"## {t}\n{x}" for _, t, x in scored[:max_sections])


def physics_text() -> str:
    return PHYSICS_FILE.read_text(encoding="utf-8")


def physics_sections() -> dict:
    """Split physics.md into {heading: text} so offline mode can quote one section."""
    sections, current = {}, None
    for line in physics_text().splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    return {k: _reflow(v) for k, v in sections.items()}


def _reflow(lines: list) -> str:
    """Join wrapped lines back into paragraphs/bullets so answers read nicely."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") or not out:
            out.append(line)
        else:
            out[-1] += " " + line
    return "\n".join(out)


def known_numbers() -> set:
    """Every number that appears in our two knowledge files.
    Used by the fact-checker to spot numbers the AI might have made up."""
    text = facts_text() + "\n" + physics_text()
    return {normalise_number(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}


# ---------------------------------------------------------------- fact-check helpers
# A number only counts as "known" together with WHAT it measures (its unit). So "15 m" is NOT grounded just
# because "15" appears somewhere else ("10-15 launches", "15 November").
#   unit word -> (kind, factor that converts it to the kind's base unit)
UNITS = {
    "m": ("length", 1), "metre": ("length", 1), "meter": ("length", 1), "cm": ("length", 0.01),
    "mm": ("length", 0.001), "km": ("length", 1000), "ft": ("length", 0.3048), "feet": ("length", 0.3048),
    "foot": ("length", 0.3048),
    "ml": ("volume", 1), "millilitre": ("volume", 1), "milliliter": ("volume", 1),
    "l": ("volume", 1000), "litre": ("volume", 1000), "liter": ("volume", 1000),
    "psi": ("pressure", 1), "bar": ("pressure", 14.5038),
    "g": ("mass", 1), "gram": ("mass", 1), "kg": ("mass", 1000), "kilogram": ("mass", 1000),
    "degree": ("angle", 1), "°": ("angle", 1), "deg": ("angle", 1),
    "%": ("percent", 1), "percent": ("percent", 1),
    "s": ("time", 1), "sec": ("time", 1), "second": ("time", 1),
    "m/s": ("speed", 1), "km/h": ("speed", 1 / 3.6),
}
# YAML keys end in their unit: distance_m, total_length_cm, water_ml, pressure_psi, angle_deg, dry_mass_g
KEY_UNITS = {"_m": "m", "_cm": "cm", "_mm": "mm", "_ml": "ml", "_l": "l", "_psi": "psi", "_bar": "bar",
             "_g": "g", "_kg": "kg", "_deg": "degree", "_s": "s"}
UNIT_RE = (r"(m/s|km/h|cm|mm|km|metres?|meters?|m|millilit(?:re|er)s?|ml|lit(?:re|er)s?|l|psi|bar|"
           r"kilograms?|kg|grams?|g|%|percent|degrees?|deg|°|seconds?|secs?|s|feet|foot|ft)(?![a-zA-Z])")
NUM = r"(\d+(?:\.\d+)?)"


def unit_kind(unit: str):
    """'meters' -> ('length', 1.0) ; unknown unit -> None"""
    u = unit.lower()
    if u not in UNITS and u.endswith("s") and u[:-1] in UNITS:
        u = u[:-1]
    if u.startswith("millilit"):
        u = "ml"
    elif u.startswith("lit"):
        u = "l"
    return UNITS.get(u)


def measurements(text: str) -> list:
    """Every 'number + unit' in a text, ranges included ("10 to 15 meters" -> 10 m and 15 m).
    Returns [(number_as_written, unit_as_written, kind, value_in_base_unit), ...]"""
    found = []
    rng = rf"{NUM}\s*(?:-|–|—|to|and)\s*{NUM}\s*{UNIT_RE}"
    for a, b, unit in re.findall(rng, text, flags=re.I):
        k = unit_kind(unit)
        if k:
            found += [(a, unit, k[0], float(a) * k[1]), (b, unit, k[0], float(b) * k[1])]
    for n, unit in re.findall(rf"{NUM}\s*{UNIT_RE}", text, flags=re.I):
        k = unit_kind(unit)
        if k:
            found.append((n, unit, k[0], float(n) * k[1]))
    return found


def derived_facts() -> dict:
    """Numbers that follow from our data by simple physics (NOT measured). The bot may quote these only as
    clearly-labelled theoretical estimates, and the fact-checker accepts them."""
    out = {}
    best = (load_facts().get("best_result") or {}).get("distance_m")
    try:   # no drag, 45 degrees: max height = range / 4
        out["theoretical_max_height_m"] = round(float(best) / 4, 1)
    except (TypeError, ValueError):
        pass
    return out


def test_angles() -> list:
    """The launch angles used in the test rows (to stop claims like 'tests showed 45 degrees is best')."""
    return sorted({t.get("angle_deg") for t in load_facts().get("test_results") or [] if t.get("angle_deg") is not None})


def known_measurements() -> list:
    """(kind, value) for every measurement in our files: YAML fields named with their unit, any
    'number + unit' written in the YAML text or physics.md, and the derived physics estimates."""
    known = []

    def walk(node, key=""):
        if isinstance(node, dict):
            for k2, v in node.items():
                walk(v, str(k2))
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            for suf, unit in KEY_UNITS.items():
                if key.lower().endswith(suf):
                    kind, f = unit_kind(unit)
                    known.append((kind, float(node) * f))
                    break
        elif isinstance(node, str):
            known.extend((kind, val) for _, _, kind, val in measurements(node))

    walk(load_facts())
    known.extend((kind, val) for _, _, kind, val in measurements(physics_text()))
    for name, val in derived_facts().items():
        known.append(("length", float(val)))
    return known


def is_known_measurement(kind: str, value: float, known: list | None = None) -> bool:
    """True if a measurement of this kind and value (within 2.5 %, so 15 ft = 4.6 m, 4.1 bar = 60 psi) is in our files."""
    known = known_measurements() if known is None else known
    return any(k == kind and abs(v - value) <= max(abs(v), abs(value)) * 0.025 + 1e-9 for k, v in known)


def normalise_number(n: str) -> str:
    n = n.rstrip("0").rstrip(".") if "." in n else n
    return n.lstrip("0") or "0"


def is_unknown(value) -> bool:
    return value is None or str(value).strip().lower() in {"unknown", "", "tbd", "?"}
