"""
lab_mode.py - the Launch Lab component (Python side). The page is lab_page.py; the browser part
lives in lab_component/ (index.html, lab.css, lab.js, physics.js - plain files, no build step).
"""
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component("launch_lab", path=str(Path(__file__).parent / "lab_component"))
VERSION = "2"   # bump after editing lab_component/* so browsers load the new files


def launch_lab(name: str, team: str, defaults: dict, saved: dict | None = None, key: str = "launch_lab"):
    """Draw the lab. Returns {"id", "action": "ask" | "chat", "params": {...}} when a button sends something."""
    return _component(name=name, team=team, defaults=defaults, saved=saved, version=VERSION, key=key, default=None)
