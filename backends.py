"""
backends.py - the "brains" the chatbot can use.

  groq    : Groq - the FASTEST free option (key: https://console.groq.com/keys).
            The same key also powers the voice (mic) button.
  gemini  : Google Gemini (free key: https://aistudio.google.com/apikey)
  ollama  : a model running on your own laptop (https://ollama.com) - no internet needed
  offline : no AI at all - keyword answers straight from rocket_info.yaml (see offline.py)

Every brain STREAMS its answer: it yields small pieces of text as soon as the AI
produces them, so the reply starts appearing on screen almost instantly.

Each stream_* function gets:
  system   -> the instructions + team facts (built in bot.py)
  history  -> earlier messages: [{"role": "user"/"assistant", "content": "..."}]
  message  -> the new question
"""
import base64
import json
import os

import requests

TIMEOUT = (10, 60)  # seconds: (connect, read)


class BackendError(Exception):
    """Raised when an online brain can't answer (no internet, bad key, quota used up...)."""


def friendly_error(who: str, status: int) -> str:
    reasons = {400: "bad request or invalid API key", 401: "invalid API key", 403: "API key not allowed",
               404: "model name not found - change the model in .env",
               429: "free quota used up for now - wait a minute"}
    return f"{who}: {reasons.get(status, 'error')} ({status})"


def _post(url, who, **kw):
    try:
        r = requests.post(url, timeout=TIMEOUT, **kw)
    except requests.RequestException:
        raise BackendError(f"{who}: can't connect (no internet, or the server isn't running)")
    if r.status_code != 200:
        raise BackendError(friendly_error(who, r.status_code))
    r.encoding = "utf-8"   # so emojis come through correctly
    return r


# ---------------------------------------------------------------- Gemini
def _models(main_var, main_default, backup_var, backup_default):
    """The main model + a backup model. Free limits are counted PER MODEL,
    so when the main one runs out for the day, the backup one usually still works."""
    models = [os.getenv(main_var, main_default), os.getenv(backup_var, backup_default)]
    return [m for i, m in enumerate(models) if m and m not in models[:i]]


def _try_models(models, start):
    """Call start(model) for each model until one works (skips 'quota used up' / 'model not found')."""
    last = None
    for model in models:
        try:
            return start(model)
        except BackendError as e:
            last = e
            if "(429)" not in str(e) and "(404)" not in str(e):
                raise
    raise last


def _race(attempts, delays, deadline=15.0):
    """'Hedged' requests: free AI servers are sometimes slow to start answering (we measured the same
    question taking 0.4 s once and 15 s the next). So: start attempt 0; if it hasn't produced its first
    words after delays[1] seconds, ALSO start attempt 1 (and so on) - whichever starts talking first wins,
    the others are dropped. An attempt that fails starts the next one straight away.
    Each attempt is a function returning an iterator of text pieces."""
    import queue
    import threading
    import time

    box, won, started, errors = queue.Queue(), threading.Event(), [], []

    def run(i):
        try:
            it = iter(attempts[i]())
            first = next(it, None)
            box.put(("ok", i, first, it))
        except Exception as e:  # noqa: BLE001 - reported below if every attempt fails
            box.put(("err", i, e, None))

    def launch():
        i = len(started)
        started.append(i)
        threading.Thread(target=run, args=(i,), daemon=True).start()

    launch()
    t0 = time.time()
    while True:
        nxt = delays[len(started)] if len(started) < len(attempts) else deadline
        wait = max(0.0, t0 + nxt - time.time())
        try:
            kind, i, val, it = box.get(timeout=wait)
        except queue.Empty:
            if len(started) >= len(attempts):   # nobody has said a word for `deadline` seconds: give up,
                won.set()                       # bot.py then answers from the offline backup instead
                raise BackendError(f"Gemini: no answer within {deadline:.0f} s (server busy)")
            launch()                    # attempt still silent -> start the next one alongside it
            continue
        if kind == "ok" and not won.is_set():
            won.set()
            if val:
                yield val
            yield from it
            return
        if kind == "err":
            errors.append(val)
            if len(errors) == len(attempts):
                raise errors[-1]
            if len(started) < len(attempts) and len(started) - len(errors) == 0:
                launch()                # everything running has failed -> next one now


