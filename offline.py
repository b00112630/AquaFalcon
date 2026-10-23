"""
offline.py - the "no internet, no API key" backup brain.

It doesn't understand language like an AI does. It looks for keywords in the
question, picks the best-matching topic, and builds an answer straight from
rocket_info.yaml and physics.md.  Simple, but it never makes facts up and it
keeps the live demo alive if the Wi-Fi dies.
"""
import difflib
import random
import re

from knowledge import derived_facts, is_unknown, load_facts, physics_sections, test_angles

rng = random.Random()

# topic -> keywords that point to it (more matches = better score)
TOPICS = {
    "greeting":      ["hi", "hello", "hey", "salam", "marhaba", "hola", "yo", "sup", "مرحبا", "هلا", "السلام"],
    "identity":      ["who are you", "your name", "what are you", "called", "introduce"],
    "team":          ["team", "members", "who built", "who made", "who designed", "teammates", "group", "roles"],
    "how_it_works":  ["how does", "work", "works", "newton", "third law", "thrust", "action", "reaction", "launch work", "propel", "fly"],
    "pressure":      ["pressure", "psi", "bar", "pump", "pumped", "pressurise", "pressurize"],
    "water":         ["water", "volume", "ml", "how much water", "litre", "liter", "fill", "full"],
    "stability":     ["stability", "stable", "cg", "cp", "centre of gravity", "center of gravity",
                      "centre of pressure", "center of pressure", "wobble", "tumble", "straight", "swing test"],
    "projectile":    ["projectile", "trajectory", "angle", "parabola", "range", "path", "45", "degrees", "gravity", "arc"],
    "design":        ["design", "nose", "cone", "fins", "fin", "length", "long", "mass", "weight", "heavy", "shape", "look like", "built", "bottle"],
    "materials":     ["materials", "material", "made of", "made from", "build it", "tape", "glue", "cardboard", "المواد", "مواد"],
    "tests":         ["test", "tests", "testing", "results", "data", "how far", "distance", "best", "record", "flights", "furthest", "farthest",
                      "how far can you fly", "how far did it go", "how far did you go", "how far did you fly", "مسافة", "قديش بعيد"],
    "competition":   ["competition", "the competition", "at the competition", "contest", "official", "final", "placed", "placement", "rank", "november 15", "launch day"],
    "safety":        ["safety", "safe", "keep people safe", "danger", "dangerous", "goggles", "explode", "burst", "risk", "precaution", "distance away"],
    "sustainability":["sustainability", "sustainable", "environment", "eco", "green", "recycle", "recycled", "reuse", "waste", "plastic", "emissions"],
    "drag":          ["drag", "air resistance", "aerodynamic", "streamlined"],
    "energy":        ["energy", "kinetic", "potential", "work done"],
    # questions about team facts that are NOT in rocket_info.yaml -> honest "I don't know"
    "not_recorded":  ["cost", "costs", "money", "spend", "spent", "budget", "price", "aed", "dirhams",
                      "altitude", "height", "how high", "ارتفاع", "ارتفع", "flight time", "how long in the air", "speed", "how fast"],
    "process":       ["design process", "engineering process", "steps", "iterate", "improve", "improvement"],
}

# words that mean "this is about the rocket/project" - used to tell
# "a team question I can't answer" apart from "totally off-topic"
ON_TOPIC_HINTS = ["rocket", "rockets", "team", "bottle", "launch", "fly", "flight", "project", "ngn", "chatbot"]

# when two topics tie, the one earlier in this list wins (the more specific topic)
PRIORITY = ["competition", "not_recorded", "safety", "sustainability", "stability", "water", "pressure",
            "projectile", "materials", "tests", "team", "design", "drag", "energy", "process",
            "how_it_works", "identity", "greeting"]


def _clean(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9\u0600-\u06FF ]+", " ", text.lower()) + " "


# ---- typo tolerance: people type fast ("how for a can you fight" = "how far can you fly")
# common slips first (whole words / phrases), then any unknown word is swapped for the closest known keyword
TYPOS = {"how for": "how far", "how fat": "how far", "fight": "fly", "flie": "fly", "fli": "fly", "flys": "fly",
         "hight": "height", "heigth": "height", "hieght": "height", "rocekt": "rocket", "rokit": "rocket",
         "roket": "rocket", "materails": "materials", "matrials": "materials", "presure": "pressure",
         "pressur": "pressure", "saftey": "safety", "safty": "safety", "distence": "distance", "desgin": "design",
         "watter": "water", "fines": "fins", "resluts": "results", "reslts": "results", "tset": "test"}
