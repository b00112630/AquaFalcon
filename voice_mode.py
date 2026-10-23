"""
voice_mode.py - the ChatGPT-style hands-free voice mode (Python side).

The browser part lives in voice_component/ (plain HTML/JS/CSS, no build step):
  * voice_component/index.html : an invisible Streamlit custom component (the "bridge")
  * voice_component/voice.js   : the full-screen voice screen, listening, silence detection,
                                 speaking the answer sentence by sentence, barge-in
  * voice_component/voice.css  : its look (AquaFalcon night-sky launch pad + glowing water core)

How a question travels:
  1. voice.js hears you (free browser speech recognition) and sends {"id", "text"} through
     the bridge -> voice_mode() returns it in app.py, which answers it like a typed question.
  2. While the answer streams, app.py also writes it into a hidden box on the page
     (stream_html below). voice.js reads that box ~8 times a second and starts speaking
     as soon as the first sentence is complete.
  3. When the answer is finished, voice.js listens again automatically.
  4. The voice: voice.js sends "server_tts": true with the question and app.py adds one mp3 per
     sentence (tts.py: free natural voice "Ava") as data-a0, data-a1, ... (base64) as each is ready.
     voice.js plays them in order; the browser's own voice is only a last-resort backup.
"""
import base64
import html
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component("voice_mode", path=str(Path(__file__).parent / "voice_component"))
VERSION = "18"   # bump this after editing voice.js / voice.css so browsers load the new files


def voice_mode(name: str, can_transcribe: bool, team: str = "", key: str = "voice"):
    """Draw the (invisible) bridge. Returns the latest question sent from voice mode, or None:
    {"id": "...", "text": "..."}  or, in browsers without speech recognition,
    {"id": "...", "audio": "<base64>", "mime": "audio/webm"} to be transcribed by backends.py."""
    try:                       # warm the voice service up so the first spoken answer starts fast
        import tts
        tts.warm()
    except Exception:
        pass
    return _component(name=name, team=team, can_transcribe=can_transcribe, version=VERSION, key=key, default=None)


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


def stream_html(state: dict | None) -> str:
    """The hidden box voice.js reads: which question it answers, the answer so far, done or not."""
    s = state or {}
    return (f'<div class="afv-stream" data-id="{html.escape(str(s.get("id", "")))}" '
            f'data-done="{1 if s.get("done") else 0}" data-t="{_b64(s.get("text", ""))}" '
            f'data-heard="{_b64(s.get("heard", ""))}" data-err="{_b64(s.get("err", ""))}" '
            f'data-audio="{s.get("audio", "")}"'
            # one mp3 per sentence; "x" = that sentence's mp3 failed (voice.js uses the browser voice for it)
            + "".join(f' data-a{i}="{c or "x"}"' for i, c in enumerate(s.get("clips") or []))
            + '></div>')
