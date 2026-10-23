
/* On streamlit.app, reopen with ?embed=true so Streamlit's floating crown/profile badges don't cover our buttons */
try { (function(){ var T = window.top, L = T.location;
  if (/\.streamlit\.app$/.test(L.hostname) && !/[?&]embed=true/.test(L.search)) {
    L.replace(L.pathname + (L.search ? L.search + "&" : "?") + "embed=true" + L.hash); } })(); } catch (e) {}
/* AquaFalcon voice mode - runs in the main page (loaded by voice_component/index.html).
   Free browser APIs only:
     - SpeechRecognition (Chrome, Edge, iPhone Safari 14.5+) turns your voice into text
     - the answer is read out loud by a natural neural voice the server makes (tts.py, one mp3 per sentence,
       the first sentence plays while the rest are made); speechSynthesis is only a last-resort backup
     - getUserMedia + an AnalyserNode measure loudness (orb animation, barge-in, silence detection)
   Fallback when the browser has no SpeechRecognition (e.g. Firefox): MediaRecorder records the
   question and the server transcribes it with the free Groq/Gemini key (backends.transcribe). */
(function () {
  if (window.AFVoice) return;
  var W = window, D = document;
  var SR = W.SpeechRecognition || W.webkitSpeechRecognition;
  var synth = W.speechSynthesis;
  var IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  // Home-screen app ("Add to Home Screen") = standalone display mode
  var STANDALONE = navigator.standalone === true || !!(W.matchMedia && W.matchMedia("(display-mode: standalone)").matches);
  var QS = W.location.search || "";
  var DEBUG = /[?&]debug=1\b/.test(QS);                 // ?debug=1 shows a small diagnostics line (iPhone)
  // iPhone/iPad path: Apple's webkitSpeechRecognition is unreliable on iPhone and often missing or silent in
  // home-screen apps, and it fights the speaker for the audio. So on iPhone voice mode records you itself
  // (mic -> Web Audio), detects when you start/stop talking from the loudness, and the server transcribes
  // the clip. Answers play as server mp3s through the <audio> player unlocked by the opening tap, with the
  // mic switched off while it talks. (?iossr=1 = old recognizer path, ?iosvoice=browser = phone's own voice)
  var IOS_VAD = IOS && !/[?&]iossr=1\b/.test(QS);
  // Natural server voice on every device (?voice=browser = the browser's own voice, the old robotic one)
  var SRV_VOICE = !/[?&](ios)?voice=browser\b/.test(QS);
  var IOS_SRV_VOICE = IOS && SRV_VOICE;
  var KEEPMIC = /[?&]keepmic=1\b/.test(QS);              // experiment: mute mic tracks instead of releasing them
  var LITE = IOS;                                         // lighter animation on iPhone/iPad

  // ---- tunable numbers ----
  // End of your turn = this long with NO new words. iPhone's recognizer stops at every short pause,
  // so on iPhone we never trust its "end" - we keep restarting it and add the words up instead.
  var SILENCE_MS = IOS ? 1300 : 1200;
  var SHORT_WAIT = 1.6;       // a one-word question ("hello?") waits 1.6x longer, in case you go on
  var REC_SILENCE_MS = 1200;  // same idea for the record-and-transcribe fallback (level meter)
  var SPEAK_START_MS = 1200;  // browser voice silent this long -> use the server voice instead
  var SRV_WAIT_MS = 6500;     // a sentence's natural-voice mp3 not here this long -> browser voice for the rest
  var BARGE_MS = 250;         // you must talk this long over the bot to interrupt it
  var THINK_TIMEOUT = 45000;  // give up waiting for an answer after this
  // iPhone recorder (voice activity detection on the mic loudness)
  var VAD_END_MS = 1100;   // pause allowed mid-sentence (stutters, "umm")
  var VAD_END_SHORT_MS = 1700;  // longer grace while you have only said a word or two      // this long quiet after you talked = end of your turn
  var VAD_MIN_MS = 400;       // shorter than this = a click/cough, ignored
  var VAD_MAX_MS = 30000;     // longest question
  var VAD_IDLE_MS = 45000;    // nobody talks this long -> mic off, "Tap to talk"
  var PREROLL_MS = 450;       // keep this much audio from just before you started (first syllable)
  var MIC_TIMEOUT = 8000;     // the mic must start within this

  var send = null, args = {};
  var state = "closed";       // closed | listening | thinking | speaking | muted | tap
  var engine = IOS_VAD ? "vad" : (SR ? "speech" : "record");
  // Language: "auto" (default) = English, Arabic or a mix, detected by the server's speech-to-text. Browser
  // recognizers can only listen for ONE language, so in auto mode every device records you itself (the same
  // record -> server transcribe path as iPhone). Picking English or عربي in settings uses the browser's own
  // recognizer for that one language (desktop only; iPhone always records).
  var AUTO_OK = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && (W.AudioContext || W.webkitAudioContext));
  function chooseEngine() {
    if (IOS_VAD) return "vad";
    if (lang === "auto" && AUTO_OK && args.can_transcribe) return "vad";
    return SR ? "speech" : "record";
  }
  var muted = false, lang = "auto", voiceName = localStorage.getItem("afv-voice") || "";
  var rec = null, recOn = false, heardText = "", interimText = "", lastHeardAt = 0, silenceTimer = null;
  var restartTries = 0, committed = "", sessFinal = "", sessInter = "", holdShown = false, fx = null, needsKick = false, closing = false;
  var srvClips = [], srvIdx = 0, srvPlaying = false, srvDone = false, spokenBefore = "";
  var pendingId = null, thinkTimer = null, pollTimer = null;
  var spokenUpTo = 0, streamDone = false, queue = [], speakingNow = false, speakToken = 0, uttStart = 0, cutAtFact = false;
  var botSentences = [], botIdx = -1;
  var stream = null, actx = null, analyser = null, buf = null, level = 0, noiseFloor = 0.01, echoFloor = 0.02, loudSince = 0;
  var mr = null, chunks = [], recHeard = false, recStart = 0, recLoudAt = 0;
  var ui = {}, greetDone = null, press = 0;
  // iPhone backup voice: if the browser voice stays silent, answers come from the server as mp3
  var serverVoice = SRV_VOICE, srvFellBack = false, srvWaitTimer = null, lateTts = false, lastRaw = "", player = null, pseudoLvl = 0;
  var BASE = ((D.currentScript && D.currentScript.src) || "").replace(/[^\/?#]*([?#].*)?$/, "");
  var SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

  function $(sel) { return ui.root.querySelector(sel); }
  // opening lines: one is picked at random each time voice mode opens (never the same twice in a row)
  var GREETINGS = [
    "Do you have any questions about the project?",
    "Ask me anything about the project.",
    "What would you like to know about our water rocket?",
    "Got a question about the rocket or the launch?",
    "Hi! What do you want to know about the project?",
    "Ask me about our rocket design, testing or results.",
    "Curious how we built the rocket? Ask away.",
    "Want to know how far our rocket flew?",
    "Ask me how we tested the rocket.",
    "Anything you'd like to know about the team or the design?",
    "What should I tell you about our water rocket?",
    "Questions about the fins or the nose cone? Go ahead.",
    "Ready when you are. What do you want to know about the project?"
  ];
  var lastGreet = -1;
  function pickGreeting() {
    var i = Math.floor(Math.random() * GREETINGS.length);
    if (i === lastGreet) i = (i + 1) % GREETINGS.length;
    return (lastGreet = i);
  }

  // ---- soft "got it" sound when your question is sent (Web Audio, unlocked by the opening tap)
  function fxUnlock() {
    try {
      if (!fx) { var AC = W.AudioContext || W.webkitAudioContext; if (AC) fx = new AC(); }
      if (fx && fx.state === "suspended") fx.resume();
    } catch (e) { fx = null; }
  }
  function ack() {
    if (ui.core) { ui.core.classList.remove("afv-ack"); void ui.core.offsetWidth; ui.core.classList.add("afv-ack"); }
    try {
      if (!fx) return;
      if (fx.state === "suspended") fx.resume();
      var t = fx.currentTime + 0.01;
      [[660, 0], [990, 0.085]].forEach(function (n) {      // two quick soft notes, like a water drop
        var o = fx.createOscillator(), g = fx.createGain();
        o.type = "sine"; o.frequency.setValueAtTime(n[0], t + n[1]);
        o.frequency.exponentialRampToValueAtTime(n[0] * 1.25, t + n[1] + 0.08);
        g.gain.setValueAtTime(0.0001, t + n[1]);
        g.gain.exponentialRampToValueAtTime(0.07, t + n[1] + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t + n[1] + 0.14);
        o.connect(g); g.connect(fx.destination); o.start(t + n[1]); o.stop(t + n[1] + 0.16);
      });
    } catch (e) {}
  }
  var ICON = {
    wave: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.8C9 6.6 6.5 9.6 6.5 13.2a5.5 5.5 0 0 0 11 0c0-3.6-2.5-6.6-5.5-10.4z"/><path d="M9.2 14.2c1-.9 1.8-.9 2.8 0s1.8.9 2.8 0"/></svg>',
    caps: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3.5"/><path d="M7 11h4M13 11h4M7 15h7"/></svg>',
    sliders: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
    kbd: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6" width="19" height="12" rx="3"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    micoff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 10V6a3 3 0 0 0-5.7-1.3"/><path d="M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.7 3M12 18v3"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>',
    // AquaFalcon mark: a bottle rocket with a falcon wing, riding a water drop
    mark: '<svg viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="afvMk" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7dd3fc"/><stop offset="1" stop-color="#2563eb"/></linearGradient></defs>' +
      '<rect x="0.5" y="0.5" width="31" height="31" rx="9" fill="#0f2257" stroke="url(#afvMk)" stroke-width="1"/>' +
      '<path d="M3.6 19.6c3.4-3.6 7-4.6 10.3-4.1l-.4 3.4c-3.2-.6-6.4-.4-9.9.7z" fill="#7dd3fc" opacity=".9"/>' +
      '<path d="M5.2 22.3c2.8-1.6 5.6-2.2 8.4-2l-.2 2.2c-2.7-.3-5.3-.3-8.2-.2z" fill="#7dd3fc" opacity=".55"/>' +
      '<path d="M18.5 4.2c3 2.4 4.6 6 4.6 10.2v6.4h-9.2v-6.4c0-4.2 1.6-7.8 4.6-10.2z" fill="#fff"/>' +
      '<path d="M13.9 15.6l-2.6 3.3v2.9l2.6-1.1zM23.1 15.6l2.6 3.3v2.9l-2.6-1.1z" fill="#93c5fd"/>' +
      '<circle cx="18.5" cy="11.6" r="1.9" fill="#2563eb"/>' +
      '<path d="M18.5 22.6c-1.3 1.7-2.2 2.8-2.2 3.9a2.2 2.2 0 0 0 4.4 0c0-1.1-.9-2.2-2.2-3.9z" fill="#38bdf8"/></svg>'
  };


  // ------------------------------------------------------------ UI
  function setTeam() {    // "Voice link · <team name from rocket_info.yaml>"
    var el = ui.root && ui.root.querySelector(".afv-team");
    if (el) el.textContent = "Voice link" + (args.team ? " · " + args.team : "");
  }
  function build() {
    var name = args.name || "AquaFalcon";
    var root = D.createElement("div"); root.id = "afv"; root.setAttribute("data-state", "closed");
    root.innerHTML =
      '<div class="afv-sky" aria-hidden="true"><i class="afv-stars s1"></i><i class="afv-stars s2"></i><i class="afv-horizon"></i></div>' +
      '<div class="afv-top"><button class="afv-btn afv-menu" aria-label="Captions on/off" title="Captions on/off">' + ICON.caps + '</button>' +
      '<div class="afv-brand">' + ICON.mark + '<div><div class="afv-title"></div><div class="afv-sub"><i></i><span class="afv-team"></span></div></div></div>' +
      '<button class="afv-btn afv-set" aria-label="Voice settings" title="Voice settings">' + ICON.sliders + '</button></div>' +
      '<div class="afv-sheet"><label>Language you speak</label><div class="afv-seg"><button data-l="auto">Auto</button><button data-l="en-US">English</button><button data-l="ar-JO">عربي</button></div>' +
      '<label>Voice</label><select class="afv-voice"></select><div class="afv-note"></div></div>' +
      '<div class="afv-stage"><div class="afv-core">' +
        '<svg class="afv-gauge" viewBox="0 0 120 120" aria-hidden="true"><circle class="afv-g-track" cx="60" cy="60" r="56"/><circle class="afv-g-fill" cx="60" cy="60" r="56"/><circle class="afv-g-ticks" cx="60" cy="60" r="51"/></svg>' +
        '<i class="afv-ripple"></i><i class="afv-ripple r2"></i><i class="afv-ripple r3"></i>' +
        '<button class="afv-orb" aria-label="Tap to talk or interrupt"><i class="afv-orb-water"></i><canvas></canvas></button></div>' +
      '<div class="afv-status"></div>' + (IOS_VAD ? '<div class="afv-meter" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>' : '') + '</div>' +
      '<div class="afv-caps"><div class="afv-cap afv-cap-you" dir="auto"></div><div class="afv-cap afv-cap-bot" dir="auto"></div></div>' +
      '<div class="afv-bottom"><button class="afv-btn afv-mute" aria-label="Mute microphone" title="Mute microphone">' + ICON.mic + '</button>' +
      '<div class="afv-pill"><span class="afv-kbd">' + ICON.kbd + '</span>' +
      '<input class="afv-input" type="text" enterkeyhint="send" autocomplete="off" placeholder="Ask a question…"></div>' +
      '<button class="afv-btn afv-close" aria-label="End voice mode" title="End voice mode">' + ICON.x + '<span>End</span></button></div>';
    D.body.appendChild(root);
    ui.root = root; setTeam(); ui.orb = $(".afv-orb"); ui.canvas = $("canvas"); ui.core = $(".afv-core"); ui.gauge = $(".afv-g-fill"); ui.status = $(".afv-status");
    ui.you = $(".afv-cap-you"); ui.bot = $(".afv-cap-bot"); ui.input = $(".afv-input"); ui.mute = $(".afv-mute");
    ui.sheet = $(".afv-sheet"); ui.voiceSel = $(".afv-voice");
    if (LITE) root.classList.add("afv-lite");
    ui.meter = $(".afv-meter"); ui.meterBars = ui.meter ? [].slice.call(ui.meter.children) : [];
    if (IOS && DEBUG) { ui.dbg = D.createElement("div"); ui.dbg.className = "afv-debug"; root.appendChild(ui.dbg); }
    $(".afv-title").textContent = name;

    ui.orb.addEventListener("click", onOrbTap);
    $(".afv-close").addEventListener("click", close);
    ui.mute.addEventListener("click", toggleMute);
    $(".afv-menu").addEventListener("click", function () { root.classList.toggle("nocaps"); });
    $(".afv-set").addEventListener("click", function () { fillVoices(); ui.sheet.classList.toggle("open"); });
    $(".afv-kbd").addEventListener("click", function () { ui.input.focus(); });
    ui.root.querySelectorAll(".afv-seg button").forEach(function (b) {
      b.addEventListener("click", function () { setLang(b.getAttribute("data-l")); });
    });
    ui.voiceSel.addEventListener("change", function () { voiceName = ui.voiceSel.value; localStorage.setItem("afv-voice", voiceName); speakPreview(); });
    ui.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && ui.input.value.trim()) { e.preventDefault(); var t = ui.input.value.trim(); ui.input.value = ""; ui.input.blur(); interruptSpeech(); stopListening(); submit({ text: t, typed: true }); }
    });
    D.addEventListener("keydown", function (e) { if (e.key === "Escape" && state !== "closed") close(); });
    setLang(localStorage.getItem("afv-lang2") || "auto");   // (new key: everyone starts on Auto)
    requestAnimationFrame(frame);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function setLang(l) {
    lang = l; localStorage.setItem("afv-lang2", l);
    ui.root.querySelectorAll(".afv-seg button").forEach(function (b) { b.classList.toggle("sel", b.getAttribute("data-l") === l); });
    var want = state === "closed" ? engine : chooseEngine();
    if (want !== engine) {           // switching between Auto (record) and one-language (browser recognizer)
      var was = state === "listening"; stopListening(); engine = want;
      if (was) setTimeout(function () { if (state === "listening") startListening(true); }, 250);
      return;
    }
    if (recOn) { stopRecognition(); if (state === "listening") setTimeout(startListening, 250); }
  }

  function setState(s, msg) {
    state = s; holdShown = false; if (ui.root) { ui.root.setAttribute("data-state", s); ui.root.classList.remove("afv-hold"); }
    var text = msg != null ? msg : ({
      listening: "Listening…", thinking: "Thinking…", speaking: IOS ? "Responding… · Tap to interrupt" : "Responding…",
      greeting: "Tap to interrupt", starting: "Starting the mic…",
      muted: "Mic muted · Tap to talk", tap: "Tap to talk", closed: ""
    })[s] || "";
    if (ui.status) ui.status.textContent = text;
  }

  // launcher button next to the chat box
  var autoTried = false;
  function placeLauncher() {
    var b = D.getElementById("afv-launch");
    if (!b) {
      b = D.createElement("button"); b.id = "afv-launch"; b.type = "button";
      b.setAttribute("aria-label", "Voice mode"); b.title = "Voice mode"; b.innerHTML = ICON.wave;
      b.addEventListener("click", open); D.body.appendChild(b);
    }
    var ci = D.querySelector('[data-testid="stChatInput"]');
    if (!ci || state !== "closed") { b.style.display = "none"; return; }
    if (!autoTried) { autoTried = true; if (/[?&]voice=1\b/.test(W.location.search)) { openPassive(); return; } }
    D.body.classList.add("afv-has-launch");
    var r = ci.getBoundingClientRect();
    if (!r.width) { b.style.display = "none"; return; }
    var h = Math.min(r.height, 56);
    b.style.display = "flex";
    b.style.left = Math.round(r.right + 8) + "px";
    b.style.top = Math.round(r.bottom - h / 2 - 22) + "px";
  }

  // ------------------------------------------------------------ open / close
  function open() {
    if (!ui.root) build();
    if (SRV_VOICE) serverVoice = true;
    if (IOS) { D.body.classList.add("afv-lite-open"); var sf = $(".afv-safari"); if (sf) sf.remove(); }
    needsKick = false; closing = false; ui.root.classList.remove("closing");
    fxUnlock();
    D.body.style.overflow = "hidden";
    ui.root.classList.add("open"); ui.sheet.classList.remove("open");
    ui.you.textContent = ""; ui.bot.textContent = "";
    muted = false; ui.mute.classList.remove("on"); ui.mute.innerHTML = ICON.mic;
    placeLauncher();
    // Greeting, spoken inside this tap: on iPhone the first speak() must happen in a tap, so this
    // also unlocks the voice for the answers. The mic starts once the greeting is over.
    // unlock an <audio> player inside this tap too (used if the browser voice turns out silent)
    try { if (!player) { player = new Audio(); player.setAttribute("playsinline", ""); player.preload = "auto"; }
      player.src = SILENT; var pp = player.play(); if (pp && pp.catch) pp.catch(function () {}); } catch (e) {}
    try { synth.cancel(); } catch (e) {}
    fillVoices();
    var gi = pickGreeting(), greet = GREETINGS[gi];
    metrics.submitAt = performance.now(); metrics.firstAudioMs = null;   // greeting latency (until the 1st question)
    ui.bot.textContent = greet;
    function goListen() {
      if (state === "closed") return;
      engine = chooseEngine();
      if (engine === "vad" && !args.can_transcribe) engine = SR ? "speech" : "vad";   // no AI key: iPhone's own recognizer is all we have
      if (engine === "vad") {
        if (!args.can_transcribe) { setState("tap", "Voice input needs the app's free AI key. Type below - I'll still answer out loud."); return; }
        startListening(true); return;
      }
      if (!SR && !args.can_transcribe) {
        setState("tap", "This browser can't do voice input. Type below - I'll still answer out loud.");
        return;
      }
      setState("starting");
      if (IOS && engine === "speech") { startListening(true); return; }   // iPhone: no extra mic stream (keeps the speaker loud)
      startMic().then(function () { startListening(true); });
    }
    greetDone = goListen;
    if (IOS_VAD) {
      // iPhone: ask for the mic inside this tap (one permission prompt), then switch it off so the greeting
      // plays loud through the unlocked player, then listen.
      setState("greeting", "Starting the mic…");
      var gfired = false;
      var gdone = function () { if (gfired) return; gfired = true; greetDone = null; if (state === "greeting") goListen(); };
      greetDone = gdone;
      var needMic = !!args.can_transcribe;
      (needMic ? iosMicStart() : Promise.resolve(true)).then(function (ok) {
        if (state !== "greeting" || gfired) return;
        if (!ok) { gfired = true; greetDone = null; iosMicFailed(true); return; }
        iosMicStop();
        if (IOS_SRV_VOICE && BASE) playServer(BASE + "greet" + gi + ".mp3?v=" + (args.version || "1"), gdone);
        else if (synth) speakNow(greet, gdone, greetSilent);
        else gdone();
        setTimeout(gdone, 9000);   // never hang on the greeting
      });
      return;
    }
    if (serverVoice && BASE) {     // natural voice: pre-made greeting mp3 (browser voice only if it can't play)
      setState("greeting"); uttStart = performance.now();
      var dfired = false;
      var dDone = function () { if (dfired) return; dfired = true; if (state === "greeting") { greetDone = null; goListen(); } };
      greetDone = dDone;
      playServer(BASE + "greet" + gi + ".mp3?v=" + (args.version || "1"), dDone, function () {
        if (state !== "greeting") return;
        if (synth) { try { speakNow(greet, dDone); } catch (e) { dDone(); } } else dDone();
      });
      setTimeout(function () { if (state === "greeting" && !dfired && !speakingNow) dDone(); }, 15000);   // never hang
      return;
    }
    if (synth) {
      setState("greeting"); uttStart = performance.now();
      try { speakNow(greet, function () { if (state === "greeting") { greetDone = null; goListen(); } }, greetSilent); }
      catch (e) { goListen(); }
    } else goListen();
  }

  // End: the water core launches up like the rocket, the stars streak down and the screen fades to
  // the chat underneath (~1 s, CSS transforms/opacity only); only then is voice mode really closed.
  function close() {
    if (!ui.root || closing || state === "closed") return;
    stopListening(); interruptSpeech(); stopMic();
    clearTimeout(thinkTimer); clearInterval(pollTimer); pendingId = null; needsKick = false;
    var reduce = W.matchMedia && W.matchMedia("(prefers-reduced-motion: reduce)").matches;
    closing = true; setState("leaving", ""); D.body.classList.remove("afv-lite-open");
    // iPhone skipped the page redraw after each spoken answer: ask for one now (an empty "question" = just redraw)
    if (IOS && send && askedSinceOpen) { askedSinceOpen = false; send({ id: "r" + Date.now().toString(36), refresh: 1 }); }
    ui.root.classList.add("closing");
    setTimeout(function () {
      closing = false;
      ui.root.classList.remove("open", "closing");
      D.body.style.overflow = "";
      setState("closed"); placeLauncher();
    }, reduce ? 320 : 720);
  }
  // home-screen app opened with ?voice=1: show voice mode at once; the first tap on the core starts it
  // (iPhone only allows the mic and the voice to start inside a tap)
  function openPassive() {
    if (!ui.root) build();
    D.body.style.overflow = "hidden";
    ui.root.classList.add("open"); needsKick = true; if (IOS) D.body.classList.add("afv-lite-open");
    ui.you.textContent = ""; ui.bot.textContent = "";
    setState("tap", "Tap the water core to start");
  }

  function toggleMute() {
    muted = !muted;
    ui.mute.classList.toggle("on", muted); ui.mute.innerHTML = muted ? ICON.micoff : ICON.mic;
    if (muted) { stopListening(); if (state === "listening") setState("muted"); }
    else if (state === "muted" || state === "tap") { startListening(true); }
  }

  function onOrbTap() {
    ui.sheet.classList.remove("open");
    if (IOS) fxUnlock();     // a tap is the moment iPhone lets a sleeping audio context wake up again
    if (state === "greeting") { interruptSpeech(); var g = greetDone; greetDone = null; if (g) g(); return; }
    if (state === "speaking") { interruptSpeech(); startListening(true); return; }
    if (needsKick) { open(); return; }   // opened from the home-screen app (?voice=1): this tap starts it
    if (state === "listening" && engine === "vad") { if (ios.active && ios.speechMs >= 250) iosFinish(); return; }   // tap = send now
    if (state === "listening") { if (currentText()) finishListening(); return; }   // tap = send now
    if (state === "muted" || state === "tap") { if (muted) toggleMute(); else startListening(true); return; }
  }

  // ------------------------------------------------------------ microphone level (orb + barge-in)
  function startMic() {
    if (stream) return Promise.resolve();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.resolve();
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(function (s) {
        stream = s;
        try {
          var AC = W.AudioContext || W.webkitAudioContext; actx = new AC();
          if (actx.state === "suspended") actx.resume();
          var src = actx.createMediaStreamSource(s); analyser = actx.createAnalyser(); analyser.fftSize = 1024;
          buf = new Float32Array(analyser.fftSize); src.connect(analyser);
        } catch (e) { analyser = null; }
      })
      .catch(function (e) {
        if (!SR) setState("tap", "Microphone blocked. Allow the mic for this site, then tap the water core.");
      });
  }
  function stopMic() {
    if (IOS_VAD || ios.stream) iosMicStop(true);
    try { if (mr && mr.state !== "inactive") mr.stop(); } catch (e) {}
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null; analyser = null;
    try { if (actx) actx.close(); } catch (e) {}
    actx = null;
  }
  function readLevel() {
    if (engine === "vad") { pseudoLvl = Math.max(ios.rms, pseudoLvl * 0.85); return ios.proc ? pseudoLvl : 0; }
    if (!analyser) { pseudoLvl *= 0.93; return pseudoLvl; }   // iPhone (no mic stream): words arriving = "volume"
    analyser.getFloatTimeDomainData(buf);
    var sum = 0; for (var i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    return Math.sqrt(sum / buf.length);
  }


  // ------------------------------------------------------------ iPhone/iPad: record + voice activity detection
  // One mic stream feeds the AudioContext unlocked by the opening tap (a context made outside a tap stays
  // silent on iPhone, which is why the old version "didn't hear" you after the first answer). Each ~43 ms block
  // of audio gives a loudness (RMS): loud for ~90 ms = you started (we keep ~0.45 s from just before, so the
  // first syllable isn't lost); 1.5 s quiet after at least 0.4 s of talking = you're done. The clip is sent as
  // a small 16 kHz WAV and the server transcribes it (backends.transcribe). The mic is switched off while it
  // talks (so the answer is loud) and switched back on to listen.
  var ios = { stream: null, src: null, proc: null, sink: null, rate: 48000, nf: 0.004, rms: 0,
    pre: [], preMs: 0, cap: [], capMs: 0, atLoudMs: 0, active: false, speechMs: 0, loudRun: 0, lastLoud: 0,
    listenAt: 0, lastPcm: 0, acquiring: null, err: "", acqMs: 0, fails: 0, clipMs: 0, sentAt: 0, rtt: 0, stalledAt: 0 };
  function micLive() { return !!(ios.stream && ios.stream.getAudioTracks().some(function (t) { return t.readyState === "live"; })); }
  function iosMicStart() {
    if (micLive() && ios.proc) return Promise.resolve(true);
    if (micLive()) { ios.stream.getAudioTracks().forEach(function (t) { t.enabled = true; }); iosWire(); return Promise.resolve(!!ios.proc); }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { ios.err = "no getUserMedia"; return Promise.resolve(false); }
    if (ios.acquiring) return ios.acquiring;
    var t0 = performance.now();
    var gum = navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    var to = new Promise(function (_, rej) { setTimeout(function () { rej({ name: "Timeout" }); }, MIC_TIMEOUT); });
    ios.acquiring = Promise.race([gum, to]).then(function (s) {
      ios.acquiring = null; ios.stream = s; ios.acqMs = Math.round(performance.now() - t0); ios.err = ""; ios.fails = 0;
      iosWire(); return !!ios.proc;
    }, function (e) {
      ios.acquiring = null; ios.err = (e && (e.name || e.message)) || String(e); ios.fails++;
      gum.then(function (s) { if (!ios.stream) s.getTracks().forEach(function (t) { t.stop(); }); }, function () {});
      return false;
    });
    return ios.acquiring;
  }
  function iosWire() {
    iosUnwire();
    fxUnlock();
    if (!fx || !ios.stream) { ios.err = ios.err || "no AudioContext"; return; }
    try {
      if (fx.state !== "running") fx.resume();
      ios.rate = fx.sampleRate || 48000;
      ios.src = fx.createMediaStreamSource(ios.stream);
      var n = (fx.createScriptProcessor || fx.createJavaScriptNode).call(fx, 2048, 1, 1);
      n.onaudioprocess = onPcm;
      ios.sink = fx.createGain(); ios.sink.gain.value = 0;
      ios.src.connect(n); n.connect(ios.sink); ios.sink.connect(fx.destination);
      ios.proc = n; ios.lastPcm = performance.now(); ios.stalledAt = 0;
    } catch (e) { ios.err = "wire: " + (e.message || e); iosUnwire(); }
  }
  function iosUnwire() {
    try { if (ios.proc) { ios.proc.onaudioprocess = null; ios.proc.disconnect(); } } catch (e) {}
    try { if (ios.src) ios.src.disconnect(); } catch (e) {}
    try { if (ios.sink) ios.sink.disconnect(); } catch (e) {}
    ios.proc = ios.src = ios.sink = null;
  }
  function iosMicStop(full) {
    iosUnwire(); ios.rms = 0;
    if (ios.stream) {
      if ((KEEPMIC || !IOS) && !full) ios.stream.getAudioTracks().forEach(function (t) { t.enabled = false; });
      else { ios.stream.getTracks().forEach(function (t) { t.stop(); }); ios.stream = null; }
    }
  }
  function vadReset() { ios.pre = []; ios.preMs = 0; ios.cap = []; ios.capMs = 0; ios.active = false; ios.speechMs = 0; ios.loudRun = 0; ios.atLoudMs = 0; }
  function onPcm(e) {
    var d = e.inputBuffer.getChannelData(0), sum = 0;
    for (var i = 0; i < d.length; i++) sum += d[i] * d[i];
    var rms = Math.sqrt(sum / d.length), now = performance.now(), ms = d.length / ios.rate * 1000;
    ios.rms = rms; ios.lastPcm = now; ios.stalledAt = 0;
    if (state !== "listening" || muted) return;
    var startT = Math.max(0.012, ios.nf * 3.2), keepT = Math.max(0.008, ios.nf * 2);
    var copy = new Float32Array(d);
    if (!ios.active) {
      if (rms < startT) ios.nf = Math.min(0.05, Math.max(0.0015, ios.nf * 0.95 + rms * 0.05));
      ios.pre.push(copy); ios.preMs += ms;
      while (ios.pre.length > 1 && ios.preMs - ms > PREROLL_MS) { ios.pre.shift(); ios.preMs -= ms; }
      if (rms > startT) {
        if (++ios.loudRun >= 2) {          // you started talking
          ios.active = true; ios.cap = ios.pre; ios.capMs = ios.preMs; ios.pre = []; ios.preMs = 0;
          ios.speechMs = ms * 2; ios.peak = rms; ios.lastLoud = now; ios.atLoudMs = ios.capMs; lastHeardAt = Date.now();
          ui.you.textContent = "…";
        }
      } else ios.loudRun = 0;
      if (now - ios.listenAt > VAD_IDLE_MS) setTimeout(function () { if (state === "listening" && !ios.active) { iosMicStop(); setState("tap"); } }, 0);
      return;
    }
    ios.cap.push(copy); ios.capMs += ms;
    if (rms > (ios.peak || 0)) ios.peak = rms;
    keepT = Math.max(keepT, (ios.peak || 0) * 0.18);   // noisy room: "quiet" is relative to how loud you spoke
    if (rms > keepT) { ios.lastLoud = now; ios.speechMs += ms; ios.atLoudMs = ios.capMs; lastHeardAt = Date.now(); }
    if (now - ios.lastLoud > (ios.speechMs < 1200 ? VAD_END_SHORT_MS : VAD_END_MS)) {
      if (ios.speechMs >= VAD_MIN_MS) iosFinish();
      else { vadReset(); ui.you.textContent = ""; }      // just a click or a cough: keep listening
    } else if (ios.capMs > VAD_MAX_MS) iosFinish();
  }
  function iosFinish() {
    if (state !== "listening") return;
    var keepMs = Math.min(ios.capMs, ios.atLoudMs + 350);   // drop the trailing silence (smaller, faster upload)
    var chunks = ios.cap, rate = ios.rate; ios.clipMs = Math.round(keepMs);
    vadReset();
    var wav = encodeWav(chunks, rate, keepMs);
    if (DEBUG) ios.lastWav = wav;
    ios.sentAt = performance.now();
    submit({ audio: wav, mime: "audio/wav", ios: IOS ? 1 : 0 });
  }
  function encodeWav(chunks, rate, keepMs) {
    var total = 0; chunks.forEach(function (c) { total += c.length; });
    total = Math.min(total, Math.round(keepMs / 1000 * rate));
    var out = 16000, ratio = rate / out, n = Math.floor(total / ratio);
    var all = new Float32Array(total), o = 0;
    for (var c = 0; c < chunks.length && o < total; c++) { var ch = chunks[c].subarray(0, Math.min(chunks[c].length, total - o)); all.set(ch, o); o += ch.length; }
    var buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    function str(p, s) { for (var i = 0; i < s.length; i++) v.setUint8(p + i, s.charCodeAt(i)); }
    str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVE"); str(12, "fmt "); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, out, true); v.setUint32(28, out * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, n * 2, true);
    var peak = 0.0001;
    for (var p = 0; p < all.length; p++) { var a = Math.abs(all[p]); if (a > peak) peak = a; }
    var gain = Math.min(8, 0.9 / peak);                       // normalise quiet speech
    for (var i = 0; i < n; i++) {
      var s0 = Math.floor(i * ratio), s1 = Math.min(all.length, Math.floor((i + 1) * ratio)), acc = 0;
      for (var j = s0; j < s1; j++) acc += all[j];
      var sm = (s1 > s0 ? acc / (s1 - s0) : 0) * gain;
      sm = Math.max(-1, Math.min(1, sm)); v.setInt16(44 + i * 2, sm < 0 ? sm * 0x8000 : sm * 0x7fff, true);
    }
    var bytes = new Uint8Array(buf), bin = "";
    for (var k = 0; k < bytes.length; k += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(k, k + 0x8000));
    return btoa(bin);
  }
  function iosListen(fromTap) {
    vadReset(); ios.listenAt = performance.now(); ui.you.textContent = "";
    iosMicStart().then(function (ok) {
      if (!ok) { iosMicFailed(fromTap); return; }
      if (state !== "listening" || muted) { iosMicStop(state === "closed"); return; }
      try { if (fx && fx.state !== "running") fx.resume(); } catch (e) {}
      ios.listenAt = performance.now();
    });
  }
  function iosMicFailed(fromTap) {
    if (state === "closed") return;
    var e = ios.err || "";
    if (STANDALONE && (/NotAllowed|Security|no getUserMedia|NotFound|NotReadable/.test(e) || ios.fails >= 2)) { showSafari(e); return; }
    if (/NotAllowed|Security/.test(e)) setState("tap", "Microphone blocked. In Safari tap aA › Website Settings › Microphone › Allow, then tap the core.");
    else setState("tap", "The mic didn't start (" + e + "). Tap the water core to try again.");
  }
  // home-screen app that can't get the mic: offer Safari, where it works
  function showSafari(why) {
    setState("tap", "Mic blocked in the home-screen app");
    var box = $(".afv-safari");
    if (!box) {
      box = D.createElement("div"); box.className = "afv-safari";
      var url = W.location.origin + W.location.pathname + "?voice=1";
      box.innerHTML = '<b>Your iPhone isn’t giving the microphone to the home-screen app.</b>' +
        '<span>Voice mode works in Safari. Open it there (it opens straight into voice mode), or allow the mic in Settings › Safari › Microphone.</span>' +
        '<div class="afv-safari-row"><a class="afv-safari-go" href="x-safari-' + esc(url) + '">Open in Safari</a>' +
        '<button class="afv-safari-copy" type="button">Copy link</button><button class="afv-safari-retry" type="button">Try again</button></div>';
      ui.root.appendChild(box);
      box.querySelector(".afv-safari-copy").addEventListener("click", function () {
        var b = this; try { navigator.clipboard.writeText(url).then(function () { b.textContent = "Copied ✓"; }); } catch (e) { W.prompt("Copy this link:", url); }
      });
      box.querySelector(".afv-safari-retry").addEventListener("click", function () { box.remove(); ios.fails = 0; fxUnlock(); startListening(true); });
    }
    if (DEBUG) ios.err = why || ios.err;
  }
  function dbgLine(now) {
    if (!ui.dbg || now - (ui.dbgAt || 0) < 250) return; ui.dbgAt = now;
    ui.dbg.textContent = "st=" + state + " eng=" + engine + " sa=" + (STANDALONE ? 1 : 0) + " ctx=" + (fx ? fx.state : "-") +
      " mic=" + (micLive() ? "on" : "off") + " lvl=" + ios.rms.toFixed(3) + " nf=" + ios.nf.toFixed(3) +
      " vad=" + (ios.active ? "talk " + Math.round(ios.speechMs) + "ms" : "wait") + " acq=" + ios.acqMs + "ms clip=" + ios.clipMs +
      "ms rtt=" + ios.rtt + "ms srv=" + (serverVoice ? 1 : 0) + (ios.err ? " err=" + ios.err : "");
  }

  // ------------------------------------------------------------ listening
  function startListening(fromTap) {
    if (state === "closed") return;
    if (byePending && !fromTap) { byePending = false; setTimeout(close, 600); return; }   // said bye: end voice mode by itself
    byePending = false;
    if (muted) { setState("muted"); return; }
    heardText = ""; interimText = ""; committed = sessFinal = sessInter = ""; lastHeardAt = 0; clearTimeout(silenceTimer);
    setState("listening");
    if (engine === "vad") iosListen(fromTap);
    else if (engine === "speech") startRecognition(fromTap); else startRecorder();
  }
  function stopListening() {
    clearTimeout(silenceTimer);
    if (engine === "vad") { vadReset(); iosMicStop(); }
    stopRecognition();
    if (mr && mr.state !== "inactive") { mr._discard = true; try { mr.stop(); } catch (e) {} }
  }

  function startRecognition(fromTap) {
    stopRecognition();
    try {
      rec = new SR();
      rec.lang = lang === "auto" ? "en-US" : lang; rec.interimResults = true; rec.maxAlternatives = 1;
      rec.continuous = !IOS;   // iPhone repeats words in continuous mode - restart instead
    } catch (e) { return fallbackToRecorder("no recognizer"); }
    var mine = rec;
    sessFinal = sessInter = "";
    rec.onresult = function (ev) {
      if (mine !== rec) return;
      var fin = "", inter = "";
      for (var i = 0; i < ev.results.length; i++) {
        var t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) fin += t; else inter += t;
      }
      sessFinal = fin; sessInter = inter;
      var before = currentText();
      heardText = join(committed, fin); interimText = inter;
      var all = currentText();
      if (all && all !== before) {          // new words -> restart the patience clock
        lastHeardAt = Date.now(); ui.you.textContent = all; pseudoLvl = 0.035 + Math.random() * 0.03;
        armSilence();
      }
    };
    rec.onerror = function (ev) {
      if (mine !== rec) return;
      var err = ev.error;
      if (err === "no-speech" || err === "aborted") return;  // onend restarts
      if (err === "not-allowed" && !fromTap) { recOn = false; rec = null; setState("tap"); return; }
      if (err === "not-allowed") { recOn = false; rec = null; setState("tap", "Microphone blocked. Allow the mic for this site (Safari: aA › Website Settings › Microphone), then tap."); return; }
      // service-not-allowed (iPhone: Dictation/Siri off), network, audio-capture -> record + server transcription
      fallbackToRecorder(err);
    };
    rec.onend = function () {
      if (mine !== rec) return;
      recOn = false;
      if (state !== "listening") return;
      // The recognizer stopped (iPhone does this at every little pause). That is NOT the end of your
      // turn: keep what it heard and start it again straight away. armSilence() decides when you're done.
      committed = join(committed, join(sessFinal, sessInter)); sessFinal = sessInter = "";
      heardText = committed; interimText = "";
      setTimeout(function () { if (state === "listening" && mine === rec) startRecognition(false); }, 40);
    };
    try { rec.start(); recOn = true; restartTries = 0; }
    catch (e) {   // iPhone sometimes refuses an instant restart - try again a moment later
      recOn = false;
      if (!fromTap && state === "listening" && ++restartTries < 5) setTimeout(function () { if (state === "listening") startRecognition(false); }, 250);
      else setState("tap");
    }
  }
  function stopRecognition() {
    var r = rec; rec = null; recOn = false;
    if (r) { try { r.onresult = r.onend = r.onerror = null; r.abort(); } catch (e) {} }
  }
  function fallbackToRecorder(why) {
    stopRecognition();
    if (args.can_transcribe && W.MediaRecorder) {
      engine = "record";
      startMic().then(function () { if (state === "listening") startRecorder(); });
    } else {
      setState("tap", why === "service-not-allowed"
        ? "Turn on Dictation (Settings › General › Keyboard) to talk - or type below."
        : "Voice input didn't start (" + why + "). Tap to retry, or type below.");
    }
  }

  function join(a, b) { return ((a || "") + " " + (b || "")).replace(/\s+/g, " ").trim(); }
  function currentText() { return join(heardText, interimText); }
  // patience: submit only after SILENCE_MS with no new words (debounced on the last word's time)
  function armSilence() {
    clearTimeout(silenceTimer);
    var txt = currentText();
    if (!txt) return;
    var need = SILENCE_MS * (txt.split(" ").length < 2 ? SHORT_WAIT : 1);
    var quiet = Date.now() - lastHeardAt;
    if (quiet < need) { silenceTimer = setTimeout(armSilence, need - quiet + 20); return; }
    if (txt.replace(/[^\p{L}\p{N}]/gu, "").length < 2) return;   // just a noise ("uh") -> keep listening
    finishListening();
  }

  function finishListening() {
    clearTimeout(silenceTimer);
    if (state !== "listening") return;
    var text = currentText();
    stopRecognition();
    if (!text) { startListening(false); return; }
    submit({ text: text });
  }

  // fallback engine: record, detect silence with the level meter, send audio to the server
  function startRecorder() {
    if (!stream) { startMic().then(function () { if (stream && state === "listening") startRecorder(); else if (state === "listening") setState("tap", "Microphone blocked. Allow it, then tap."); }); return; }
    chunks = []; recHeard = false; recStart = Date.now(); recLoudAt = 0;
    var mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg"].filter(function (m) { return MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m); })[0];
    try { mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream); }
    catch (e) { setState("tap", "Recording isn't supported here. Type below."); return; }
    var me = mr;
    me.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
    me.onstop = function () {
      if (me._discard || state !== "listening") return;
      var blob = new Blob(chunks, { type: me.mimeType || "audio/webm" });
      var fr = new FileReader();
      fr.onload = function () { submit({ audio: String(fr.result).split(",")[1], mime: (blob.type || "audio/webm").split(";")[0] }); };
      fr.readAsDataURL(blob);
    };
    me.start(250);
    ui.you.textContent = "";
  }
  function recorderTick(now) {   // called every animation frame while the recorder runs
    if (!mr || mr.state !== "recording" || state !== "listening") return;
    var thr = Math.max(0.02, noiseFloor * 3);
    if (level > thr) { recHeard = true; recLoudAt = now; lastHeardAt = Date.now(); ui.you.textContent = "…"; }
    if (recHeard && now - recLoudAt > REC_SILENCE_MS && now - recStart > 900) { try { mr.stop(); } catch (e) {} }
    else if (!recHeard && now - recStart > 15000) { mr._discard = true; try { mr.stop(); } catch (e) {} startListening(false); }
  }

  // ------------------------------------------------------------ asking

  // "thanks, bye" / "I'm leaving" / "يلا باي" -> say goodbye, then close voice mode by itself
  var byePending = false;
  function isBye(t) {
    t = (t || "").toLowerCase().replace(/[.,!?؟،]/g, " ").replace(/\s+/g, " ").trim();
    if (!t) return false;
    var words = t.split(" ").length;
    if (/\b(bye|byee+|goodbye|good bye|bye bye|see (you|ya|u)|cya|gotta go|got to go|have to go|i ?(have|need) to (go|leave)|i'?m (leaving|going|off|done)|i am (leaving|going|done)|that'?s (all|it)( for now| for today)?|good ?night|talk (to you )?later|ttyl|later bro|peace out|end (the )?(call|chat|conversation))\b/.test(t)) return words <= 14;
    if (/(مع السلامة|مع السلامه|باي|يلا سلام|سلام عليكم|بدي امشي|لازم امشي|لازم روح|خلصت|خلص هيك|تصبح على خير|ma3 ?el ?salam|ma3 ?salam|yalla bye|yala bye|bdi amshi|lazem rou7)/.test(t)) return words <= 14;
    if (/^(ok(ay)? |alright |cool |great |perfect )?(thanks|thank you|thank u|thx|ty|شكرا|شكراً|يسلمو|يعطيك العافية|merci|shukran|shokran)( (so much|a lot|very much|bro|man|aqua ?falcon|habibi))?$/.test(t)) return true;
    return false;
  }
  var askedSinceOpen = false;
  function submit(q) {
    if (!send) { setState("tap", "Still connecting… try again in a second."); return; }
    askedSinceOpen = true;
    byePending = !!(q.text && isBye(q.text));
    pendingId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    q.id = pendingId; q.lang = lang;
    if (q.text) ui.you.textContent = q.text; else if (q.audio) ui.you.textContent = "…";
    ui.bot.textContent = "";
    spokenUpTo = 0; streamDone = false; queue = []; cutAtFact = false; botSentences = []; botIdx = -1;
    srvReset();
    setState("thinking");
    ack();                         // soft "got it" blip + ripple, so it never feels dead
    if (SRV_VOICE) serverVoice = true;   // a fallback on the last answer doesn't stick: try the natural voice again
    srvFellBack = false;
    metrics.submitAt = performance.now(); metrics.firstAudioMs = null; metrics.textAt = 0; metrics.ev = [];
    if (serverVoice) q.server_tts = true;
    releaseMicForSpeech();
    send(q);
    clearTimeout(thinkTimer);
    thinkTimer = setTimeout(function () {
      if (state === "thinking") { pendingId = null; ui.bot.textContent = "That took too long - ask me again?"; startListening(false); }
    }, THINK_TIMEOUT);
    clearInterval(pollTimer); pollTimer = setInterval(poll, 120);
  }

  function b64(s) {
    try { var bin = atob(s || ""); var bytes = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i); return new TextDecoder().decode(bytes); }
    catch (e) { return ""; }
  }

  // read the hidden box app.py streams the answer into
  function poll() {
    if (!pendingId) { clearInterval(pollTimer); return; }
    var el = D.querySelector(".afv-stream[data-id='" + pendingId + "']");
    if (!el) return;
    var heard = b64(el.getAttribute("data-heard")); if (heard && !byePending && isBye(heard)) byePending = true; if (heard) { ui.you.textContent = heard; if (ios.sentAt) { ios.rtt = Math.round(performance.now() - ios.sentAt); ios.sentAt = 0; } }
    var err = b64(el.getAttribute("data-err"));
    var done = el.getAttribute("data-done") === "1";
    if (err) {
      clearInterval(pollTimer); clearTimeout(thinkTimer); pendingId = null;
      ui.bot.textContent = err; startListening(false); return;
    }
    if (done) { clearInterval(pollTimer); clearTimeout(thinkTimer); pendingId = null; }
    feed(b64(el.getAttribute("data-t")), done, el);
  }

  // take every finished sentence from the streaming answer and queue it for speaking
  function feed(raw, done, el) {
    lastRaw = raw;
    if (serverVoice) return feedServer(raw, done, el);
    if (cutAtFact) { if (done) { streamDone = true; maybeFinished(); } return; }
    while (true) {
      var rest = raw.slice(spokenUpTo);
      var m = rest.match(/[.!?؟。](?=\s|$)|\n/);
      var end;
      if (m && (m.index + 1 < rest.length || done)) end = m.index + 1;
      else if (done && rest.trim()) end = rest.length;
      else break;
      var seg = rest.slice(0, end); spokenUpTo += end;
      var f = seg.search(/🔎|\(📡|_\(📡/);
      if (f >= 0) { seg = seg.slice(0, f); cutAtFact = true; }
      var clean = speakable(seg);
      if (clean) { queue.push(clean); botSentences.push(clean); showBot(); }
      if (cutAtFact) break;
    }
    if (done) streamDone = true;
    if (!speakingNow) speakNext();
    maybeFinished();
  }

  function speakable(s) {
    return s.replace(/\*\*|__|[*_`#>|~]/g, " ").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, "")
      .replace(/^\s*[-•]\s+/gm, "").replace(/-{3,}/g, " ").replace(/\s+/g, " ").trim();
  }

  // captions show the sentence being spoken right now (the whole answer used to be stacked in a 3-line box,
  // so later sentences were cut off / the text jumped around as it grew - the "overlapping subtitles")
  function showBot() {
    var i = botIdx < 0 ? 0 : Math.min(botIdx, botSentences.length - 1);
    var t = botSentences[i] || "";
    if (ui.bot.textContent !== t) ui.bot.textContent = t;
  }

  // ------------------------------------------------------------ speaking
  function pickVoice(l) {
    var vs = synth.getVoices() || [];
    if (voiceName) { var v0 = vs.find(function (v) { return v.name === voiceName; }); if (v0 && v0.lang.slice(0, 2) === l.slice(0, 2)) return v0; }
    var pool = vs.filter(function (v) { return v.lang && v.lang.replace("_", "-").toLowerCase().indexOf(l.slice(0, 2)) === 0; });
    if (l.indexOf("ar") === 0) return pool[0] || null;
    var prefs = [/Samantha/, /Google US English/, /Microsoft (Ava|Aria|Jenny|Emma).*Natural/, /Ava \(Premium|Ava \(Enhanced|Zoe \(Premium|Samantha \(Enhanced/, /Natural|Premium|Enhanced/, /Ava|Allison|Susan|Karen|Daniel|Alex/];
    var us = pool.filter(function (v) { return /en-US/i.test(v.lang.replace("_", "-")); });
    for (var p = 0; p < prefs.length; p++) {
      var hit = us.find(function (v) { return prefs[p].test(v.name); }) || pool.find(function (v) { return prefs[p].test(v.name); });
      if (hit) return hit;
    }
    return us[0] || pool[0] || null;
  }
  function fillVoices() {
    if (!ui.voiceSel) return;
    var vs = (synth.getVoices() || []).filter(function (v) { return /^(en|ar)/i.test(v.lang); });
    var best = pickVoice("en-US");
    ui.voiceSel.innerHTML = '<option value="">Automatic' + (best ? " (" + esc(best.name) + ")" : "") + "</option>" +
      vs.map(function (v) { return '<option value="' + esc(v.name) + '"' + (v.name === voiceName ? " selected" : "") + ">" + esc(v.name + " · " + v.lang) + "</option>"; }).join("");
    $(".afv-note").textContent = chooseEngine() === "vad" ? "Auto: speak English, عربي or a mix of both. Your voice is recorded and the app's free AI turns it into text. Tap the water core to send early or to interrupt." : (SR ? "Speech recognition: built into this browser (free)." : (args.can_transcribe ? "This browser has no speech recognition - your voice is recorded and transcribed by the app's free AI key." : "This browser has no speech recognition - type instead.")) +
      " Tap the orb or just start talking to interrupt." +
      (serverVoice ? " Voice: natural AI voice (Ava), made by the app for free. The list above is only a backup if it can't load." : "");
  }
  if (synth && synth.addEventListener) synth.addEventListener("voiceschanged", fillVoices);
  function speakPreview() {
    interruptSpeech();
    if (serverVoice && BASE) { try { var a = new Audio(BASE + "greet" + pickGreeting() + ".mp3?v=" + (args.version || "1")); a.play().catch(function () {}); return; } catch (e) {} }
    speakNow("Hi, this is my voice.", function () {});
  }
  // numbers for testing/debugging (window.AFVoice.metrics): which engine spoke, how fast the first audio came
  var metrics = { srvPlays: 0, synthPlays: 0, fallbacks: 0, submitAt: 0, firstAudioMs: null, ev: [] };
  function mark(what) { if (metrics.ev.length > 60) metrics.ev.shift(); metrics.ev.push(what + "@" + Math.round(performance.now() - (metrics.submitAt || 0))); }

  var liveUtts = [];   // keep utterances referenced (iPhone Safari drops ones that get garbage-collected)
  function speakNow(text, onDone, onSilent) {
    var u = new SpeechSynthesisUtterance(text);
    var l = /[\u0600-\u06FF]/.test(text) ? "ar" : "en-US";
    var v = pickVoice(l); if (v) { u.voice = v; u.lang = v.lang; } else u.lang = l;
    u.rate = 1.05; u.pitch = 1;
    var token = speakToken, fired = false, started = false;
    function fin() { if (fired || token !== speakToken) return; fired = true; liveUtts.splice(liveUtts.indexOf(u), 1); onDone(); }
    u.onstart = function () { started = true; metrics.synthPlays++; noteFirstAudio(); };
    u.onend = fin; u.onerror = function () { if (!started && onSilent) return; fin(); };
    u.onboundary = function () { bump = 1; started = true; };
    // no sound within 1.2 s -> this browser's voice is silent (seen on iPhones): switch to the server voice
    if (onSilent) setTimeout(function () {
      if (started || fired || token !== speakToken) return;
      fired = true; speakToken++; try { synth.cancel(); } catch (e) {}
      serverVoice = true; onSilent(text, onDone);
    }, SPEAK_START_MS);
    // watchdog: some browsers forget to fire onend
    setTimeout(function wd() { if (fired || token !== speakToken) return; if (!synth.speaking && !synth.pending) fin(); else setTimeout(wd, 700); }, 1500 + text.length * 90);
    liveUtts.push(u);
    try { synth.resume(); } catch (e) {}
    synth.speak(u);
  }

  function noteFirstAudio() {
    if (metrics.submitAt && metrics.firstAudioMs == null) metrics.firstAudioMs = Math.round(performance.now() - metrics.submitAt);
  }
  // ---- server voice (the natural voice): play an mp3 the server made, through the <audio> unlocked on the
  // opening tap. onFail (optional) runs instead of after() if the clip can't play at all (then: browser voice).
  function playServer(src, after, onFail) {
    releaseMicForSpeech();
    var tok = ++speakToken;
    speakingNow = true;
    if (state !== "greeting") { if (state !== "speaking") echoFloor = Math.max(0.015, noiseFloor * 2); setState("speaking"); }
    uttStart = performance.now(); loudSince = 0;
    var ended = false, began = false, lastT = -1, stuck = 0;
    function end() { if (ended || tok !== speakToken) return; ended = true; speakingNow = false; after(); }
    function fail() {
      if (ended || tok !== speakToken) return;
      mark("clipfail");
      if (onFail && !began) { ended = true; speakingNow = false; metrics.fallbacks++; onFail(); } else end();
    }
    // watchdog: a clip that stops making progress (stalled network, iPhone audio hiccup) never hangs voice mode
    (function wd() { setTimeout(function () {
      if (ended || tok !== speakToken) return;
      var t = player.currentTime || 0;
      if (t === lastT && (player.paused || player.readyState < 3)) stuck += 1; else stuck = 0;
      lastT = t;
      if (stuck >= 4) fail(); else wd();
    }, 1000); })();
    try {
      player.onended = end; player.onerror = fail;
      player.onplaying = function () { if (tok !== speakToken || began) return; began = true; metrics.srvPlays++; noteFirstAudio(); };
      player.src = src; var pr = player.play();
      if (pr && pr.catch) pr.catch(function (e) {
        if (tok !== speakToken || ended) return;
        if (e && e.name === "AbortError") return;           // replaced by a newer clip
        if (onFail && !IOS) { fail(); return; }
        ended = true; speakingNow = false; setState("tap", "Tap the water core to hear me");
      });
    } catch (e) { fail(); }
  }
  function afterSpeech() { if (greetDone) { var g = greetDone; greetDone = null; g(); } else if (state !== "closed") startListening(false); }
  function requestTts(text) {   // ask the server to voice text we already have (no new chat message)
    if (!send || !text) { afterSpeech(); return; }
    pendingId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    streamDone = false; lateTts = false;
    srvReset();
    send({ id: pendingId, tts: text });
    clearInterval(pollTimer); pollTimer = setInterval(poll, 120);
    clearTimeout(thinkTimer); thinkTimer = setTimeout(function () { if (pendingId) { pendingId = null; afterSpeech(); } }, 20000);
  }
  function greetSilent(text) {    // the greeting made no sound: play it from the server instead
    var gi = GREETINGS.indexOf(text);   // pre-made mp3 per greeting (voice_component/greet0.mp3 ...)
    if (BASE && gi >= 0) playServer(BASE + "greet" + gi + ".mp3?v=" + (args.version || "1"), afterSpeech);
    else requestTts(text);
  }
  function answerSilent() {        // an answer sentence made no sound: the server voices the rest, sentence by sentence
    spokenBefore = botSentences.slice(0, Math.max(0, botIdx)).join(" ");
    queue = []; speakingNow = false; lateTts = true;
    if (!pendingId) { lateTts = false; requestTts(restAfterSpoken(speakable(cutFooter(lastRaw)))); }
  }
  function restAfterSpoken(clean) {
    return spokenBefore && clean.indexOf(spokenBefore) === 0 ? clean.slice(spokenBefore.length).trim() : clean;
  }
  function cutFooter(raw) { var f = (raw || "").search(/🔎|\(📡|_\(📡/); return f >= 0 ? raw.slice(0, f) : (raw || ""); }
  // server voice: the box carries one mp3 per sentence (data-a0, data-a1, ...) as soon as each is ready,
  // so the first sentence plays while the rest are still being made
  function srvReset() { srvClips = []; srvIdx = 0; srvPlaying = false; srvDone = false; srvPlayed = 0; clearTimeout(srvWaitTimer); srvWaitTimer = null; }
  // the answer's sentences, split exactly like the server does (tts.split_sentences), so sentence i = mp3 i.
  // ends[i] = where sentence i stops in the raw text (used when the browser voice takes over mid-answer)
  function splitClient(raw, done) {
    var text = raw || "", out = [], ends = [], pos = 0, f = text.search(/🔎|\(📡|_\(📡/);
    if (f >= 0) { text = text.slice(0, f); done = true; }
    while (true) {
      var rest = text.slice(pos), m = rest.match(/[.!?؟。](?=\s|$)|\n/), end;
      if (m && (m.index + m[0].length < rest.length || done)) end = m.index + m[0].length;
      else if (done && rest.trim()) end = rest.length;
      else break;
      var c = speakable(rest.slice(0, end)); pos += end;
      if (c) { out.push(c); ends.push(pos); }
    }
    return { s: out, ends: ends };
  }
  function feedServer(raw, done, el) {
    if (lateTts) {
      var clean = speakable(cutFooter(raw));
      if (done) { streamDone = true; lateTts = false; pendingId = null; requestTts(restAfterSpoken(clean)); }
      return;
    }
    var sp = splitClient(raw, done);
    if (sp.s.length && sp.s.length !== botSentences.length) { botSentences = sp.s; showBot(); }
    if (el) {
      for (var k = srvClips.length; ; k++) { var a = el.getAttribute("data-a" + k); if (!a) break; srvClips.push(a); mark("clip" + k + (a === "x" ? "x" : "")); }
      if (!srvClips.length && el.getAttribute("data-audio")) srvClips.push(el.getAttribute("data-audio"));
    }
    if (sp.s.length && !metrics.textAt) { metrics.textAt = 1; mark("text"); }
    if (done) { streamDone = true; srvDone = true; mark("done"); }
    srvPump();
  }
  var srvPlayed = 0;
  function srvPump() {
    if (srvPlaying || state === "closed" || !serverVoice) return;
    if (srvIdx < srvClips.length) {
      clearTimeout(srvWaitTimer); srvWaitTimer = null;
      var i = srvIdx++, clip = srvClips[i], line = botSentences[i] || "";
      srvPlaying = true; botIdx = i; showBot();
      var next = function () { srvPlaying = false; srvPump(); };
      var viaBrowser = function () {          // this sentence has no natural-voice mp3: browser voice for it
        if (synth && line) { speakingNow = true; setState("speaking"); releaseMicForSpeech(); speakNow(line, function () { speakingNow = false; next(); }); }
        else next();
      };
      if (clip === "x") { viaBrowser(); return; }
      srvPlayed++;
      playServer("data:audio/mpeg;base64," + clip, next, viaBrowser);
    } else if (srvDone) {
      srvDone = false; clearTimeout(srvWaitTimer); srvWaitTimer = null;
      var txt = speakable(cutFooter(lastRaw));
      // no server voice at all (no internet for the voice service): use the browser's own voice instead
      if (!srvPlayed && !srvClips.length && txt && synth && !lateTts) { metrics.fallbacks++; mark("noclips"); speakingNow = true; setState("speaking"); releaseMicForSpeech(); speakNow(txt, function () { speakingNow = false; afterSpeech(); }); }
      else afterSpeech();
    } else if (!srvWaitTimer && srvIdx < splitClient(lastRaw, streamDone).s.length) {
      // the next sentence's text is here but its mp3 isn't: wait a bit, then let the browser voice take over
      srvWaitTimer = setTimeout(function () {
        srvWaitTimer = null;
        if (srvPlaying || state === "closed" || !serverVoice || srvIdx < srvClips.length) return;
        if (srvIdx < splitClient(lastRaw, streamDone).s.length) srvGiveUp();
      }, SRV_WAIT_MS);
    }
  }
  // the natural voice is too slow/broken right now: the browser voice reads the rest of this answer
  function srvGiveUp() {
    if (!synth) return;
    metrics.fallbacks++; mark("giveup" + srvIdx);
    var sp = splitClient(lastRaw, streamDone), played = srvIdx;
    serverVoice = false; srvFellBack = true; srvReset();
    spokenUpTo = played > 0 ? sp.ends[played - 1] : 0; queue = []; speakingNow = false; cutAtFact = false;
    botSentences = sp.s.slice(0, played); botIdx = played - 1;
    feed(lastRaw, streamDone, null);
  }
  // iPhone: an open mic switches the phone to "call" audio (quiet earpiece / muted), so let go of
  // the recognizer and the mic stream before speaking; listening starts them again afterwards.
  function releaseMicForSpeech() { if (engine === "vad") { vadReset(); iosMicStop(); } else if (IOS) { stopRecognition(); stopMic(); } }

  function speakNext() {
    if (state === "closed") return;
    if (!queue.length) { speakingNow = false; maybeFinished(); return; }
    var text = queue.shift();
    speakingNow = true; botIdx++; showBot();
    if (state !== "speaking") { setState("speaking"); echoFloor = Math.max(0.015, noiseFloor * 2); }
    uttStart = performance.now(); loudSince = 0;
    releaseMicForSpeech();
    speakNow(text, speakNext, srvFellBack ? null : answerSilent);
  }

  function maybeFinished() {
    if (streamDone && !queue.length && !speakingNow && (state === "speaking" || state === "thinking")) {
      if (!botSentences.length && state === "thinking") ui.bot.textContent = "";
      setTimeout(function () { if (!speakingNow && (state === "speaking" || state === "thinking")) startListening(false); }, 250);
    }
  }

  function interruptSpeech() {
    speakToken++; queue = []; speakingNow = false; streamDone = true; cutAtFact = true;
    try { synth.cancel(); } catch (e) {}
    try { if (player) player.pause(); } catch (e) {}
    lateTts = false; srvReset();
    clearInterval(pollTimer); pendingId = null;
  }

  // ------------------------------------------------------------ animation + barge-in loop
  // The "water core": a glass bubble of water with a bottle-rocket nozzle and fins.
  // idle = gentle float, listening = waves follow your voice, thinking = bubbles swirl while the
  // pressure gauge fills, speaking = the water pulses with the voice and thrust sprays from the nozzle.
  var bump = 0, scale = 1, wav = 0.02, swirl = 0, thrust = 0, fill = 0.55, lastNow = performance.now();
  var bubbles = [], spray = [];
  for (var i = 0; i < (LITE ? 10 : 18); i++) bubbles.push(newBubble(true));
  function newBubble(anywhere) {
    return { x: 0.2 + Math.random() * 0.6, y: anywhere ? 0.35 + Math.random() * 0.65 : 1.02, r: 0.006 + Math.random() * 0.018,
      sp: 0.00006 + Math.random() * 0.00012, ph: Math.random() * 6.28, wob: 0.004 + Math.random() * 0.012 };
  }
  function drawOrb(now) {
    var c = ui.canvas; if (!c) return;
    var dt = Math.min(64, now - lastNow); lastNow = now;
    var dpr = Math.min(W.devicePixelRatio || 1, 2), S = Math.round(c.clientWidth * dpr);
    if (!S) return;
    var H = Math.round(S * 1.5);
    if (c.width !== S || c.height !== H) { c.width = S; c.height = H; }
    var ctx = c.getContext("2d"), cx = S / 2, cy = S / 2, R = S / 2 * 0.985, TAU = Math.PI * 2;
    ctx.clearRect(0, 0, S, H);
    var talking = state === "speaking" || state === "greeting";

    // targets per state, eased so changes feel liquid
    var tw, tf, ts, tt;
    if (state === "listening") { tw = 0.018 + Math.min(0.11, level * 1.6); tf = 0.52 + Math.min(0.14, level * 2); ts = 0.15; tt = 0; }
    else if (state === "thinking") { tw = 0.035; tf = 0.5 + press * 0.3; ts = 1; tt = 0; }
    else if (talking) { tw = 0.03 + bump * 0.05 + Math.min(0.05, level); tf = 0.6 + 0.04 * Math.sin(now / 180); ts = 0.35; tt = 0.55 + bump * 0.45; }
    else if (state === "leaving") { tw = 0.06; tf = 0.6; ts = 0.6; tt = 1.6; }   // full thrust for the launch-away exit
    else { tw = 0.016; tf = 0.55; ts = 0.1; tt = 0; }
    wav += (tw - wav) * 0.12; fill += (tf - fill) * 0.05; swirl += (ts - swirl) * 0.04; thrust += (tt - thrust) * 0.15;

    // --- nozzle + fins (behind the glass)
    ctx.save();
    var nw = S * 0.15, ny = cy + R * 0.9;
    var ng = ctx.createLinearGradient(cx - nw, 0, cx + nw, 0);
    ng.addColorStop(0, "#1e3a8a"); ng.addColorStop(0.5, "#5fb8f0"); ng.addColorStop(1, "#1e3a8a");
    ctx.fillStyle = ng;
    ctx.beginPath(); ctx.moveTo(cx - nw * 0.62, ny); ctx.lineTo(cx + nw * 0.62, ny);
    ctx.lineTo(cx + nw * 0.42, ny + S * 0.1); ctx.lineTo(cx - nw * 0.42, ny + S * 0.1); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#7dd3fc"; ctx.fillRect(cx - nw * 0.5, ny + S * 0.095, nw, S * 0.018);
    [-1, 1].forEach(function (sd) {
      var fg = ctx.createLinearGradient(cx + sd * R * 0.6, cy, cx + sd * R * 1.12, cy + R);
      fg.addColorStop(0, "rgba(37,99,235,.95)"); fg.addColorStop(1, "rgba(30,58,138,.9)");
      ctx.fillStyle = fg; ctx.strokeStyle = "rgba(125,211,252,.7)"; ctx.lineWidth = Math.max(1, S * 0.006);
      ctx.beginPath(); ctx.moveTo(cx + sd * R * 0.62, cy + R * 0.42);
      ctx.quadraticCurveTo(cx + sd * R * 1.05, cy + R * 0.62, cx + sd * R * 1.1, cy + R * 1.12);
      ctx.lineTo(cx + sd * R * 0.82, cy + R * 0.98); ctx.lineTo(cx + sd * R * 0.5, cy + R * 0.86); ctx.closePath();
      ctx.fill(); ctx.stroke();
    });
    ctx.restore();

    // --- thrust spray from the nozzle while it talks
    var emit = thrust * dt * 0.5;
    while (emit > 0) { if (Math.random() < emit) spray.push({ x: cx + (Math.random() - .5) * nw * 0.6, y: ny + S * 0.11,
      vx: (Math.random() - .5) * S * 0.0005, vy: S * (0.0004 + Math.random() * 0.0005), life: 1, r: S * (0.004 + Math.random() * 0.008) }); emit -= 1; }
    for (var q = spray.length - 1; q >= 0; q--) {
      var d = spray[q]; d.x += d.vx * dt; d.y += d.vy * dt; d.vx *= 1.01; d.life -= dt / 560;
      if (d.life <= 0 || d.y > H) { spray.splice(q, 1); continue; }
      ctx.fillStyle = "rgba(147,214,255," + (d.life * 0.75).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(d.x, d.y, d.r * (0.6 + d.life * 0.6), 0, TAU); ctx.fill();
    }
    if (spray.length > 260) spray.splice(0, spray.length - 260);

    // --- the glass bubble
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, TAU); ctx.clip();
    var bg = ctx.createRadialGradient(cx, cy - R * 0.3, R * 0.1, cx, cy, R);
    bg.addColorStop(0, "#16367a"); bg.addColorStop(1, "#0a1a45");
    ctx.fillStyle = bg; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);

    // water: two sloshing layers
    var level0 = cy + R - fill * 2 * R, t = now / 1000, tilt = Math.sin(t * 0.9) * (0.02 + swirl * 0.05);
    function surface(x, ph, amp) {
      var u = (x - cx) / R;
      return level0 + u * tilt * R + Math.sin(u * 3.1 + t * 2.1 + ph) * amp * S + Math.sin(u * 5.7 - t * 2.9 + ph) * amp * 0.45 * S;
    }
    function water(ph, amp, top, bot) {
      ctx.beginPath(); ctx.moveTo(cx - R, cy + R);
      for (var x = cx - R; x <= cx + R + 1; x += S / 48) ctx.lineTo(x, surface(x, ph, amp));
      ctx.lineTo(cx + R, cy + R); ctx.closePath();
      var g = ctx.createLinearGradient(0, level0 - wav * S, 0, cy + R);
      g.addColorStop(0, top); g.addColorStop(1, bot); ctx.fillStyle = g; ctx.fill();
    }
    water(2.2, wav * 0.8, "rgba(125,211,252,.55)", "rgba(37,99,235,.55)");
    water(0, wav, "#5cc8f8", "#1d4ed8");
    // glowing surface line
    ctx.beginPath();
    for (var x2 = cx - R; x2 <= cx + R + 1; x2 += S / 48) { var yy = surface(x2, 0, wav); if (x2 === cx - R) ctx.moveTo(x2, yy); else ctx.lineTo(x2, yy); }
    ctx.strokeStyle = "rgba(224,242,254,.85)"; ctx.lineWidth = Math.max(1.5, S * 0.008); ctx.stroke();
    // inner glow that brightens while talking
    var glow = ctx.createRadialGradient(cx, cy + R * 0.45, 0, cx, cy + R * 0.45, R * 0.95);
    glow.addColorStop(0, "rgba(186,230,253," + (0.18 + thrust * 0.3 + Math.min(0.25, level * 2)).toFixed(3) + ")"); glow.addColorStop(1, "rgba(186,230,253,0)");
    ctx.fillStyle = glow; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);

    // rising bubbles (swirl while thinking)
    var spd = 1 + swirl * 3.5 + thrust * 1.5;
    bubbles.forEach(function (b, n) {
      b.y -= b.sp * dt * spd;
      var bx = cx + (b.x - 0.5) * 2 * R + Math.sin(t * (1.5 + swirl * 3) + b.ph) * (b.wob + swirl * 0.09) * S;
      var by = cy - R + b.y * 2 * R;
      if (by < surface(bx, 0, wav) + 2 || b.y < 0) { bubbles[n] = newBubble(false); return; }
      var br = b.r * S;
      ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = Math.max(1, S * 0.004);
      ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU); ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.beginPath(); ctx.arc(bx - br * 0.35, by - br * 0.35, br * 0.3, 0, TAU); ctx.fill();
    });

    // glass: highlight + rim
    // curved glass reflection (a thin crescent, top-left) + a small sparkle
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.86, Math.PI * 1.08, Math.PI * 1.42);
    ctx.strokeStyle = "rgba(255,255,255,.38)"; ctx.lineWidth = Math.max(2, S * 0.022); ctx.lineCap = "round"; ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.beginPath(); ctx.arc(cx - R * 0.2, cy - R * 0.78, Math.max(1.5, S * 0.011), 0, TAU); ctx.fill();
    var rim = ctx.createRadialGradient(cx, cy, R * 0.78, cx, cy, R);
    rim.addColorStop(0, "rgba(125,211,252,0)"); rim.addColorStop(1, "rgba(125,211,252,.45)");
    ctx.fillStyle = rim; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    ctx.restore();
    ctx.beginPath(); ctx.arc(cx, cy, R - 1, 0, TAU);
    ctx.strokeStyle = "rgba(186,230,253,.75)"; ctx.lineWidth = Math.max(1.5, S * 0.007); ctx.stroke();
  }

  var lastDraw = 0, lastLvlCss = -1, lastGauge = -1;
  function frame(now) {
    requestAnimationFrame(frame);
    if (state === "closed") return;
    if (LITE) {                      // iPhone: 30 fps is plenty and halves the work
      if (now - lastDraw < 31) return;
      lastDraw = now;
    }
    level = readLevel();
    if (!ui.root) return;
    if (engine === "vad") {
      if (ui.dbg) dbgLine(now);
      if (ui.meter) {
        var ml = state === "listening" ? Math.min(1, ios.rms * 14) : 0;
        for (var mi = 0; mi < ui.meterBars.length; mi++) {
          var on = ml > (mi + 0.5) / ui.meterBars.length;
          if (ui.meterBars[mi]._on !== on) { ui.meterBars[mi]._on = on; ui.meterBars[mi].className = on ? "on" : ""; }
        }
      }
      // the mic went quiet at the hardware level (audio context suspended / interrupted by a call or Siri)
      if (state === "listening" && ios.proc && now - ios.lastPcm > 2500) {
        if (!ios.stalledAt) { ios.stalledAt = now; try { fx.resume(); } catch (e) {} }
        else if (now - ios.stalledAt > 2500) { ios.err = "mic stalled (" + (fx ? fx.state : "-") + ")"; iosMicStop(); setState("tap"); }
      }
    }
    if (state === "listening" && level < noiseFloor * 4) noiseFloor = noiseFloor * 0.97 + level * 0.03;
    if (engine === "record") recorderTick(now);
    // you paused but it's still waiting for you: say so, softly (tap the core sends right away)
    if (state === "listening" && engine === "vad") {
      var vs = !ios.proc ? "Listening…" : !ios.active ? "Listening…" : (now - ios.lastLoud > 600 ? "Still listening · Tap to send" : "Hearing you…");
      if (ui.status.textContent !== vs) { ui.status.textContent = vs; ui.root.classList.toggle("afv-hold", vs.charAt(0) === "S"); holdShown = vs.charAt(0) === "S"; }
    } else if (state === "listening") {
      var hold = !!lastHeardAt && !!(currentText() || recHeard) && Date.now() - lastHeardAt > 650;
      if (hold !== holdShown) {
        holdShown = hold; ui.root.classList.toggle("afv-hold", hold);
        ui.status.textContent = hold ? "Still listening · Tap to send" : "Listening…";
      }
    }

    // barge-in: you start talking while the bot is speaking -> stop it and listen
    if (state === "speaking" && !muted && analyser) {
      var since = now - uttStart;
      var thr = Math.max(0.045, echoFloor * 2.2, noiseFloor * 5);
      if (since > 350) {
        if (level > thr) { if (!loudSince) loudSince = now; else if (now - loudSince > BARGE_MS) { interruptSpeech(); startListening(false); } }
        else { loudSince = 0; echoFloor = echoFloor * 0.98 + level * 0.02; }
      }
    }

    // core size + pressure gauge + ripples
    var target = 1, talking = state === "speaking" || state === "greeting";
    if (talking) { bump *= 0.92; if (Math.random() < 0.07) bump = Math.max(bump, 0.4 + Math.random() * 0.6); }  // syllable-ish flicker (iPhone fires no word events)
    if (state === "listening") target = 1 + Math.min(0.12, level * 2) + 0.012 * Math.sin(now / 600);
    else if (talking) target = 1.02 + 0.02 * Math.sin(now / 160) + bump * 0.035;
    else if (state === "thinking") target = 0.97 + 0.012 * Math.sin(now / 260);
    else target = 1 + 0.018 * Math.sin(now / 1100);
    scale += (target - scale) * 0.18;
    var floatY = (state === "listening" || state === "thinking") ? 0 : Math.sin(now / 1300) * 6;
    ui.orb.style.transform = "translateY(" + floatY.toFixed(1) + "px) scale(" + scale.toFixed(4) + ")";
    var tp = state === "thinking" ? 0.97 : state === "listening" ? 0.08 + Math.min(0.6, level * 7) : talking ? 0.3 + bump * 0.25 : 0.04;
    press += (tp - press) * (state === "thinking" ? 0.012 : 0.1);
    var gv = (press * 0.75 * 351.86).toFixed(1), lv = Math.min(1, level * 9);
    if (ui.gauge && (!LITE || Math.abs(gv - lastGauge) > 1.5)) { lastGauge = +gv; ui.gauge.style.strokeDasharray = gv + " 400"; }
    if (ui.core && (!LITE || Math.abs(lv - lastLvlCss) > 0.04)) { lastLvlCss = lv; ui.core.style.setProperty("--lvl", lv.toFixed(3)); }
    drawOrb(now);
  }

  // ------------------------------------------------------------ public API (used by the bridge + tests)
  W.AFVoice = {
    connect: function (fn) { send = fn; },
    update: function (a) { args = a || {}; if (ui.root) { $(".afv-title").textContent = args.name || ""; setTeam(); } placeLauncher(); },
    open: open, close: close,
    state: function () { return state; },
    metrics: function () { return JSON.parse(JSON.stringify(metrics)); },
    // test hooks: pretend the recognizer heard something / inspect what is queued
    _fakeWords: function (text, isFinal) {   // test hook: words arrive like the recognizer's, patience applies
      if (state !== "listening") { stopRecognition(); setState("listening"); }
      if (isFinal) { committed = join(committed, text); heardText = committed; interimText = ""; } else interimText = text;
      lastHeardAt = Date.now(); ui.you.textContent = currentText(); armSilence();
    },
    _fakeEnd: function () { committed = join(committed, interimText); heardText = committed; interimText = ""; },  // iPhone "onend" on a pause
    tapCore: function () { onOrbTap(); },
    _fakeHeard: function (text) { stopRecognition(); heardText = text; interimText = ""; setState("listening"); finishListening(); },
    _wav: function () { return ios.lastWav || ""; },
    _ios: function () { return { proc: !!ios.proc, mic: micLive(), active: ios.active, speechMs: ios.speechMs, nf: ios.nf, rms: ios.rms, err: ios.err, clipMs: ios.clipMs, rtt: ios.rtt, acqMs: ios.acqMs, ctx: fx ? fx.state : null, srvPlayed: srvPlayed, standalone: STANDALONE }; },
    _debug: function () { return { state: state, engine: engine, pendingId: pendingId, queue: queue.slice(), spoken: botSentences.slice(), caption: ui.bot ? ui.bot.textContent : "" }; }
  };
  setInterval(placeLauncher, 400);
  W.addEventListener("resize", placeLauncher);
})();
