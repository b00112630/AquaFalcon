"""Runs once per server start on Streamlit Cloud: downloads the Kokoro voice model (~120 MB) in the background.
Until it's there, English answers use the online edge-tts voice, so nothing waits on it."""
import threading
import tts


def _get():
    try:
        if not tts.kokoro_ready():
            tts.kokoro_download()
            tts.warm()
    except Exception as e:  # no internet / GitHub down -> edge-tts keeps working
        print("[boot] Kokoro download failed:", e, flush=True)


threading.Thread(target=_get, daemon=True).start()
