"""
pages/launch_lab.py - the Launch Lab: an interactive water-rocket flight simulator (a separate page, so the
chat page stays exactly as it is). Opened from the small rocket button in the chat's top bar.

  * lab_mode.py + lab_component/   the page itself (HTML + JS, no build step): sliders, animated flight, charts
  * lab_component/physics.js and launchlab.py   the same flight model in JavaScript and Python
  * "Ask ... why" puts a question with the setup (re-computed here in Python) into the chat's normal
    question queue and goes back to the chat, which answers it like any typed question.
"""
import html
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import launchlab  # noqa: E402
from lab_mode import launch_lab  # noqa: E402
from knowledge import load_facts  # noqa: E402

facts = load_facts()
R = facts["rocket"]
NAME = R["name"]
_FAVICON = ROOT / "static" / "favicon-64.png"
st.set_page_config(page_title=f"Launch Lab · {NAME}", page_icon=str(_FAVICON) if _FAVICON.exists() else R["emoji"],
                   layout="wide", initial_sidebar_state="collapsed")

ACCENT = "#1e3a8a"   # same navy as the chat page (app.py) - the Lab uses the chat page's look on purpose
# the chat page's logo (app.py LOGO), so both pages share one top bar
LOGO = f"""<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<rect width="32" height="32" rx="9" fill="{ACCENT}"/>
<path d="M16 6.5c2.6 2.4 3.9 5.6 3.9 9.4v5.3h-7.8v-5.3c0-3.8 1.3-7 3.9-9.4z" fill="#fff"/>
<path d="M12.1 17.6l-2.6 3.1v2.6l2.6-1.2zM19.9 17.6l2.6 3.1v2.6l-2.6-1.2z" fill="#fff" opacity=".75"/>
<path d="M16 22.6c.9 1.3 1.4 2.2 1.4 2.9a1.4 1.4 0 0 1-2.8 0c0-.7.5-1.6 1.4-2.9z" fill="#7dd3fc"/>
</svg>"""

# same values as the chat page's STYLE block (white page, navy ink, Inter, frosted top bar)
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --accent: #1e3a8a; --ink: #0f172a; --muted: #64748b; --line: #e5e7eb; }
html, body, [class*="st-"], .stMarkdown { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing: antialiased; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
footer, #MainMenu, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], .stDeployButton { display: none !important; }
.stApp { background: #ffffff !important; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1120px; padding: 74px 1.25rem 28px !important; }
@media (max-width: 640px) { .block-container, [data-testid="stMainBlockContainer"] { padding: 70px .6rem 20px !important; } }
.topbar { position: fixed; top: 0; left: 0; right: 0; height: 60px; z-index: 999;
  background: rgba(255,255,255,.86); backdrop-filter: saturate(180%) blur(14px);
  -webkit-backdrop-filter: saturate(180%) blur(14px); border-bottom: 1px solid var(--line); }
.topbar .inner { max-width: 1120px; margin: 0 auto; height: 100%; display: flex; align-items: center;
  gap: 11px; padding: 0 1.25rem; }
.topbar svg { width: 32px; height: 32px; flex: none; }
.topbar .title { font-weight: 600; font-size: 15px; color: var(--ink); letter-spacing: -.01em; line-height: 1.2; }
.topbar .sub { font-size: 12px; color: var(--muted); line-height: 1.2; margin-top: 2px; }
.topbar .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #22c55e;
  margin-right: 5px; vertical-align: 1px; }
@media (min-width: 1100px) { .topbar .title { font-size: 16px; } }
iframe { color-scheme: light; }
/* the style + top-bar blocks take no room, so no gap above the Lab */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"],
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] { gap: 0 !important; }
</style>""", unsafe_allow_html=True)
st.markdown(f"""<div class="topbar"><div class="inner">{LOGO}
<div><div class="title">{html.escape(NAME)}</div>
<div class="sub"><span class="dot"></span>{html.escape(R.get('team_name', ''))} · Water rocket assistant</div></div>
</div></div>""", unsafe_allow_html=True)


def main_page() -> str:
    """The chat page's file name (app.py locally, streamlit_app.py on Streamlit Cloud)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return Path(get_script_run_ctx().main_script_path).name
    except Exception:
        return "app.py"


value = launch_lab(NAME, team=R.get("team_name", ""), defaults=launchlab.params_from_facts(facts),
                   saved=st.session_state.get("lab_params"))

if isinstance(value, dict) and value.get("id") and value["id"] != st.session_state.get("lab_seen"):
    st.session_state.lab_seen = value["id"]
    params = launchlab.clean(value.get("params"))
    st.session_state.lab_params = params
    if value.get("action") == "ask":
        # the chat page answers everything in this queue on its next run (same as a typed question)
        st.session_state.setdefault("pending", []).append(launchlab.ask_text(params))
    st.switch_page(main_page())
