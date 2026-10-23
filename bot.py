"""
bot.py - the heart of the chatbot.

For every question:
  1. Build the instructions ("system prompt"): the rocket's personality + rules +
     the team facts from rocket_info.yaml + the matching physics notes.
  2. Send instructions + recent chat + question to the brain (backends.py) and
     STREAM the answer back piece by piece (so it starts showing instantly).
  3. If that brain fails (no internet, quota used up...), try the next brain that
     has a key, and finally the offline keyword brain - the demo never dies.
  4. Fact-check the answer: flag any measurement that isn't in our files.
"""
import os
import re

from dotenv import load_dotenv

import charts
import offline
import whatif
from backends import BACKENDS, BackendError, pick_backend
from knowledge import (compact_facts, derived_facts, facts_text, is_known_measurement, is_unknown, known_measurements,
                       load_facts, measurements, relevant_physics, test_angles)

load_dotenv()

MAX_HISTORY = 6  # how many earlier messages the bot remembers (fewer = faster + cheaper)


VOICE_STYLE = """
VOICE MODE: your answer is read out loud by a phone voice. Never start with "Hey". Answer in 1 or 2 short spoken sentences (under 35 words),
the direct answer first. Plain words only: no lists, tables, markdown, emojis or symbols. Say units in words (in Arabic too, e.g. "ثلاثة كيلو")."""


def system_prompt(question: str = "", voice: bool = False) -> str:
    """The instructions that give the bot its personality and rules (voice=True: short, speakable answers)."""
    facts = load_facts()
    r = facts["rocket"]
    physics = relevant_physics(question) or "(use correct general physics)"
    height_rule, competition_rule, angle_rule = claim_rules(facts, question)
    style = ("Calm, warm and lively, like talking on the phone. NO emojis, lists or tables." if voice else
             "lively, warm, proud, fun. 1-3 emojis. Short: 2-5 sentences, or a short list/table if useful.")
    return f"""You are {r['name']} {r['emoji']}, the water rocket built by {r['team_name']} for {r['course']}.
You ARE the rocket: talk in first person ("my fins", "when I launch").

STYLE: {style}
Explain physics simply and link it to MY design.
LANGUAGE: the user's LATEST message decides. Written in English letters -> answer in English (always, even if
earlier messages were Arabic). Written in Arabic script (even with a few English words mixed in) -> answer in
Arabic script: simple, friendly Arabic a Jordanian/Palestinian student would say (a light Levantine touch like
"شو" or "كتير" is fine; never stiff or formal).
TYPOS: people type fast and voice-to-text mishears. Read every message generously and answer the closest rocket
question it most likely means (e.g. "how for a can you fight" = "how far can you fly"; "hight" = height). Only treat
it as off-topic if no rocket meaning is plausible.

RULES
1. Team facts come ONLY from TEAM FACTS. Never invent or estimate a team number.
2. If a team fact is missing or "unknown", say it isn't recorded yet. Don't guess.
3. Physics: answer correctly, using the notes when they help.
4. Off-topic (homework, sports, other subjects...): don't answer it, not even a hint.
   Redirect playfully in 1-2 sentences and suggest a rocket question.
5. Never suggest anything that breaks the safety rules.
6. NEVER estimate a quantity the team did not record (height, speed, flight time, cost, burst pressure...).
   Say plainly that it wasn't measured. {height_rule}
7. {competition_rule}
8. Only say "our tests showed X" if the TEST RESULTS rows show it. Never give a date for a test unless its row has
   one. {angle_rule}
9. Describe the design exactly as TEAM FACTS say: no extra adjectives or features. Answers under "What would you
   improve?" are plans for next time, NOT things we already did. Don't say the rocket is all recycled: only the bottles
   and the folder are reused; clay, duct tape and hot glue are new.
10. Don't open with a greeting unless the user greeted you; if you do greet, say "Hi" (never "Hey").

TEAM FACTS
{compact_facts()}
PHYSICS NOTES
{physics}""" + (VOICE_STYLE if voice else "")