STOP = {"what", "when", "where", "which", "while", "with", "your", "yours", "about", "there", "their", "they",
        "this", "that", "these", "those", "have", "does", "doing", "done", "would", "could", "should", "tell",
        "much", "many", "more", "most", "some", "very", "really", "please", "thanks", "thank", "okay", "from",
        "into", "just", "like", "know", "want", "need", "make", "good", "best", "were", "will", "then", "than"}


def _vocab() -> set:
    words = set()
    for kws in list(TOPICS.values()) + [ON_TOPIC_HINTS]:
        for k in kws:
            words.update(w for w in k.split() if len(w) >= 3)
    return words


def fix_typos(question: str) -> str:
    """Correct obvious typos so near-miss questions still find their topic."""
    q = _clean(question)
    for wrong, right in TYPOS.items():
        q = q.replace(f" {wrong} ", f" {right} ")
    vocab = _vocab()
    out = []
    for w in q.split():
        if len(w) >= 4 and w not in vocab and w not in STOP and not re.search(r"[\u0600-\u06FF\d]", w):
            close = difflib.get_close_matches(w, vocab, n=1, cutoff=0.8)
            w = close[0] if close else w
        out.append(w)
    return " ".join(out)


def score_topics(question: str) -> list:
    q = _clean(question)
    scores = []
    for topic, words in TOPICS.items():
        s = sum(len(w.split()) for w in words if f" {w} " in q)   # multi-word phrases count more
        if s:
            scores.append((s, topic))
    scores.sort(key=lambda x: (-x[0], PRIORITY.index(x[1])))
    return scores


def _faq_match(question: str, faq: list):
    q = set(_clean(question).split())
    best, best_overlap = None, 0
    for item in faq or []:
        words = {w for w in _clean(item["q"]).split() if len(w) > 3}
        overlap = len(q & words)
        if overlap > best_overlap:
            best, best_overlap = item, overlap
    return best if best_overlap >= 2 else None