def stream_gemini(system: str, history: list, message: str):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise BackendError("GEMINI_API_KEY is not set in .env")
    base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")

    # Gemini calls the assistant "model" instead of "assistant"
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in history]
    contents.append({"role": "user", "parts": [{"text": message}]})
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": 1024}}
    models = _models("GEMINI_MODEL", "gemini-3.1-flash-lite-preview", "GEMINI_BACKUP_MODEL", "gemini-3.1-flash-lite")

    def start(model):
        url = f"{base}/v1beta/models/{model}:streamGenerateContent?alt=sse"
        fast = {**body, "generationConfig": {**body["generationConfig"], "thinkingConfig": {"thinkingBudget": 0}}}
        try:   # "thinking" off = answers start ~3x faster
            return _post(url, "Gemini", json=fast, headers={"x-goog-api-key": key}, stream=True)
        except BackendError as e:
            if "(400)" not in str(e):
                raise
            # this model can't switch thinking off -> ask normally
            return _post(url, "Gemini", json=body, headers={"x-goog-api-key": key}, stream=True)

    def pieces(model):
        r = start(model)
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                data = json.loads(line[5:])
                for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    if part.get("text") and not part.get("thought"):
                        yield part["text"]

    hedge = float(os.getenv("GEMINI_HEDGE_S", "1.2") or 0)
    if hedge <= 0:            # hedging switched off: plain "main model, then backup" like before
        yield from pieces(_try_models(models, lambda m: m))
        return
    order = (models * 2)[:4]  # main, backup, main again, backup again
    yield from _race([lambda m=m: pieces(m) for m in order], [0, hedge, hedge * 2.2, hedge * 3.8],
                     deadline=float(os.getenv("GEMINI_DEADLINE_S", "15")))


# ---------------------------------------------------------- Groq / Ollama
def _stream_openai_style(url, key, models, who, system, history, message):
    """Groq and Ollama both speak the same 'chat completions' format."""
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    def start(model):
        body = {"model": model, "messages": messages, "temperature": 0.6, "stream": True}
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"   # think less -> answer faster
        return _post(url, who, json=body, headers=headers, stream=True)

    r = _try_models(models, start)
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            data = line[5:].strip()
            if data == "[DONE]":
                break
            piece = json.loads(data)["choices"][0].get("delta", {}).get("content")
            if piece:
                yield piece


def stream_groq(system, history, message):
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise BackendError("GROQ_API_KEY is not set in .env")
    base = os.getenv("GROQ_BASE_URL", "https://api.groq.com")
    models = _models("GROQ_MODEL", "openai/gpt-oss-120b", "GROQ_BACKUP_MODEL", "openai/gpt-oss-20b")
    # free Groq limits are per model and per MINUTE: a 3rd model keeps answering during a burst of questions
    third = os.getenv("GROQ_BACKUP_MODEL_2", "").strip()   # optional, e.g. another model your key lists
    if third and third not in models:
        models.append(third)
    yield from _stream_openai_style(f"{base}/openai/v1/chat/completions", key, models, "Groq",
                                    system, history, message)


def stream_ollama(system, history, message):
    base = os.getenv("OLLAMA_URL", "http://localhost:11434")
    models = [os.getenv("OLLAMA_MODEL", "llama3.2")]
    yield from _stream_openai_style(f"{base}/v1/chat/completions", "", models, "Ollama",
                                    system, history, message)


BACKENDS = {"groq": stream_groq, "gemini": stream_gemini, "ollama": stream_ollama}


def pick_backend() -> str:
    """Choose a brain: the BACKEND setting in .env, or the first API key we find."""
    choice = os.getenv("BACKEND", "auto").strip().lower()
    if choice != "auto":
        return choice
    if os.getenv("GROQ_API_KEY", "").strip():
        return "groq"      # fastest
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "offline"


# ---------------------------------------------------------------- Voice
# Speech-to-text hint: the speaker may use English, Arabic (Levantine: Jordanian / Palestinian) or mix both.
STT_HINT = ("A student asking the AquaFalcon water rocket chatbot about the project, in English, Arabic "
            "(Levantine dialect) or a mix: rocket, fins, nozzle, الصاروخ، الزعانف، شو، قديش، كيف.")


def transcribe(audio: bytes, filename: str, mime: str, lang: str = "auto") -> str:
    """Turn a voice recording into text. Uses Groq Whisper if there's a Groq key,
    otherwise Gemini. (iPhones record .m4a/.mp4, Chrome records .webm - both work.)
    lang: "auto" (default) = detect English / Arabic / a mix by itself; "en-US" or "ar-JO" = that language only."""
    code = {"en": "en", "ar": "ar"}.get((lang or "auto")[:2].lower(), "")
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        base = os.getenv("GROQ_BASE_URL", "https://api.groq.com")
        r = _post(f"{base}/openai/v1/audio/transcriptions", "Groq voice",
                  headers={"Authorization": f"Bearer {groq_key}"},
                  files={"file": (filename, audio, mime)},
                  data={"model": os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"), "prompt": STT_HINT,
                        **({"language": code} if code else {})})   # no language = Whisper detects it
        return r.json().get("text", "").strip()

    gem_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gem_key:
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        body = {"contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
            {"text": "Transcribe this voice message exactly as spoken. It may be English, Arabic (often Levantine: "
                     "Jordanian/Palestinian) or a mix of both: write Arabic words in Arabic script and English words "
                     "in English, keeping the speaker's own words and dialect (don't translate). Reply with only the words."}]}]}
        models = _models("GEMINI_MODEL", "gemini-3.5-flash-lite", "GEMINI_BACKUP_MODEL", "gemini-3.1-flash-lite")
        r = _try_models(models, lambda m: _post(f"{base}/v1beta/models/{m}:generateContent", "Gemini voice",
                                                json=body, headers={"x-goog-api-key": gem_key}))
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()

    raise BackendError("voice needs a Groq or Gemini key in .env")