def claim_rules(facts: dict, question: str = "") -> tuple[str, str, str]:
    """The data-driven parts of rules 6-8 (they follow the YAML, so they stay right when the team edits it)."""
    h = derived_facts().get("theoretical_max_height_m")
    wants_theory = re.search(r"estimat|theor|calculat|approx|roughly|predict|physics|work (it )?out|guess", question, re.I)
    if h and wants_theory:   # the number is only given to the AI when the user asked for an estimate
        height_rule = (f"Max height was NOT measured. The user asked for an estimate, so you may say: about {h} m is the "
                       "THEORETICAL maximum (no-drag physics for our best flight at 45 degrees: height = range / 4), the real "
                       f"height was lower because of drag. Use exactly {h} m (not a range) and call it a theoretical estimate.")
    else:
        height_rule = ("Max height was NOT measured: if asked how high it flew, say we didn't measure height (we measured "
                       "distance) and offer to give a physics estimate. Give NO height number.")
    comp = facts.get("competition") or {}
    if is_unknown(comp.get("result_distance_m")) and is_unknown(comp.get("placement")):
        competition_rule = (f"The competition ({comp.get('date', 'date unknown')}) has NOT happened yet / has no recorded "
                            "result. Never say what happened there (pressure, distance, place). Our pressures, distances "
                            "and angles come from our OWN test launches (bike pump with a gauge); on competition day "
                            "the organisers' pump sets the pressure, and we don't know that value yet.")
    else:
        competition_rule = ("Competition facts come only from the competition block of TEAM FACTS; our test numbers are "
                            "from our own test launches, not the competition.")
    angles = test_angles()
    angle_rule = (f"Every test launch used {angles[0]} degrees, so our tests did NOT compare angles: say we chose "
                  f"{angles[0]} degrees from physics (best range in theory), not because tests proved it best, and don't "
                  "call it the best angle for our design."
                  if len(angles) == 1 else "")
    return height_rule, competition_rule, angle_rule


def naive_prompt(question: str = "") -> str:
    """The FIRST version we tried, before fixing the limitations (kept for the report)."""
    r = load_facts()["rocket"]
    return f"You are {r['name']}, a friendly chatbot about our water rocket. Answer every question helpfully.\n" \
           f"Here is some info about our rocket:\n{facts_text()}"


COMPETITION_WORDS = re.compile(r"competition|launch day|on the day|contest", re.I)
PAST_CLAIM = re.compile(r"\b(?:flew|went|reached|landed|placed|won|scored|got|launched|used|set|was|were)\b", re.I)


def fact_check(answer: str, question: str, extra: list | None = None) -> str:
    """Our fix for the 'made-up number' problem: returns a warning (or "") for any measurement in the answer
    that isn't in our files or the question. A number only counts as grounded TOGETHER with what it measures:
    "15 m" is not accepted just because "15" appears elsewhere ("10-15 launches", "15 November")."""
    known = known_measurements() + list(extra or [])   # extra = the what-if calculator's own computed numbers
    asked = {(kind, round(val, 6)) for _, _, kind, val in measurements(question)}
    asked_numbers = set(re.findall(r"\d+(?:\.\d+)?", question))
    suspicious = []
    for num, unit, kind, val in measurements(answer):
        if (kind, round(val, 6)) in asked or (num in asked_numbers and not measurements(question)):
            continue
        if not is_known_measurement(kind, val, known):
            suspicious.append(f"{num} {unit}")
    notes = []
    if suspicious:
        notes.append("I couldn't find " + ", ".join(dict.fromkeys(suspicious)) +
                     " in our team notes - treat it as an estimate, not a measured result.")
    comp = load_facts().get("competition") or {}
    if is_unknown(comp.get("result_distance_m")) and is_unknown(comp.get("placement")):
        for sentence in re.split(r"(?<=[.!?])\s+|\n", answer):
            if (COMPETITION_WORDS.search(sentence) and PAST_CLAIM.search(sentence)
                    and any(k in ("pressure", "length") for _, _, k, _ in measurements(sentence))
                    and not re.search(r"at least|minimum|must|need", sentence, re.I)):
                notes.append("The competition hasn't happened yet, so no competition-day numbers are recorded - "
                             "our numbers come from our own test launches.")
                break
    if not notes:
        return ""
    return "\n\n🔎 *Fact-check: " + " ".join(notes) + "*"