def answer(question: str) -> str:
    f = load_facts()
    r = f["rocket"]
    name = r["name"]
    phys = physics_sections()
    hype = rng.choice(["Ooh, good one!", "Love this question!", "Great question!", "Ahh, my favourite topic!", "Let's go!"])

    question = fix_typos(question)
    faq = _faq_match(question, f.get("faq"))
    if faq:
        return f"{hype} 🙌 {faq['a']}"

    scores = score_topics(question)
    if not scores:
        q = _clean(question)
        hints = ON_TOPIC_HINTS + [name.lower()]
        if any(f" {w} " in q for w in hints):
            return (f"Hmm, honest answer: I don't have that in my team notes yet 🤔 "
                    f"I'd rather say I don't know than make something up! "
                    f"Ask the team, or try asking about my design, test results, safety or physics.")
        return (f"Haha, that's outside my flight path! 🛰️ I'm {name}, and I only know about our water rocket. "
                f"Try: *How do you fly?*, *What were your test results?* or *How do you keep people safe?*")

    topic = scores[0][1]
    d, L = f["design"], f["launch"]

    if topic == "greeting":
        return f"Hi! 👋 I'm **{name}**, {r['team_name']}'s water rocket. {r['tagline']} Ask me anything about how I fly, my design, or my test results! {r['emoji']}"
    if topic == "identity":
        return (f"I'm **{name}** {r['emoji']} - a water rocket built by {r['team_name']} for {r['course']}. "
                f"I'm also a chatbot, so you can ask me about my physics, design, tests, safety and sustainability!")
    if topic == "team":
        people = "\n".join(f"- **{m['name']}**: {m['role']}" for m in f["team_members"])
        return f"Meet my crew! 👩‍🚀👨‍🚀\n\n{people}"
    if topic == "how_it_works":
        return (f"{hype} 💧 I'm powered by **Newton's Third Law**. We pump air into my bottle until the pressure is high "
                f"(about {L['launch_pressure_psi']} psi). When I'm released, that air shoves the water out of my nozzle downward "
                f"super fast - that's the *action*. The water pushes me up and forward - the *reaction*, called **thrust**. "
                f"Thrust only lasts a split second, then I coast through the air like a thrown ball. 🚀")
    if topic == "pressure":
        return (f"Pressure is my fuel tank! ⛽ {phys['Pressure']}\n\n"
                f"Test pressure: **{L['launch_pressure_psi']} psi**. {L['launch_pressure_note']}.")
    if topic == "water":
        return (f"We fill me with **{L['water_volume_ml']} mL** of water - {L['water_fraction']}. 💦 "
                f"{L['best_water_volume_reason']}")
    if topic == "stability":
        return (f"Staying straight is everything! 🎯 {d['stability']}.\n\n{phys['Stability: centre of gravity (CG) and centre of pressure (CP)']}")
    if topic == "projectile":
        angles = test_angles()
        why = (f" All our test launches used {angles[0]} degrees, so we picked it from the physics below "
               f"(best range in theory); we haven't compared different angles yet." if len(angles) == 1 else "")
        return (f"After the water runs out I become a projectile! 🏹 We launch at **{L['launch_angle_deg']} degrees**.{why}\n\n"
                f"{phys['Projectile motion']}")
    if topic == "design":
        return (f"Here's my look! 😎\n\n- **Body:** {d['bottle']}\n- **Length:** {d['total_length_cm']} cm (rule: under 50 cm)\n"
                f"- **Dry mass:** {d['dry_mass_g']} g\n- **Nose cone:** {d['nose_cone']}\n- **Fins:** {d['fins']} ({d['fin_size']})\n\n"
                f"Why? {d['why_this_design']}.")
    if topic == "materials":
        mats = "\n".join(f"- {m}" for m in f["materials"])
        return f"I'm made of pretty humble stuff! ♻️\n\n{mats}"
    if topic == "not_recorded" and re.search(r"height|high|altitude|ارتف", _clean(question)):
        h = derived_facts().get("theoretical_max_height_m")
        wants_theory = re.search(r"estimat|theor|calculat|roughly|approx|physics|predict", question.lower())
        if not (wants_theory and h):
            return ("Honest answer: we didn't measure my height, so I won't guess a number! 📏 "
                    "Our measured result is distance: the best flight was "
                    f"**{f['best_result']['distance_m']} m**. Ask me for a physics estimate of the height if you like.")
        return ("We didn't measure my height, so this is physics, not data! 📏"
                + (f" If you want the theory: for our best flight at 45 degrees, no-drag physics gives a maximum of "
                   f"about **{h} m** (height = range / 4). That's a *theoretical estimate*, not a measurement, and the "
                   f"real height was lower because of drag." if h else ""))
    if topic == "not_recorded":
        return (f"Honest answer: that isn't recorded in my team notes yet 🤔 and I'd rather say "
                f"I don't know than make up a number! The team hasn't added it yet. "
                f"Meanwhile, ask me about my design, test results, safety or physics.")
    if topic == "competition":
        c = f["competition"]
        if is_unknown(c.get("result_distance_m")):
            return (f"The competition is on **{c['date']}** 🏁 and I don't have the official result recorded yet, "
                    f"so I won't guess! Our best *test* flight was **{f['best_result']['distance_m']} m** "
                    f"({f['best_result']['settings']}). The minimum to qualify is {c['minimum_distance_m']} m.")
        return f"At the competition I flew **{c['result_distance_m']} m** and placed **{c['placement']}**! 🏆"
    if topic == "tests":
        rows = "\n".join(f"| {t['test']} | {t['water_ml']} | {t['pressure_psi']} | {t['angle_deg']} | {t['distance_m']} | {t['notes']} |"
                         for t in f["test_results"])
        return (f"Here's my flight log! 📊\n\n| Test | Water (mL) | Pressure (psi) | Angle (deg) | Distance (m) | Notes |\n"
                f"|---|---|---|---|---|---|\n{rows}\n\n"
                f"🥇 Best: **{f['best_result']['distance_m']} m** with {f['best_result']['settings']}.")
    if topic == "safety":
        rules = "\n".join(f"- {s}" for s in f["safety"])
        return f"Safety first, always! 🥽\n\n{rules}"
    if topic == "sustainability":
        items = "\n".join(f"- {s}" for s in f["sustainability"])
        return f"I'm a pretty green rocket 🌱\n\n{items}"
    if topic == "drag":
        return f"Air is sneaky! 💨 {phys['Drag (air resistance)']}"
    if topic == "energy":
        return f"Energy story time ⚡ {phys['Energy']}"
    if topic == "process":
        return f"Engineering is a loop, not a straight line! 🔁 {phys['Engineering design process']}"
    return "I'm not sure about that one yet! 🤔"
