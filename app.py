"""
app.py - the chat web page (built with Streamlit).

Run it with:   streamlit run app.py
It opens in your browser at http://localhost:8501  (works on phones too - see README).

The look (fonts, colours, bubbles) is all in the STYLE block below - plain CSS.
"""
import base64
import hashlib
from pathlib import Path
import html
import json
import os
import re
import time

import streamlit as st

# Launch Lab (lab_page.py): shown instead of the chat when the rocket button was pressed (or ?view=lab)
if st.query_params.get("view") == "lab" and "view" not in st.session_state:
    st.session_state.view = "lab"
if st.session_state.get("view") == "lab":
    import lab_mode as _lab_mode
    if not hasattr(_lab_mode, "handle_return"):      # a server started before this update has the old module loaded
        import importlib as _il
        _lab_mode = _il.reload(_lab_mode)
    if not _lab_mode.handle_return(st):
        import runpy as _runpy
        from pathlib import Path as _P
        _runpy.run_path(str(_P(__file__).resolve().parent / "lab_page.py"), run_name="__lab__")
        st.stop()
    st.query_params.clear()
import streamlit.components.v1 as components

# On Streamlit Community Cloud, keys live in "Secrets" instead of a .env file
try:
    for k, v in st.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass

from backends import BackendError, transcribe  # noqa: E402
from bot import RocketBot, clean_question  # noqa: E402
import charts  # noqa: E402
from knowledge import load_facts  # noqa: E402
from voice_mode import stream_html, voice_mode  # noqa: E402

facts = load_facts()
R = facts["rocket"]
NAME = R["name"]
SUGGESTIONS = ["How do you fly?", "How much water, and why?", "Why don't you tumble?",
               "Show me your test results", "How do you stay safe?", "Is your design sustainable?"]
ACCENT = "#1e3a8a"   # deep aerospace navy - change this one colour to re-theme the app

_FAVICON = Path(__file__).parent / "static" / "favicon-64.png"
st.set_page_config(page_title=f"{NAME} · {R['team_name']}", page_icon=str(_FAVICON) if _FAVICON.exists() else R["emoji"],
                   layout="centered",
                   initial_sidebar_state="collapsed")

# A simple monogram logo (nose cone + fins), drawn as SVG so it stays sharp on any screen
LOGO = f"""<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<rect width="32" height="32" rx="9" fill="{ACCENT}"/>
<path d="M16 6.5c2.6 2.4 3.9 5.6 3.9 9.4v5.3h-7.8v-5.3c0-3.8 1.3-7 3.9-9.4z" fill="#fff"/>
<path d="M12.1 17.6l-2.6 3.1v2.6l2.6-1.2zM19.9 17.6l2.6 3.1v2.6l-2.6-1.2z" fill="#fff" opacity=".75"/>
<path d="M16 22.6c.9 1.3 1.4 2.2 1.4 2.9a1.4 1.4 0 0 1-2.8 0c0-.7.5-1.6 1.4-2.9z" fill="#7dd3fc"/>
</svg>"""

# ---------------- STYLE ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --accent: #1e3a8a; --accent-soft: #eef2fb; --ink: #0f172a; --muted: #64748b; --line: #e5e7eb;
        --bot-bg: #f2f3f5; }
html, body, [class*="st-"], .stMarkdown, button, input, textarea {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing: antialiased; }
/* keep Material icons working inside Streamlit widgets */
[data-testid="stIconMaterial"], .material-symbols-rounded { font-family: 'Material Symbols Rounded' !important; }

/* hide default Streamlit chrome */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], footer, #MainMenu, [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], .stDeployButton { display: none !important; }
.stApp { background: #ffffff; }
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 720px; padding-top: 84px !important; padding-bottom: 32px !important; }

/* top bar */
.topbar { position: fixed; top: 0; left: 0; right: 0; height: 60px; z-index: 999;
  background: rgba(255,255,255,.86); backdrop-filter: saturate(180%) blur(14px);
  -webkit-backdrop-filter: saturate(180%) blur(14px); border-bottom: 1px solid var(--line); }
