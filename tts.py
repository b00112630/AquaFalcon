"""
tts.py - the voice of voice mode (all devices): a natural, human-sounding neural voice, made on the server.

voice.js plays these mp3s one sentence at a time (sentence 1 plays while the rest are being made).
The browser's own speechSynthesis voice is only a last resort if the server voice fails.
All engines here are free and need no key or account:
  1. Kokoro    - (English) "Heart", a very human-sounding voice that runs ON THIS COMPUTER (~0.5 s a sentence,
                 no internet, no limits). Optional: pip install kokoro-onnx lameenc, then
                 python tts.py kokoro-download   (one-time ~120 MB model download). Skipped if not installed.
  2. edge-tts  - natural online "neural" voices (Ava Multilingual for English if Kokoro is missing, Sana for Arabic)
  3. gTTS      - Google Translate's voice (simpler, very fast) if edge-tts fails
Returns None if all fail (no internet, no Kokoro) - voice.js then uses the browser voice / captions.

Change the voice: edit VOICES / RATE below.
Fix how a word is said: edit PRONOUNCE below (only the spoken audio changes, captions stay as written).
"""
import asyncio
import io
import re

# Arabic answers: Sana (Jordanian, female like Ava, so it still feels like the same rocket; native accent and
# ~1.5 s per sentence). Tried: ar-JO-TaimNeural (male, fine) and Ava speaking Arabic (non-native, slower).
VOICES = {"en": "en-US-AvaMultilingualNeural", "ar": "ar-JO-SanaNeural"}
RATE = "+0%"          # speaking speed, e.g. "+5%" faster, "-5%" slower

# English voice that runs on this computer (Kokoro). Other voices to try: af_bella, af_nicole, am_michael.
KOKORO_VOICE = "af_heart"
KOKORO_SPEED = 1.0
# where the Kokoro model lives (download with: python tts.py kokoro-download). Change with KOKORO_DIR in .env
KOKORO_FILES = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

# How the voice should SAY some words (written form -> spoken spelling). Applied only to the text
# sent to the voice; the captions and chat keep the real spelling. Longest entries are matched first,
# whole words only, any capitalisation. The multilingual voice reads "Aqua" the Spanish way (ah-kwa),
# so we spell it the way we say it. Prefer "Aqua Falcon"? Change the values to "Aqua Falcon".
PRONOUNCE = {
    "AquaFalcon": "Aqua Falcon",
}


def pronounce(text: str) -> str:
    """Respell words from PRONOUNCE (case-insensitive, whole words) - for the voice only."""
    for word in sorted(PRONOUNCE, key=len, reverse=True):
        pat = r"(?<!\w)" + r"\s*".join(re.escape(p) for p in word.split()) + r"(?!\w)"
        text = re.sub(pat, PRONOUNCE[word], text, flags=re.I)
    # a lone "Hey!" opener sounds odd in this voice - say "Hi!" instead
    text = re.sub(r"^\s*(hey[\s,!]*)+", "Hi! ", text, flags=re.I)
    return text


