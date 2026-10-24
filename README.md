# 🚀 AquaFalcon - Water Rocket Chatbot (NGN110)

A lively chatbot that **is** our water rocket. Ask it (typing or talking) how it flies,
what it's made of, how the test launches went, and how we keep everyone safe.

> Everything here is **100% free**: no credit card anywhere.
> The rocket name and all team facts live in ONE file: `rocket_info.yaml`.
> Values marked `# EXAMPLE` are placeholders - replace them with your team's real data.

---

## 1. What's in the folder

| File | What it does |
|---|---|
| `rocket_info.yaml` | **Your team's facts** (name, team, design, water, pressure, tests, safety, sustainability, FAQ). Edit this! |
| `knowledge/physics.md` | Short physics notes (Newton's 3rd law, pressure, CG/CP, projectile motion...) |
| `app.py` | The chat web page (Streamlit): streaming answers, mic button, suggestion chips, Listen (read-aloud), and a **Settings** button (top-right) to pick the AI brain, auto read-aloud, or clear the chat. The whole look is the CSS block at the top; change `ACCENT` (and `--accent`) to re-colour it |
| `bot.py` | The brain's rules: personality, "don't invent facts", off-topic redirect, fact-check, fallbacks |
| `backends.py` | Talks to the free AI services (Groq, Gemini, or Ollama on your laptop) + voice-to-text |
| `voice_mode.py` + `voice_component/` | **Voice mode** (hands-free, AquaFalcon-styled): the water-drop button next to the chat box. `tts.py` = the free natural voice (Kokoro "Heart" on your laptop, or edge-tts Ava online) that reads answers out loud. Plain HTML/JS/CSS, no build step - see section 3b |
| `whatif.py` | **"What if" calculator**: "what if we used 70 psi?" → a distance prediction computed in Python from your test rows (never invented by the AI). See the section at the end |
| `charts.py` | **Auto charts** in the chat bubble (distance per test, vs pressure, vs water), drawn from your test rows |
| `offline.py` | Backup brain with **no internet / no key**: keyword answers straight from the fact file |
| `tests/test_questions.yaml` | 17 test questions covering every area of the brief |
| `tests/run_tests.py` | Asks all test questions and saves a results table (CSV + Markdown) |
| `tests/test_regressions.py` | Quick checks for bugs we fixed (made-up height / competition facts, blank messages...) and for the what-if calculator + charts. No key needed: `python tests/test_regressions.py` |
| `.env.example` | Template for your free API keys |
| `run_windows.bat` / `run_mac.command` | Double-click shortcuts to start the app |
| `docs/` | The report write-up (PDF + editable Word file) |

---

## 2. Setup on your laptop (about 10 minutes)

**Step 1 - Install Python 3.11 or newer**
- Windows: download from https://www.python.org/downloads/ and **tick "Add python.exe to PATH"** in the installer.
- Mac: download from the same page (or `brew install python`).

**Step 2 - Open a terminal inside the project folder**
- Windows: open the folder, click the address bar, type `cmd`, press Enter.
- Mac: right-click the folder → *New Terminal at Folder*.

**Step 3 - Install the libraries** (one time)
```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (Mac)
pip install -r requirements.txt
```
(On Mac use `python3` if `python` isn't found.)

**Step 4 - Get a free key (no credit card)**
1. Go to https://console.groq.com/keys, sign in with Google/GitHub, click **Create API Key**, copy it.
2. Copy `.env.example`, rename the copy to `.env`, and paste the key after `GROQ_API_KEY=`.
3. Optional backup: a free Gemini key from https://aistudio.google.com/apikey → paste after `GEMINI_API_KEY=`.

No key at all? It still runs in **offline mode** (simpler answers, no mic).

**Step 5 - Run it**
```
streamlit run app.py
```
Your browser opens at http://localhost:8501. Try the suggestion chips, type, or tap 🎤.

Shortcut after the first setup: double-click `run_windows.bat` (Windows) or `run_mac.command` (Mac;
the first time, right-click → Open).

Terminal-only version (no web page): `python bot.py`

> Platform approval: the brief says the platform must be approved by your instructor. Show them this
> README: it's a Python app (Streamlit) using a free AI API, with an offline mode that needs no AI at all.

---

## 3. Use it on your iPhone

| Option | How | Mic 🎤 works? |
|---|---|---|
| **A. Same Wi-Fi** | Run `streamlit run app.py --server.address 0.0.0.0`. Find the laptop's IP (Windows: `ipconfig` → IPv4; Mac: `ipconfig getifaddr en0`). On the iPhone open Safari → `http://<that-ip>:8501` | ❌ No - iPhones only allow the mic on **https** pages. Typing + read-aloud work. |
| **B. Free https link from your laptop** | Install cloudflared (free, no account): Windows `winget install --id Cloudflare.cloudflared`, Mac `brew install cloudflared`. With the app running, open a 2nd terminal: `cloudflared tunnel --url http://localhost:8501`. It prints a link like `https://something.trycloudflare.com` - open it on any phone. | ✅ Yes. The link changes every time and works only while your laptop is on. |
| **C. Free permanent link** (best for the presentation) | Streamlit Community Cloud - see below. | ✅ Yes |


### Install AquaFalcon on your iPhone as an app (free)
A real App Store app needs a paid Apple developer account, so AquaFalcon installs as a **web app** instead -
same thing for daily use: its own icon, opens full screen, no Safari bars.
1. Open the AquaFalcon **https** link in **Safari** (not Chrome/WhatsApp's built-in browser).
2. Tap the **Share** button (square with the arrow) → scroll down → **Add to Home Screen** → **Add**.
3. The AquaFalcon icon (the water-rocket core) appears on your home screen. Tap it to open the app.

Want the icon to open **straight into voice mode**? Open the link with `?voice=1` at the end
(e.g. `https://your-link/?voice=1`) and add *that* page to the home screen. It opens on the voice screen - tap the water core once to start.
On a laptop, Chrome shows an **Install** icon in the address bar for the same thing.
How it works: `static/` holds the icon + `manifest.json` (served by Streamlit because `enableStaticServing = true` in
`.streamlit/config.toml`), and the voice-mode bridge adds the app tags (`apple-touch-icon`, `apple-mobile-web-app-capable`, app name, navy theme colour) to the page.

### Free deploy on Streamlit Community Cloud (no credit card)
1. Make a free GitHub account → **New repository** (public is fine) → *uploading an existing file* → drag in all project files **except `.env`** (never upload your key).
2. Go to https://share.streamlit.io, sign in with GitHub → **Create app** → pick your repo, branch `main`, main file `app.py`.
3. Click **Advanced settings → Secrets** and paste:
   ```
   GROQ_API_KEY = "your-groq-key"
   GEMINI_API_KEY = "your-gemini-key"
   ```
4. Deploy. You get a link like `https://aquafalcon.streamlit.app`. Open it once before the presentation (see limits below).

---

## 3b. Voice mode (hands-free talking, AquaFalcon style)

Tap the **water-drop button** next to the chat box. The AquaFalcon "launch pad" opens: a navy night sky,
the **AquaFalcon · Team 7** badge, and the **water core** - a glass bubble of water with a nozzle and fins, like our bottle rocket.
It greets you out loud with a short project question (one of 13, picked at random each time, e.g. "Ask me about our rocket design,
testing or results.") and then listens. Status words are plain: **Listening…** (ripples follow your voice) · **Still listening · Tap to send**
(you paused, it's waiting) · **Thinking…** (bubbles swirl, the pressure gauge fills) · **Responding…** (the water pulses, thrust sprays from the nozzle).

1. **Just talk.** Your words appear as a live caption while you speak.
2. **It waits for a real pause.** Laptop: it sends after about **1.5 s with no new words** (a one-word question waits a bit longer).
   iPhone: it sends after about **1.5 s of quiet** once you've talked for at least 0.4 s (it measures your voice's loudness, so short
   pauses mid-sentence don't cut you off).
3. **Tap the water core to send right away** if you don't want to wait. A soft "drop" sound + ripple confirms it was sent.
4. The rocket **answers out loud in 1-2 short sentences** and starts speaking the **first sentence while the rest is still being written**.
5. When it finishes, it **listens again automatically** - a real back-and-forth conversation.
6. **Interrupt any time:** start talking over it (laptop) or tap the water core (iPhone) and it stops and listens.
7. **Mic button** = mute (stop listening). **End** = the water core launches away like the rocket and you're back in the chat. Every question and answer is also saved in the normal chat.
8. Top-right **sliders** = settings: speak English or عربي. (The voice list there is only the backup voice - see "The voice" below.) Top-left button = captions on/off. You can also type in the "Type a question" box.

**What it uses (all free, no key needed for the voice part on laptops):**
- Laptop (Chrome/Edge): the browser's built-in speech recognition (`webkitSpeechRecognition`) for listening; answers are spoken by the natural server voice (below).
- **iPhone / iPad (its own path, since v4):** Apple's built-in speech recognition is unreliable on iPhone and often missing or silent
  inside home-screen apps, and it fights the speaker. So on iPhone voice mode **records you itself**: the mic goes into Web Audio,
  a loudness meter notices when you start talking (it keeps ~0.45 s from just before, so your first word isn't cut) and when you stop
  (**1.5 s quiet** after at least 0.4 s of talking - or **tap the water core** to send early). The clip is sent as a small 16 kHz WAV
  and the app turns it into text with the same free Groq/Gemini key as the 🎤 button (`backends.transcribe`).
  The **7 little bars under the status light up while you talk**, so you can see it hearing you ("Hearing you…").
- iPhone answers are spoken by **edge-tts** (free natural voices, no key; **gTTS** as backup, `tts.py`), one mp3 per sentence so the first
  sentence starts while the rest is made, played through the audio player unlocked by your opening tap. The **mic is switched off while it talks**
  (iPhones make the speaker quiet while the mic is on) and back on to listen. Tap the core to interrupt. No internet for the voice service?
  It falls back to the phone's own voice.
- iPhone runs a lighter animation (30 fps, no blur behind the glass, still stars, the chat page underneath isn't drawn while voice mode is open).
- Browsers without speech recognition (e.g. Firefox): it records your question and the app transcribes it with the free key.
- In voice mode the bot is told to answer in 1-3 short spoken sentences with no emojis or tables, so it sounds natural.

**iPhone checklist**
- The link must be **https** (option B or C above). On `http://` iPhones block the microphone.
- Use **Safari**. When asked, tap **Allow** for the microphone. If you tapped Don't Allow: in Safari tap **aA → Website Settings → Microphone → Allow**.
- iPhone voice input needs the app's free AI key (Groq or Gemini in `.env` / Secrets) because the server does the listening. With no key at all,
  it falls back to Apple's recognizer (needs **Settings → General → Keyboard → Enable Dictation**).
- **Home-screen app and the mic:** if your iPhone won't give the microphone to the home-screen app, voice mode says so and shows an
  **Open in Safari** button (it opens straight into voice mode there) plus **Copy link**. Also check **Settings → Safari → Microphone → Ask/Allow**.
- Something odd? Open the link with **`?debug=1`** at the end: a small line at the bottom shows the state, mic level, how long the mic took to start,
  the clip length, the server round-trip and the last error - send a screenshot of it.
- Advanced switches (add to the link): `?iossr=1` = use Apple's recognizer instead (old way), `?iosvoice=browser` = phone's own voice for answers,
  `?keepmic=1` = keep the mic open between turns (muted) instead of switching it off.
- Turn **silent mode off** (the switch on the side / Action button) and turn the volume up - iPhones mute web audio in silent mode.
- The very first tap on the water-drop button "unlocks" sound on iPhone - that's why voice mode must be opened with a tap.

**The voice (natural, on every device)**
- English answers, the Listen button and the greetings are spoken by **Kokoro "Heart"** (`af_heart`), a very human-sounding
  voice that runs **on your own laptop**: about 0.5 s per sentence, no internet, no key, no limits. It's optional:
  ```
  pip install kokoro-onnx lameenc
  python tts.py kokoro-download        # one-time ~120 MB model download (saved outside the project folder)
  ```
  Without it, English is spoken by **Ava** (`en-US-AvaMultilingualNeural`, free online voice through **edge-tts**). Arabic
  answers always use the Jordanian edge-tts voice `ar-JO-SanaNeural` (Kokoro is English-only).
  `tts.py` makes one mp3 per sentence while the answer is still being written, so the first sentence starts playing while the
  next ones are being made, and the caption shows the sentence being spoken. Order: Kokoro → edge-tts → gTTS → browser voice.
- If edge-tts hiccups (it sometimes answers "no audio received" or is slow), `tts.py` retries quickly / starts a second try beside a
  slow one, then falls back to **gTTS**. If no server voice arrives within ~6.5 s, or there's no internet for it, the browser's own
  voice (`speechSynthesis`) reads the rest - a last resort only.
- **Change the voice:** edit `VOICES` (and `RATE` for speed) at the top of `tts.py`. List voices with `edge-tts --list-voices`.
- **Fix how a word is said:** edit `PRONOUNCE` at the top of `tts.py`. It only changes what the voice *says* - captions and chat keep
  the real spelling. Default: `"AquaFalcon" -> "Aqua Falcon"` (two words, so every voice says the name clearly).
  After changing it, re-make the 13 greeting clips
  (`voice_component/greet0-12.mp3`, same texts as `GREETINGS` in `voice.js`) with `python tts.py greetings`, and bump `VERSION`
  in `voice_mode.py` so browsers fetch the new files.
- Want the old built-in browser voice instead? Add `?voice=browser` to the link.

**Honest limits (free browser voice)**
- Talking over the bot works best with **headphones/AirPods**. On loud laptop speakers the mic can hear the bot itself; the app raises its "you're talking" threshold while the bot speaks, so speak clearly or tap the water core.
- On iPhone an open microphone switches the phone to "call audio" (quiet earpiece or muted), so voice mode **turns the mic off while
  the rocket talks** and back on after. That means on iPhone you interrupt by **tapping the water core** (talking over it works on laptops).
  If Safari doesn't restart listening by itself after an answer, the core dims and says **"Tap to talk"** - one tap and you're back.
- The natural voice needs internet (it's made by a free online service). Offline, the built-in browser voice takes over and sounds more robotic.
- Chrome's speech recognition needs internet (it uses Google's free service). Offline, use the chat box - the offline brain still answers.

**Why it's built this way (for the report):** Streamlit can't talk to the microphone or the speaker by itself, and voice mode needs messages in **both directions** (browser → Python: "here is the question"; Python → browser: "here is the answer, sentence by sentence"). So `voice_mode.py` declares a real Streamlit **custom component** (`components.declare_component` with a local folder - plain JavaScript using Streamlit's component messages, so no npm/React build is needed). The question goes browser → Python as the component's value; the answer streams back through a hidden box on the page that the voice screen reads several times a second, so speaking can start before the answer is finished. The answer goes through exactly the same `bot.py` brain, fallbacks and fact-check as typed questions.

---

## 4. Free services and their limits

| Service | Used for | Free limits (no card) | If the limit is hit |
|---|---|---|---|
| **Groq** (recommended, fastest) | chat (`openai/gpt-oss-120b`, backup `openai/gpt-oss-20b`) | per model: 30 requests/min, 1,000 requests/day, 8,000 tokens/min, 200,000 tokens/day. One question uses ~2,000 tokens, so about **3-4 questions per minute** and ~100 per day per model. | The bot switches to the backup Groq model, then Gemini (if you added a key), then offline mode. |
| **Groq Whisper** | voice → text (`whisper-large-v3-turbo`) | 20 requests/min, 2,000/day, 7,200 seconds of audio per hour | Voice switches to Gemini (if you added a key); otherwise just type. |
| **Google Gemini** (backup) | chat + voice → text (`gemini-3.5-flash-lite`, backup `gemini-3.1-flash-lite`) | Counted per model and per day. We saw **500 requests/day** on `gemini-3.5-flash-lite` (Oct 2026). Your exact per-minute limits are shown in AI Studio → *Rate limit*. | Backup Gemini model, then offline mode. |
| **Kokoro "Heart"** (optional, on your laptop) | English voice | Free, offline, unlimited (~120 MB model) | edge-tts Ava |
| **edge-tts (Ava / Sana)** | reading answers aloud (Arabic always; English if no Kokoro) | Free, no key, no published limit | gTTS, then the browser's own voice |
| **Browser voice** | voice-mode listening (laptop) + backup voice | Free, built into the phone/laptop, unlimited | Voice mode records + uses Groq/Gemini instead |
| **Streamlit Community Cloud** | public link | Free. The app **sleeps after ~12 hours with no visitors**; the next visit wakes it in about 30 s. | Open the link a few minutes before you present. |
| **Cloudflare quick tunnel** | https link from the laptop | Free, no account; random link each time | Just restart it. |
| **Ollama** (optional) | AI fully on your laptop, no internet | Free; needs ~4 GB free RAM. Install from https://ollama.com, run `ollama pull llama3.2`, set `BACKEND=ollama` in `.env` | - |

Groq's numbers are from Groq's rate-limits page (Sept 2026); free limits change sometimes, so check
https://console.groq.com/settings/limits for your exact numbers. Limits are per account, not per key.

---

## 5. Test it (for the report)
```
python tests/run_tests.py                     # uses your key (or offline if none)
python tests/run_tests.py --backend offline   # offline brain
python tests/run_tests.py --before            # the FIRST naive version (to show the limitation)
```
Results go to `tests/results/results_<brain>.csv` and `.md`. Each row has the question, the answer,
an automatic PASS/CHECK/FAIL, and an empty **Notes** column for your team's own judgement.
Add your own questions to `tests/test_questions.yaml`.

---

## 6. Make it YOUR rocket
Open `rocket_info.yaml` and replace every `# EXAMPLE` value: rocket name (= chatbot name), team members,
bottle, length (< 50 cm), water volume, pressure, fins, nose cone, materials, your **real test results**,
safety and sustainability. After the competition (15 Nov), fill in `result_distance_m` and `placement`.
Anything you don't know yet → write `unknown` and the bot will say so instead of guessing.
The team name in the top bar, the welcome screen and voice mode all come from `team_name` - no code to edit.
Only add a `date:` to a test row once that launch has really happened.
Restart the app after editing.

---

## 7. Troubleshooting
| Problem | Fix |
|---|---|
| Answers are slow (5-30 s) | Free Gemini is sometimes slow. Use a Groq key (much faster) and keep Gemini as the backup. |
| Can't type while it's answering | On purpose: the box unlocks when the answer is finished, so no question gets lost. |
| `python` / `pip` not found | Reinstall Python with "Add to PATH" ticked, or use `python3` / `pip3` on Mac. |
| "via offline (fallback)" under an answer + "invalid API key" | Check the key in `.env` (no spaces, no quotes). |
| "free quota used up" | Wait a minute (per-minute limit) or until tomorrow (daily limit); add the other free key as backup. |
| "model name not found" | The provider retired that model: put a current one in `.env` (`GROQ_MODEL=...` / `GEMINI_MODEL=...`). |
| Mic button does nothing on iPhone | You're on an `http://` link: use option B or C (https). Allow microphone when Safari asks. |
| No sound when reading aloud on iPhone | Turn off silent mode and tap **Listen** under the answer. |
| Voice mode says "Tap to talk" | The browser stopped listening (normal on iPhone after an answer). Tap the water core once. |
| Voice mode: I can't hear the answer (iPhone) | Turn silent mode off and the volume up. If the phone's own voice stays silent, voice mode switches to the free server voice by itself (needs `edge-tts`/`gTTS` installed: `pip install -r requirements.txt`). |
| Voice mode keeps interrupting itself | The mic hears the speaker: use headphones or lower the volume. |
| Voice mode: "Turn on Dictation" | iPhone Settings → General → Keyboard → Enable Dictation (or add a Groq key so it can record instead). |
| Changed `voice.js` but nothing changes | Bump `VERSION` in `voice_mode.py` and reload the page. |

## 8. How it works (one paragraph for the presentation)
When you ask a question, `bot.py` builds instructions for the AI: "You are AquaFalcon, a lively rocket;
only use these team facts; say when you don't know; politely refuse off-topic questions", followed by the
contents of `rocket_info.yaml` and the physics notes that match the question. The AI (Groq or Gemini) writes
the answer and it streams onto the screen word by word. A fact-checker then looks for any measurement in the
answer that isn't in our files and flags it. If the internet or the free quota fails, the offline brain answers
from the fact file using keywords, so the demo never dies. The mic records your voice, a free speech-to-text
model turns it into text, and the answer can be read aloud by the browser's built-in voice. Voice mode
chains all of this into a hands-free conversation: the browser listens, notices when you stop talking, sends the
question, speaks the answer sentence by sentence as it streams in, and then listens again.


---

## Arabic + English voice (Auto) - and typo-proof answers

- **Voice mode understands English, عربي, or a mix** without touching any setting. The default language is
  **Auto**: on every device (laptop and iPhone) voice mode records you itself and the speech-to-text
  (`backends.transcribe`, Groq Whisper or Gemini) works out the language - Levantine Arabic and mixed
  sentences like "how high did الصاروخ fly?" included. Browser speech recognition can only listen for one
  language, so it's used only if you pick **English** or **عربي** in the voice settings (sliders icon).
- **Answers come back in your language**: ask in Arabic and the rocket answers in simple, friendly Arabic
  (`bot.py`, LANGUAGE rule), spoken with the Jordanian voice `ar-JO-SanaNeural` (`tts.py`, `VOICES`), and the
  captions show right-to-left.
- **Captions** show one sentence at a time (the one being spoken), in a fixed box on phones, so they no longer
  stack, get cut off or push the layout around.
- **Listen button** under each chat answer now uses the same natural server voice as voice mode (the whole
  answer in one go, saved as `static/tts/<id>.mp3`); the browser's own voice is only the fallback.
- **Typos**: the AI is told to read messages generously ("how for a can you fight" = "how far can you fly").
  The offline backup brain fixes common typos too (`offline.py`, `TYPOS` + closest-keyword matching), and
  its footer is now a small "(📡 offline backup brain)" - the technical reason is printed in the terminal.
- Tests: `python tests/run_tests.py --backend offline` -> 21/21 (4 new: typos + an Arabic question).


## QA fixes (Oct 2026)
- **No made-up facts:** the fact-checker now accepts a number only together with what it measures ("15 m" isn't accepted just
  because "15" appears in "15 November"). The bot says height wasn't measured (it gives the ~R/4 theoretical maximum only if you ask
  for an estimate, clearly labelled), never claims competition-day facts before the competition, and doesn't say tests proved 45°
  best (every test used 45°). Checked by `tests/test_regressions.py`.
- Blank / spaces-only messages are ignored; quick double taps on the suggestion chips are queued (both get answered); questions are
  capped at 500 characters; the Settings "AI brain" choice only affects your own chat.
- iPhone: the test-results table scrolls sideways inside the bubble; the welcome logo no longer touches the top bar.
- Voice mode: the team name comes from `rocket_info.yaml`; long captions stay above the horizon line.
- The old Expo/React Native app (`mobile/`, `api.py`, `app_host.py`) was removed from the project, along with fastapi/uvicorn.

---

## "What if" calculator + auto charts (Oct 2026)

**Ask "what if" and get a real calculation.** Examples that work (typed or spoken, English or Arabic):

| You ask | AquaFalcon answers (with the example data) |
|---|---|
| what if we used 50 psi? | about **18.1 m** - straight-line fit of distance vs pressure from the 500 mL launches (40-60 psi) |
| what if we used 70 psi? | about **26 m**, flagged *"outside what we tested (40-60 psi), so this is a rough guess"* + a safety line (burst limit never measured) |
| what if 400 mL water? | about **20.1 m** - curve through the launches; the data peaks around **520 mL ≈ a third of the bottle** |
| what about 30 degrees? | about **19 m** - projectile physics (range ∝ sin 2θ) scaled from our 22.1 m average at 45°, flagged because we only launched at 45° |
| what about 700 mL at 60 psi? | "We actually tested that: **17 m** (test 4)" - a real measurement, not an estimate |
| what if we pumped 150 psi? | refuses to put a number on it (way beyond what we tested, bottle could burst) |
| شو لو استخدمنا 70 psi؟ | the same estimate, in Arabic |

How it works (`whatif.py`, about 300 lines, no AI involved):
1. **Pressure:** least-squares straight line of distance vs pressure, using the tests at your usual water and angle (from `launch:` in the YAML).
2. **Water:** every test is first scaled to your usual pressure using that line, then a parabola is fitted through distance vs water. Its peak = the best amount of water.
3. **Angle:** projectile physics, range ∝ sin(2 × angle), scaled to your measured distance at the angle you tested (drag ignored).
4. Exactly-tested settings return the real measured distance. Anything outside the tested range is labelled *rough guess*. Every answer says it's an **estimate from our test data** and states its assumption in one line.
5. In voice mode the answer is one or two short spoken sentences. The fact-checker accepts the calculator's own numbers, even when the AI repeats them in a follow-up.

**Auto charts.** Ask "show me a graph", "chart distance vs pressure", "ورجيني رسم بياني" or "show me your test results" and a chart appears inside the answer bubble, with tabs for *Per test* (best flight highlighted), *vs pressure* and *vs water* (dashed line = the calculator's fitted trend). What-if answers get the matching chart with the estimate marked in orange. The charts stretch to the bubble width, so they're readable on an iPhone. In voice mode AquaFalcon says "I put a chart in the chat" and the chart is waiting when you close voice mode.

**Real data = automatic update.** Both features read `test_results:` in `rocket_info.yaml` every time. Paste in your real launches (keep the same columns: `water_ml`, `pressure_psi`, `angle_deg`, `distance_m`) and every estimate, assumption line, tested range and chart updates by itself. Tip: tests at **2+ different pressures** and **3+ different water amounts** give the best fits. If you also test other angles, the calculator will mark those as tested.


## Launch Lab - interactive flight simulator (Oct 2026)
A separate page (the chat page is unchanged): tap the small rocket button in the top bar.
* Slide the water, pressure, launch angle and empty mass, pick bottle size, fins, nose and nozzle, press **Launch**:
  the rocket flies on screen (slow motion while the water pushes), with live height/speed charts.
* **Best water amount** tries every water level (2-80 %) and marks the best one; "Use it" sets it and launches.
* **Ask AquaFalcon why** goes back to the chat with your setup as a question (numbers re-computed in Python).
* The model (launchlab.py, same maths in lab_component/physics.js): Bernoulli water thrust with the air expanding
  adiabatically, then an air blast (compressible nozzle flow), then a coast with gravity + air drag. It is IDEAL
  (no wind, wobble or leaks), so real launches fly shorter. Start values come from rocket_info.yaml.
* Tests: `python tests/test_launchlab.py` (more pressure = higher, ~30 % water is best, 0 psi = no flight,
  JavaScript and Python give the same numbers).