def clean_question(text) -> str | None:
    """A message worth answering, or None for empty / whitespace-only input (no empty bubble, no wasted AI call)."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


class RocketBot:
    def __init__(self, backend: str | None = None, strict: bool = True):
        """backend: 'groq', 'gemini', 'ollama', 'offline' or None (= decide from .env).
        strict: True = improved version (rules + fact-check); False = first naive version."""
        self.backend = backend or pick_backend()
        self.strict = strict
        self.name = load_facts()["rocket"]["name"]
        self.used = self.backend   # which brain actually answered the last question
        self.chart = None          # chart to draw under the last answer (see charts.py), or None

    def _brains_to_try(self) -> list:
        """The chosen brain first, then any other brain that has a key."""
        order = [self.backend]
        if os.getenv("GROQ_API_KEY", "").strip():
            order.append("groq")
        if os.getenv("GEMINI_API_KEY", "").strip():
            order.append("gemini")
        return [b for i, b in enumerate(order) if b in BACKENDS and b not in order[:i]]

    def stream(self, message: str, history: list | None = None, voice: bool = False):
        """Yield the answer in small pieces. After it finishes, self.used says which brain answered
        and self.chart says which chart (if any) to draw under it.
        voice=True (voice mode): ask for short answers that sound natural when read aloud."""
        history = [{"role": m["role"], "content": m["content"]} for m in (history or [])][-MAX_HISTORY:]
        self.chart = None
        # 1) "what if we used 70 psi?" -> computed in Python from the test data (whatif.py), never by the AI
        calc = whatif.answer(message, voice=voice)
        if calc:
            self.used = "calculator"
            if calc.get("chart"):
                self.chart = dict(calc["chart"], ar=bool(whatif.AR.search(message)))
            yield calc["text"]
            return
        # 2) "show me a graph" -> a short caption from the YAML + a chart in the bubble (no AI call needed)
        self.chart = charts.spec_for(message)
        if self.chart and charts.wants_chart(message) == "explicit":
            self.used = "test data"
            yield charts.explicit_text(message, voice)
            return
        # numbers the calculator gave earlier in this chat are ours too - the fact-checker must not flag them
        extra = []
        for m in history[-4:]:
            if m["role"] == "user":
                extra += (whatif.answer(m["content"]) or {}).get("numbers", [])
        context = message + " " + " ".join(m["content"] for m in history[-2:] if m["role"] == "user")
        prompt = system_prompt(context, voice) if self.strict else naive_prompt(context)
        if self.chart:   # results question: the app draws the chart, so the AI shouldn't try to
            prompt += ("\nA chart of the test results is shown under your answer automatically: don't draw text charts "
                       "and don't say you can't show graphs.")
        chart_note = ""
        if self.chart and voice:
            chart_note = " حطيتلك رسم بياني بالمحادثة." if whatif.AR.search(message) else " I put a chart in the chat."
        problems = []
        for brain in self._brains_to_try():
            pieces = []
            try:
                for piece in BACKENDS[brain](prompt, history, message):
                    pieces.append(piece)
                    yield piece
            except BackendError as e:
                if pieces:            # failed half-way: keep what we have
                    break
                problems.append(str(e))
                continue              # failed before saying anything: try the next brain
            except Exception as e:    # e.g. a broken connection mid-stream
                if pieces:
                    break
                problems.append(f"{brain}: {e}")
                continue
            if pieces:
                self.used = brain
                if problems:   # an earlier brain failed (e.g. a per-minute limit): note it in the terminal
                    print(f"[bot] {brain} answered because:", "; ".join(problems), flush=True)
                if chart_note:
                    yield chart_note
                if self.strict:
                    yield fact_check("".join(pieces), message, extra)
                return
        # every online brain failed (or none is set up) -> offline keyword brain
        self.used = "offline" if not problems else "offline (fallback)"
        yield offline.answer(message)
        if chart_note:
            yield chart_note
        if problems:   # the reason goes to the terminal; the chat just gets a small, calm footer
            print("[bot] offline backup brain answered because:", "; ".join(problems), flush=True)
            yield "\n\n_(📡 offline backup brain)_"

    def reply(self, message: str, history: list | None = None) -> tuple[str, str]:
        """Answer in one go (used by the test script). Returns (answer, which_brain_answered)."""
        answer = "".join(self.stream(message, history))
        return answer, self.used


if __name__ == "__main__":
    # Quick terminal chat:  python bot.py
    bot = RocketBot()
    print(f"{bot.name} is ready (brain: {bot.backend}). Type 'quit' to stop.\n")
    history = []
    while True:
        q = input("You: ").strip()
        if q.lower() in {"quit", "exit", "q"}:
            break
        print(f"\n{bot.name}: ", end="", flush=True)
        answer = ""
        for piece in bot.stream(q, history):
            print(piece, end="", flush=True)
            answer += piece
        print(f"\n   [{bot.used}]\n")
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]