.topbar .inner { max-width: 720px; margin: 0 auto; height: 100%; display: flex; align-items: center;
  gap: 11px; padding: 0 1.25rem; }
.topbar svg { width: 32px; height: 32px; flex: none; }
.topbar .title { font-weight: 600; font-size: 15px; color: var(--ink); letter-spacing: -.01em; line-height: 1.2; }
.topbar .sub { font-size: 12px; color: var(--muted); line-height: 1.2; margin-top: 2px; }
.topbar .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #22c55e;
  margin-right: 5px; vertical-align: 1px; }

/* settings button, pinned into the top bar */
.st-key-settings { position: fixed; top: 12px; z-index: 1000; width: auto !important;
  right: max(1.25rem, calc((100vw - 720px) / 2 + 1.25rem)); }
.st-key-settings button { border: 1px solid var(--line) !important; background: #fff !important;
  border-radius: 999px !important; height: 36px; min-height: 36px; padding: 0 14px !important;
  color: var(--ink) !important; font-size: 13px !important; font-weight: 500; box-shadow: none !important; }
.st-key-settings button:hover { background: #f8fafc !important; }
.st-key-settings button p { font-size: 13px !important; }


/* coming back from the Launch Lab: hide the Lab while the chat redraws, fade the chat in */
[data-stale="true"]:has(iframe[title*="launch_lab"]) { display: none !important; }
/* Launch Lab button (lab_page.py), pinned into the top bar (its wrapper takes no space in the page) */
[data-testid="stLayoutWrapper"]:has(> .st-key-lablink) { position: absolute; width: 0; height: 0; }
.st-key-lablink { position: fixed; top: 12px; z-index: 1000; width: auto !important;
  right: max(1.25rem, calc((100vw - 720px) / 2 + 1.25rem)); }
.st-key-lablink button { border: 1px solid var(--line); background: #fff; border-radius: 999px; height: 36px;
  padding: 0 14px 0 11px; display: flex; align-items: center; gap: 6px; text-decoration: none; }
.st-key-lablink button:hover { background: #f8fafc; }
.st-key-lablink button span, .st-key-lablink button p { color: var(--accent) !important; font-size: 13px !important; font-weight: 600; }
@media (min-width: 1100px) { .st-key-lablink { right: max(1.25rem, calc((100vw - 780px) / 2 + 1.25rem)); } }
@media (max-width: 640px) { .st-key-lablink { right: 1rem; } .st-key-lablink button { width: 36px; padding: 0; justify-content: center; }
  .st-key-lablink button p { display: none; } }

/* welcome state */
.welcome { text-align: center; padding: 7vh 0 4px; }
.welcome svg { width: 52px; height: 52px; margin-bottom: 16px;
  filter: drop-shadow(0 8px 18px rgba(30,58,138,.22)); }
.welcome .wtitle { font-size: 30px; font-weight: 700; letter-spacing: -.025em; color: var(--ink);
  margin: 0 0 8px; line-height: 1.15; }
.welcome p { color: var(--muted); font-size: 15.5px; line-height: 1.55; max-width: 440px; margin: 0 auto; }
.specs { display: flex; justify-content: center; flex-wrap: wrap; gap: 0; margin: 26px auto 6px;
  border: 1px solid var(--line); border-radius: 14px; max-width: 460px; overflow: hidden; }
.specs div { flex: 1 1 25%; padding: 12px 6px; border-left: 1px solid var(--line); min-width: 90px; }
.specs div:first-child { border-left: none; }
.specs b { display: block; font-size: 16px; font-weight: 600; color: var(--ink); letter-spacing: -.01em; }
.specs span { font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.chips-label { text-align: center; font-size: 12px; color: var(--muted); text-transform: uppercase;
  letter-spacing: .08em; margin: 10px 0 2px; font-weight: 500; }

/* message bubbles */
[class*="st-key-umsg"], [class*="st-key-bmsg"] { width: fit-content !important; max-width: 82%;
  padding: 10px 15px; gap: 0 !important; }
[class*="st-key-umsg"] { margin-left: auto; background: var(--accent); border-radius: 20px 20px 6px 20px;
  box-shadow: 0 1px 2px rgba(15,23,42,.08), 0 4px 14px rgba(30,58,138,.16); }
[class*="st-key-umsg"] p, [class*="st-key-umsg"] li { color: #fff !important; }
[class*="st-key-bmsg"] { background: var(--bot-bg); border-radius: 20px 20px 20px 6px;
  box-shadow: 0 1px 2px rgba(15,23,42,.05); }
[class*="st-key-umsg"] p, [class*="st-key-bmsg"] p, [class*="st-key-bmsg"] li {
  font-size: 15.5px; line-height: 1.5; margin-bottom: .45em; }
[class*="st-key-umsg"] p:last-child, [class*="st-key-bmsg"] p:last-child { margin-bottom: 0; }
[class*="st-key-umsg"] [data-testid="stMarkdownContainer"], [class*="st-key-bmsg"] [data-testid="stMarkdownContainer"] {
  margin-bottom: 0 !important; }
[class*="st-key-bmsg"] [data-testid="stMarkdownContainer"] { overflow-x: auto; }
[class*="st-key-bmsg"] [data-testid="stMarkdownContainer"] { color: var(--ink); }
[class*="st-key-bmsg"] table { font-size: 13px; border-collapse: collapse; background: #fff; border-radius: 10px;
  overflow: hidden; margin: 6px 0; }
[class*="st-key-bmsg"] th, [class*="st-key-bmsg"] td { border: 1px solid var(--line) !important; padding: 5px 8px !important; }
[class*="st-key-bmsg"] code { background: #fff; color: var(--accent); }
.typing { display: inline-flex; gap: 4px; padding: 6px 2px; }
.typing i { width: 7px; height: 7px; border-radius: 50%; background: #94a3b8; display: inline-block;
  animation: blink 1.2s infinite ease-in-out; }
.typing i:nth-child(2) { animation-delay: .15s } .typing i:nth-child(3) { animation-delay: .3s }
@keyframes blink { 0%,80%,100% { opacity: .3; transform: translateY(0) } 40% { opacity: 1; transform: translateY(-3px) } }

/* footer line (name + Listen) sits flush under the bot bubble */
[class*="st-key-row"] { gap: 2px !important; margin-bottom: 4px; }
[class*="st-key-row"] iframe { display: block; }

/* suggestion chips */
[class*="st-key-chips"] [data-testid="stButtonGroup"] > div, [class*="st-key-chips"] div[role="radiogroup"],
[class*="st-key-chips"] div[data-baseweb="button-group"] { justify-content: center; gap: 8px; }
[class*="st-key-chips"] button { border: 1px solid var(--line) !important; background: #fff !important;
  border-radius: 999px !important; padding: 7px 14px !important; min-height: 0 !important;
  color: #334155 !important; box-shadow: 0 1px 2px rgba(15,23,42,.04); transition: all .15s ease; }
[class*="st-key-chips"] button p { font-size: 13.5px !important; font-weight: 500; }
[class*="st-key-chips"] button:hover { border-color: #c7d2fe !important; background: var(--accent-soft) !important;
  color: var(--accent) !important; }
.st-key-chips-wrap { margin-top: 6px; }
.st-key-chips-row { margin-top: 10px; }
[class*="st-key-bmsg"]:has(table) { max-width: 100%; min-width: 0; }
/* a bubble with a chart (charts.py) takes the full width so the chart stays readable on phones */
[class*="st-key-bmsg"]:has([class*="st-key-chart"]) { width: 100% !important; max-width: 100% !important; min-width: 0; }
[class*="st-key-chart"] { width: 100%; margin-top: 6px; gap: .3rem !important; }
[class*="st-key-chart"] [data-testid="stVerticalBlock"] { gap: .3rem !important; }
[class*="st-key-chart"] [data-baseweb="tab-list"] { gap: 4px; overflow-x: auto; scrollbar-width: none; }
[class*="st-key-chart"] [data-baseweb="tab"] p { font-size: 13px; }
[class*="st-key-chart"] [data-testid="stCaptionContainer"] p { font-size: 11.5px; color: var(--muted); margin: 0 0 4px; }
[class*="st-key-chart"] [data-testid="stVegaLiteChart"] { max-width: 100%; overflow: hidden; }
/* wide tables (test results) scroll sideways INSIDE the bubble instead of being cut off on phones */
[class*="st-key-bmsg"] [data-testid="stMarkdownContainer"] { max-width: 100%; min-width: 0; }
[class*="st-key-bmsg"] table { display: block; max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch;
  width: max-content; }
[class*="st-key-bmsg"] th { white-space: nowrap; }
@media (max-width: 640px) { [class*="st-key-bmsg"] td { white-space: nowrap; } }   /* phones: one line per row, swipe sideways */
/* keyboard users can see where they are */
button:focus-visible, a:focus-visible, [role="button"]:focus-visible {
  outline: 2px solid #2563eb !important; outline-offset: 2px; }
[class*="st-key-bmsg"] [data-testid="stMarkdownContainer"] { padding-bottom: 2px; }

/* bottom input bar */
[data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] { background: #fff !important; }
[data-testid="stBottomBlockContainer"] { max-width: 720px; padding: 10px 1.25rem 22px !important; }
[data-testid="stChatInput"] { border: 1px solid #d9dde3 !important; border-radius: 26px !important;
  background: #fff !important; box-shadow: 0 2px 6px rgba(15,23,42,.05), 0 8px 24px rgba(15,23,42,.06) !important; }
[data-testid="stChatInput"] > div { background: transparent !important; border: none !important; }
[data-testid="stChatInput"]:focus-within { border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(30,58,138,.12), 0 8px 24px rgba(15,23,42,.06) !important; }
[data-testid="stChatInput"] textarea { font-size: 16px !important; }
[data-testid="stChatInputSubmitButton"] { background: var(--accent) !important; color: #fff !important;
  border-radius: 50% !important; }
[data-testid="stChatInputSubmitButton"]:disabled { background: #cbd5e1 !important; }
.footnote { text-align: center; font-size: 11.5px; color: #94a3b8; margin-top: 8px; }

/* spinner + alerts */
[data-testid="stAlert"] { border-radius: 14px; }

/* laptops & projectors: a touch larger so it reads from the back of the room */
@media (min-width: 1100px) {
  .block-container, [data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"],
  .topbar .inner { max-width: 780px; }
  .st-key-settings { right: max(1.25rem, calc((100vw - 780px) / 2 + 1.25rem)); }
  [class*="st-key-umsg"] p, [class*="st-key-bmsg"] p, [class*="st-key-bmsg"] li { font-size: 16.5px; }
  [class*="st-key-bmsg"] table { font-size: 14px; }
  .topbar .title { font-size: 16px; }
  .welcome .wtitle { font-size: 34px; }
  .welcome p { font-size: 16.5px; max-width: 480px; }
  [class*="st-key-chips"] button p { font-size: 14px !important; }
}
@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding-left: 1rem !important; padding-right: 1rem !important;
     padding-top: 76px !important; }
  .topbar .inner { padding: 0 1rem; }
  .st-key-settings { right: 1rem; }
  .welcome { padding-top: 28px; }   /* keeps the logo clear of the fixed top bar on phones */
  .welcome svg { width: 44px; height: 44px; margin-bottom: 12px; }
  .welcome .wtitle { font-size: 25px; }
  .welcome p { font-size: 15px; }
  .specs { margin-top: 20px; }
  [class*="st-key-umsg"], [class*="st-key-bmsg"] { max-width: 88%; }
  [data-testid="stBottomBlockContainer"] { padding: 8px .8rem 14px !important; }
  .specs div { min-width: 0; padding: 10px 4px; }
  .specs b { font-size: 15px; }
  .specs span { font-size: 10.5px; }
  [class*="st-key-bmsg"] table { font-size: 12px; }
  [class*="st-key-bmsg"] th, [class*="st-key-bmsg"] td { padding: 4px 6px !important; }
  /* during a chat, chips become one swipeable row */
  .st-key-chips-row [data-testid="stButtonGroup"] > div, .st-key-chips-row div[data-baseweb="button-group"] {
    flex-wrap: nowrap !important; overflow-x: auto; justify-content: flex-start !important;
    scrollbar-width: none; -webkit-overflow-scrolling: touch; padding-bottom: 2px; }
  .st-key-chips-row div::-webkit-scrollbar { display: none; }
  .st-key-chips-row button { flex: none; white-space: nowrap; }
  /* phones: less packed - welcome chips as a tidy 2-column grid, more air between sections */
  .welcome { padding-top: 36px; }
  .welcome p { line-height: 1.55; margin-bottom: 4px; }
  .specs { margin-top: 26px; margin-bottom: 8px; }
  .st-key-chips-wrap { margin-top: 18px; }
  .st-key-chips-wrap [data-testid="stButtonGroup"] > div, .st-key-chips-wrap div[data-baseweb="button-group"] {
    display: grid !important; grid-template-columns: 1fr 1fr; gap: 10px !important; }
  .st-key-chips-wrap button { width: 100% !important; justify-content: center; padding: 10px 8px !important; min-height: 46px !important; }
  .st-key-chips-wrap button p { font-size: 13px !important; white-space: normal; line-height: 1.25; }
  [data-testid="stBottomBlockContainer"] { padding: 10px .9rem 20px !important; }
}
</style>""", unsafe_allow_html=True)

# ---------------- top bar ----------------
st.markdown(f"""<div class="topbar"><div class="inner">{LOGO}
<div><div class="title">{html.escape(NAME)}</div>
<div class="sub"><span class="dot"></span>{html.escape(R['team_name'])} · Water rocket assistant</div></div>
</div></div>""", unsafe_allow_html=True)
with st.container(key="lablink"):   # Launch Lab (lab_page.py) - rocket button in the top bar
    st.button("Launch Lab", icon=":material/rocket_launch:", key="lab_open",
              on_click=lambda: st.session_state.update(view="lab"))   # one run straight into the Lab

if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------- AI brain: always automatic (best available: Groq, then Gemini, then offline) ----------------
read_aloud = False
bot = RocketBot(backend=None)

# ---------------- voice mode bridge (invisible; see voice_mode.py) ----------------
# The water-drop button next to the chat box opens a full-screen, hands-free voice conversation.
with st.container(key="voicebridge"):
    voice_slot = st.empty()        # hidden box the voice screen reads the streaming answer from
    voice_q = voice_mode(NAME, team=R.get("team_name", ""), can_transcribe=bool(os.getenv("GROQ_API_KEY", "").strip()
                                                    or os.getenv("GEMINI_API_KEY", "").strip()))
voice_slot.markdown(stream_html(st.session_state.get("voice_last")), unsafe_allow_html=True)


@st.cache_resource
def _listen_jobs():
    """mp3s being made for the Listen buttons (shared by every visitor; made once per answer)."""
    from concurrent.futures import ThreadPoolExecutor
    return {"pool": ThreadPoolExecutor(max_workers=2), "busy": set()}


def listen_mp3(text: str) -> str:
    """URL of this answer read by the natural server voice (tts.py), made in the background the first time.
    Saved as static/tts/<hash>.mp3 (served at app/static/tts/...). The whole answer is made in ONE go so it
    flows naturally. The Listen button falls back to the browser voice if the file isn't ready / can't be made."""
    import tts
    spoken = tts.pronounce(tts.speakable(text))
    engine = f"kokoro:{tts.KOKORO_VOICE}:{tts.KOKORO_SPEED}" if tts.kokoro_ready() else "edge"
    tag = hashlib.md5(f"{spoken}|{tts.VOICES}|{tts.RATE}|{engine}".encode()).hexdigest()[:16]
    folder = Path(__file__).parent / "static" / "tts"
    path = folder / f"{tag}.mp3"
    jobs = _listen_jobs()
    if spoken and not path.exists() and tag not in jobs["busy"]:
        jobs["busy"].add(tag)

        def make():
            try:
                data = tts.speak_mp3(text)
                if data:
                    folder.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".part")
                    tmp.write_bytes(data)
                    tmp.replace(path)
                    old = sorted(folder.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
                    for p in old[:-300]:       # keep the folder small
                        p.unlink(missing_ok=True)
            finally:
                jobs["busy"].discard(tag)
        jobs["pool"].submit(make)
    return f"app/static/tts/{tag}.mp3"


def speak_button(text: str, autoplay: bool, meta: str = ""):
    """A small 'Listen' button that reads the answer with the natural server voice (same as voice mode),
    or the browser's own voice if the server voice isn't available."""
    audio_url = listen_mp3(text)
    clean = re.sub(r"[*_`#|>\[\]()]|🔎.*|\(📡.*", " ", text)
    clean = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", clean)
    lang = "ar" if re.search(r"[\u0600-\u06FF]", clean) else "en-US"
    components.html(f"""
    <style>
      html,body {{ margin:0; background:transparent; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; }}
      button {{ display:inline-flex; align-items:center; gap:5px; border:none; background:transparent;
        color:#475569; font: 500 12px 'Inter',-apple-system,BlinkMacSystemFont,sans-serif; padding:4px 6px;
        border-radius:8px; cursor:pointer; }}
      button:hover {{ background:#f1f5f9; color:#1e3a8a; }}
      svg {{ width:14px; height:14px; }}
      .row {{ display:flex; align-items:center; gap:4px; padding-left:8px; }}
      .meta {{ font: 400 12px 'Inter',-apple-system,BlinkMacSystemFont,sans-serif; color:#94a3b8; }}
      .sep {{ color:#cbd5e1; font-size:12px; }}
    </style>
    <div class="row"><span class="meta">{html.escape(meta)}</span><span class="sep">·</span><button id="b"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/>
      <path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a10 10 0 0 1 0 14"/></svg><span id="t">Listen</span></button></div>
    <script>
      const text = {json.dumps(clean)};
      const t = document.getElementById("t");
      try {{ window.frameElement.title = "Listen to this answer"; }} catch (e) {{}}
      function synth() {{ try {{ return window.parent.speechSynthesis; }} catch (e) {{ return window.speechSynthesis; }} }}
      const src = new URL({json.dumps(audio_url)}, document.baseURI).href;
      let player = null, busy = false;
      function browserVoice() {{     // last resort: the browser's own (robotic) voice
        const s = synth();
        const u = new SpeechSynthesisUtterance(text); u.lang = "{lang}"; u.rate = 1.05;
        u.onend = () => t.textContent = "Listen"; t.textContent = "Stop"; s.speak(u);
      }}
      function say() {{
        const s = synth();
        if (busy || (player && !player.paused) || s.speaking) {{
          busy = false; if (player) player.pause(); s.cancel(); t.textContent = "Listen"; return;
        }}
        busy = true; t.textContent = "Stop";
        player = new Audio(); player.preload = "auto";
        player.onended = () => {{ busy = false; t.textContent = "Listen"; }};
        player.onplaying = () => {{ if (busy) t.textContent = "Stop"; }};
        const t0 = Date.now();
        const tryPlay = () => {{     // the mp3 may still be being made (~1-3 s after the answer): retry briefly
          if (!busy) return;
          player.src = src + "?t=" + Date.now();
          player.play().catch(() => {{ if (!busy) return;
            t.textContent = "Loading…";
            if (Date.now() - t0 < 15000) setTimeout(tryPlay, 600); else {{ busy = false; browserVoice(); }} }});
        }};
        player.onerror = null;
        tryPlay();
      }}
      document.getElementById("b").onclick = say;
      if ({str(autoplay).lower()}) {{ try {{ say(); }} catch (e) {{}} }}
    </script>""", height=30)


# ---------------- the conversation ----------------
msgs = st.session_state.messages
hero = st.empty()          # welcome screen (only while the chat is empty)
convo = st.container()     # chat bubbles go in here
chips_slot = st.empty()    # suggestion chips sit below the chat

if not msgs:
    d, L, best = facts["design"], facts["launch"], facts["best_result"]
    hero.markdown(f"""<div class="welcome">{LOGO}
<div class="wtitle">Hi, I'm {html.escape(NAME)}.</div>
<p>{html.escape(R['team_name'])}'s water rocket. Ask me how I fly, what I'm made of, how my test launches went,
or how we keep everyone safe. Type, tap the mic, or tap the water-drop button to talk to me hands-free.</p>
<div class="specs"><div><b>{d['total_length_cm']} cm</b><span>Length</span></div>
<div><b>{L['water_volume_ml']} mL</b><span>Water</span></div>
<div><b>{L['launch_pressure_psi']} psi</b><span>Pressure</span></div>
<div><b>{best['distance_m']} m</b><span>Best flight</span></div></div>
</div>""", unsafe_allow_html=True)

autoplay_idx = st.session_state.pop("autoplay_idx", None)
with convo:
    for i, m in enumerate(msgs):
        if m["role"] == "user":
            with st.container(key=f"umsg{i}"):
                st.markdown(m["content"])
        else:
            with st.container(key=f"row{i}"):
                with st.container(key=f"bmsg{i}"):
                    st.markdown(m["content"])
                    if m.get("chart"):
                        charts.render(m["chart"], key=str(i))
                speak_button(m["content"], autoplay=(read_aloud and autoplay_idx == i),
                             meta=f"{NAME} · via {m.get('brain', '?')}")

# suggestion chips (tap one to ask it)
with chips_slot.container(key="chips-wrap" if not msgs else "chips-row"):
    if not msgs:
        st.markdown('<div class="chips-label">Try asking</div>', unsafe_allow_html=True)
    chip = st.pills("Try asking", SUGGESTIONS, key=f"chips{len(msgs)}", label_visibility="collapsed")

# submit_mode="disable": the box is locked while the rocket is answering, so no question gets lost
prompt = st.chat_input(f"Message {NAME}", accept_audio=True, submit_mode="disable", max_chars=500)

question = None
voice_id = None      # set when the question came from voice mode
if isinstance(voice_q, dict) and voice_q.get("id") and voice_q["id"] != st.session_state.get("voice_seen"):
    st.session_state.voice_seen = voice_id = voice_q["id"]
    if voice_q.get("audio"):       # browser without speech recognition: transcribe on the server
        import base64
        mime = voice_q.get("mime", "audio/webm")
        try:
            question = transcribe(base64.b64decode(voice_q["audio"]), "voice." + mime.split("/")[-1], mime,
                                  voice_q.get("lang") or "auto")
            err = "" if question else "I didn't catch that - try again?"
        except BackendError as e:
            question, err = None, f"I couldn't hear that ({e})."
        if err:
            st.session_state.voice_last = {"id": voice_id, "done": True, "err": err}
            voice_slot.markdown(stream_html(st.session_state.voice_last), unsafe_allow_html=True)
        else:   # show "You: ..." straight away, while the answer is still being thought up
            voice_slot.markdown(stream_html({"id": voice_id, "heard": question}), unsafe_allow_html=True)
    elif voice_q.get("tts"):       # iPhone backup voice: turn text we already showed into mp3s, one per sentence
        from tts import SentenceVoicer
        voicer, shown = SentenceVoicer(), -1
        voicer.feed(voice_q["tts"], final=True)
        while True:                # hand over each sentence's mp3 the moment it's ready
            clips, done = voicer.ready(), voicer.all_done()
            if len(clips) != shown or done:
                shown = len(clips)
                st.session_state.voice_last = {"id": voice_id, "text": voice_q["tts"], "done": done, "clips": clips}
                voice_slot.markdown(stream_html(st.session_state.voice_last), unsafe_allow_html=True)
            if done:
                break
            time.sleep(0.05)
    else:
        question = (voice_q.get("text") or "").strip()
# typed / tapped questions wait in a small queue, so two quick chip taps don't lose the first question
# (the 2nd tap reruns the page while the 1st answer is still streaming; the 1st stays queued and is answered first)
queue = st.session_state.setdefault("pending", [])
from_queue = False
if voice_id:
    pass                 # voice question handled above
else:
    if chip and st.session_state.get("chip_seen") != (len(msgs), chip):
        st.session_state.chip_seen = (len(msgs), chip)
        queue.append(chip)
    if prompt:
        typed = None
        if prompt.audio is not None:
            audio = prompt.audio.getvalue()
            tag = hashlib.md5(audio).hexdigest()
            if st.session_state.get("last_audio") != tag:       # don't transcribe the same clip twice
                st.session_state.last_audio = tag
                with st.spinner("Listening..."):
                    try:
                        typed = clean_question(transcribe(audio, "voice.wav", "audio/wav"))
                    except BackendError as e:
                        st.warning(f"Voice didn't work: {e}. You can type instead.")
        typed = typed or clean_question(prompt.text)     # blank / spaces-only messages are ignored (no empty bubble)
        if typed:
            queue.append(typed)
    if queue:
        question, from_queue = queue[0], True

if question:
    hero.empty()
    chips_slot.empty()
    n = len(msgs)
    with convo:
        with st.container(key=f"umsg{n}"):
            st.markdown(question)
        with st.container(key=f"row{n + 1}"):
            with st.container(key=f"bmsg{n + 1}"):
                box = st.empty()
                box.markdown('<div class="typing"><i></i><i></i><i></i></div>', unsafe_allow_html=True)
                pieces = bot.stream(question, msgs, voice=bool(voice_id))
                voicer = None
                if voice_id and voice_q.get("server_tts"):   # iPhone whose browser voice is silent
                    from tts import SentenceVoicer
                    voicer = SentenceVoicer()
                first = next(pieces, "")          # wait for the first piece while the dots bounce

                def all_pieces():
                    if not voice_id:
                        yield first
                        yield from pieces
                        return
                    # voice mode: also copy the answer into the hidden box (a few times a second)
                    # so the voice screen can start speaking the first sentence straight away
                    so_far, last = first or "", 0.0
                    if voicer:
                        voicer.feed(so_far)
                    voice_slot.markdown(stream_html({"id": voice_id, "text": so_far, "heard": question}),
                                        unsafe_allow_html=True)
                    yield first
                    for piece in pieces:
                        so_far += piece
                        if voicer:
                            voicer.feed(so_far)     # each finished sentence starts its own mp3 right away
                        if time.time() - last > 0.15 or any(c in piece for c in ".!?\n"):
                            last = time.time()
                            voice_slot.markdown(stream_html({"id": voice_id, "text": so_far, "heard": question,
                                                             "clips": voicer.ready() if voicer else None}),
                                                unsafe_allow_html=True)
                        yield piece

                answer = box.write_stream(all_pieces())
                if bot.chart:
                    charts.render(bot.chart, key=f"{n + 1}")
            if not isinstance(answer, str):
                answer = "".join(map(str, answer))
    st.session_state.messages += [{"role": "user", "content": question},
                                  {"role": "assistant", "content": answer, "brain": bot.used,
                                   "chart": bot.chart}]
    if from_queue and queue and queue[0] == question:
        queue.pop(0)               # answered; anything still queued is answered after the redraw below
    if voice_id:      # tell the voice screen the answer is complete (it speaks it; no Listen autoplay)
        st.session_state.voice_last = {"id": voice_id, "text": answer, "heard": question, "done": True}
        if voicer:   # iPhone server voice: keep handing over sentence mp3s until the last one is ready
            voicer.feed(answer, final=True)
            shown = -1
            while not voicer.all_done():
                clips = voicer.ready()
                if len(clips) != shown:
                    shown = len(clips)
                    voice_slot.markdown(stream_html({"id": voice_id, "text": answer, "heard": question, "clips": clips}),
                                        unsafe_allow_html=True)
                time.sleep(0.05)
            st.session_state.voice_last["clips"] = voicer.ready()
        voice_slot.markdown(stream_html(st.session_state.voice_last), unsafe_allow_html=True)
        time.sleep(0.3)   # let the browser read the final box before the page redraws
    else:
        st.session_state.autoplay_idx = n + 1
    if not (voice_id and voice_q.get("ios")):
        st.rerun()                  # redraw: bubble footer, Listen button and fresh chips
    # (iPhone voice mode covers the page, so skip that full redraw - less work while the phone is talking;
    #  voice.js asks for one redraw when you close voice mode, so the chat page catches up then)