def speakable(text: str) -> str:
    """Same clean-up as voice.js: no markdown, no emoji, stop at the 'sources' footer."""
    text = text or ""
    for mark in ("🔎", "(📡", "_(📡"):
        i = text.find(mark)
        if i >= 0:
            text = text[:i]
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\*\*|__|[*_`#>|~]", " ", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"-{3,}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _edge(text: str, lang: str) -> bytes:
    """edge-tts, made snappy and sturdy: usually ~0.8 s, but now and then the service is slow or answers
    "no audio received". So if an attempt is slow (>1.6 s) a second one starts alongside it (first one wins),
    and a failed attempt is retried right away (2 retries) - all within ~10 s, then gTTS takes over."""
    import edge_tts

    async def once():
        out = b""
        async for chunk in edge_tts.Communicate(text, VOICES[lang], rate=RATE).stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        if not out:
            raise RuntimeError("no audio")
        return out

    async def race():
        loop = asyncio.get_running_loop()
        deadline, tries, running, err = loop.time() + 10, 0, set(), None
        while True:
            if not running:
                if tries >= 3:
                    break
                running.add(asyncio.ensure_future(once())); tries += 1
            wait = min(1.6, deadline - loop.time())
            if wait <= 0:
                break
            done, running = await asyncio.wait(running, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
            for d in done:
                if d.exception() is None:
                    for r in running:
                        r.cancel()
                    return d.result()
                err = d.exception()
                await asyncio.sleep(0.1)
            if not done and tries < 3:            # slow: start a second attempt beside the first
                running.add(asyncio.ensure_future(once())); tries += 1
        for r in running:
            r.cancel()
        raise err or TimeoutError("edge-tts too slow")

    return asyncio.run(race())


def _kokoro_dir():
    import os
    from pathlib import Path
    return Path(os.getenv("KOKORO_DIR") or Path.home() / ".cache" / "aquafalcon-kokoro")


_kok = {"model": None, "failed": False}
import threading as _threading
_kok_lock = _threading.Lock()


def kokoro_ready() -> bool:
    """True if Kokoro is installed and its model files are downloaded (then English uses it)."""
    if _kok["failed"]:
        return False
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        _kok["failed"] = True
        return False
    return all((_kokoro_dir() / f).exists() for f in KOKORO_FILES)


def _to_mp3(samples, rate: int) -> bytes:
    """float audio -> mp3 bytes (lameenc if installed, else ffmpeg, else a WAV file - browsers play all three)."""
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    try:
        import lameenc
        enc = lameenc.Encoder()
        enc.set_bit_rate(64); enc.set_in_sample_rate(rate); enc.set_channels(1); enc.set_quality(2)
        return bytes(enc.encode(pcm) + enc.flush())
    except ImportError:
        pass
    import shutil
    import subprocess
    if shutil.which("ffmpeg"):
        p = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
                            "-b:a", "64k", "-f", "mp3", "-"], input=pcm, capture_output=True, timeout=30)
        if p.returncode == 0 and p.stdout:
            return p.stdout
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def _kokoro(text: str, lang: str) -> bytes:
    """Kokoro "Heart" on this computer (English only)."""
    if lang != "en" or not kokoro_ready():
        raise RuntimeError("kokoro not available")
    with _kok_lock:
        if _kok["model"] is None:
            from kokoro_onnx import Kokoro
            d = _kokoro_dir()
            _kok["model"] = Kokoro(str(d / KOKORO_FILES[0]), str(d / KOKORO_FILES[1]))
        samples, rate = _kok["model"].create(text, voice=KOKORO_VOICE, speed=KOKORO_SPEED, lang="en-us")
    return _to_mp3(samples, rate)


def kokoro_download():
    """One-time download of the Kokoro model (~120 MB) into KOKORO_DIR."""
    import urllib.request
    d = _kokoro_dir()
    d.mkdir(parents=True, exist_ok=True)
    for f in KOKORO_FILES:
        if not (d / f).exists():
            print("downloading", f, "...")
            urllib.request.urlretrieve(KOKORO_URL + f, d / (f + ".part"))
            (d / (f + ".part")).replace(d / f)
    print("Kokoro model ready in", d)


def _gtts(text: str, lang: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text, lang=lang).write_to_fp(buf)
    return buf.getvalue()


def speak_mp3(text: str) -> bytes | None:
    text = pronounce(speakable(text))[:1500]
    if not text:
        return None
    lang = "ar" if re.search(r"[\u0600-\u06FF]", text) else "en"
    for engine in (_kokoro, _edge, _gtts):
        try:
            data = engine(text, lang)
            if data:
                return data
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- per-sentence voice (fast first audio)
_END = re.compile(r"[.!?\u061F\u3002](?=\s|$)|\n")
_FOOTER = re.compile(r"\U0001F50E|\(\U0001F4E1|_\(\U0001F4E1")


def split_sentences(text: str, final: bool) -> tuple[list[str], int]:
    """Finished sentences in text (same rule as voice.js). Returns (sentences, characters used).
    final=True: the last unfinished bit counts as a sentence too."""
    f = _FOOTER.search(text)
    if f:
        text, final = text[:f.start()], True
    out, pos = [], 0
    while True:
        m = _END.search(text, pos)
        if m and (m.end() < len(text) or final):
            seg, pos = text[pos:m.end()], m.end()
        elif final and text[pos:].strip():
            seg, pos = text[pos:], len(text)
        else:
            break
        if speakable(seg):
            out.append(seg)
    return out, pos


class SentenceVoicer:
    """Turns a streaming answer into one mp3 per sentence, in the background, so the phone can play
    sentence 1 while sentence 2 is still being made (instead of waiting for the whole answer)."""

    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.jobs, self.used = [], 0

    def feed(self, text_so_far: str, final: bool = False):
        sentences, used = split_sentences(text_so_far[self.used:], final)
        self.used += used
        for s in sentences:
            self.jobs.append(self.pool.submit(speak_mp3, s))

    def ready(self) -> list[str]:
        """base64 mp3s of the sentences that are ready, in order (stops at the first one still cooking)."""
        import base64
        out = []
        for j in self.jobs:
            if not j.done():
                break
            data = j.result()
            out.append(base64.b64encode(data).decode("ascii") if data else "")
        return out

    def all_done(self) -> bool:
        return all(j.done() for j in self.jobs)


# ---------------------------------------------------------------- warm-up
_warm_at = 0.0


def warm(every: float = 240.0):
    """Make one tiny clip in the background so the first real answer doesn't pay the voice service's
    slow first connection (seen: ~5 s on the first sentence of a fresh app). Cheap; at most every few minutes."""
    import threading
    import time
    global _warm_at
    if time.time() - _warm_at < every:
        return
    _warm_at = time.time()

    def go():
        try:
            if kokoro_ready():
                _kokoro("Hi.", "en")       # loads the local model once (~1 s)
                _edge("مرحبا.", "ar")       # English is local, so keep the Arabic online voice warm
            else:
                _edge("Hi.", "en")
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()


def make_greetings():
    """Re-make voice_component/greet0.mp3 ... greet12.mp3 (the opening lines in voice.js) with the current
    VOICES / RATE / PRONOUNCE. Run:  python tts.py greetings   (then bump VERSION in voice_mode.py)."""
    from pathlib import Path
    folder = Path(__file__).parent / "voice_component"
    js = (folder / "voice.js").read_text(encoding="utf-8")
    start = js.index("var GREETINGS = [")
    lines = re.findall(r'"((?:[^"\\]|\\.)*)"', js[start:js.index("];", start)])
    for i, line in enumerate(lines):
        data = speak_mp3(line)
        if data:
            (folder / f"greet{i}.mp3").write_bytes(data)
        print(f"greet{i}.mp3", "ok" if data else "FAILED", "-", line)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["greetings"]:
        make_greetings()
    elif sys.argv[1:] == ["kokoro-download"]:
        kokoro_download()
    else:
        print("usage: python tts.py greetings | kokoro-download")
