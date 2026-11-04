"""
lab_mode.py - the Launch Lab component (Python side). The page is lab_page.py; the browser part
lives in lab_component/ (index.html, lab.css, lab.js, physics.js - plain files, no build step).
"""
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component("launch_lab", path=str(Path(__file__).parent / "lab_component"))
VERSION = "3"   # bump after editing lab_component/* so browsers load the new files


def launch_lab(name: str, team: str, defaults: dict, saved: dict | None = None, key: str = "launch_lab"):
    """Draw the lab. Returns {"id", "action": "ask" | "chat", "params": {...}} when a button sends something."""
    return _component(name=name, team=team, defaults=defaults, saved=saved, version=VERSION, key=key, default=None)


def handle_return(st) -> bool:
    """Called at the very top of app.py while the Lab is open: if the Lab's "Chat" / "Ask why" button was just
    pressed, switch back to the chat in THIS run (no second reload) and queue the question. True = show the chat."""
    v = st.session_state.get("launch_lab")
    if not (isinstance(v, dict) and v.get("id") and v.get("action") in ("chat", "ask")
            and v["id"] != st.session_state.get("lab_seen")):
        return False
    import launchlab
    st.session_state.lab_seen = v["id"]
    params = launchlab.clean(v.get("params"))
    st.session_state.lab_params = params
    if v.get("action") == "ask":
        st.session_state.setdefault("pending", []).append(launchlab.ask_text(params))
    st.session_state.view = "chat"
    return True
