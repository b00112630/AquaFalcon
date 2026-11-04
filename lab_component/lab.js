/* lab.js - AquaFalcon Launch Lab: controls, the animated flight (canvas, ~60 fps) and the two charts.
   The flight itself is computed by physics.js; this file only draws it and talks to Streamlit. */
(function () {
  "use strict";
  var PH = window.AFPhysics;
  var $ = function (id) { return document.getElementById(id); };
  var DPR = Math.min(window.devicePixelRatio || 1, 2.5);

  // ---------------------------------------------------------------- Streamlit bridge (plain postMessage)
  var args = {}, started = false;
  function post(type, extra) {
    var msg = Object.assign({ isStreamlitMessage: true, type: type }, extra || {});
    window.parent.postMessage(msg, "*");
  }
  function send(action) {
    post("streamlit:setComponentValue", { dataType: "json",
      value: { id: action + "-" + Date.now(), action: action, params: P } });
  }
  var lastH = 0;
  function fitHeight() {
    var h = Math.ceil(document.documentElement.scrollHeight);
    if (Math.abs(h - lastH) > 1) { lastH = h; post("streamlit:setFrameHeight", { height: h }); }
  }
  window.addEventListener("message", function (e) {
    var d = e.data || {};
    if (d.type !== "streamlit:render") return;
    args = d.args || {};
    if (!started) { started = true; boot(); }
  });
  post("streamlit:componentReady", { apiVersion: 1 });

  // ---------------------------------------------------------------- state
  var P = {};                 // current setup (physics units: fill 0..1)
  var res = null, sweep = null, ghost = null;      // last computed flight, fill sweep, previous flight
  var goal = "range";
  var fly = null;             // the flight being animated: {res, t, done}
  var parts = [];             // water droplets / splash particles (screen space)
  var cam = { s: 0, ts: 0, y: 0, ty: 0 };  // pixels per metre across (s) and up (y), eased towards the target
  var defaults = PH.DEFAULTS;

  function saveLocal() { try { localStorage.setItem("aflab", JSON.stringify(P)); } catch (e) {} }
  function loadLocal() { try { return JSON.parse(localStorage.getItem("aflab") || "null"); } catch (e) { return null; } }

  function boot() {
    var name = args.name || "AquaFalcon";
    $("ask-label").textContent = "Ask " + name + " why";
    document.querySelector(".ask small").textContent =
      "Opens the chat with this exact setup, so " + name + " can explain the physics.";
    $("sub").textContent = "Flight simulator";   // the team name is in the top bar
    defaults = PH.clean(args.defaults || PH.DEFAULTS);
    P = PH.clean(args.saved || loadLocal() || defaults);
    bindControls();
    syncControls();
    recompute(true);
    resize();
    window.addEventListener("resize", resize);
    if (window.ResizeObserver) new ResizeObserver(function () { resize(); }).observe(document.body);
    requestAnimationFrame(loop);
    setTimeout(fitHeight, 50);
  }

  // ---------------------------------------------------------------- controls
  var SL = { fill: ["fill", 100], psi: ["psi", 1], angle: ["angle", 1], dry: ["dry_g", 1] };
  function paintRange(el) {
    var p = (el.value - el.min) / (el.max - el.min) * 100;
    el.style.setProperty("--p", p + "%");
  }
  function bindControls() {
    Object.keys(SL).forEach(function (id) {
      var el = $(id);
      el.addEventListener("input", function () {
        P[SL[id][0]] = +el.value / SL[id][1];
        paintRange(el); showValues(); recompute(false);
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll(".seg"), function (seg) {
      seg.addEventListener("click", function (e) {
        var b = e.target.closest("button"); if (!b) return;
        var k = seg.getAttribute("data-k"), v = b.getAttribute("data-v");
        if (k === "goal") { goal = v; } else { P[k] = (k === "nose") ? v : +v; }
        syncSegs(); recompute(false, k === "goal");
      });
    });
    $("go").addEventListener("click", launch);
    $("sky").addEventListener("click", function () { if (!fly || fly.done) launch(); });
    $("reset").addEventListener("click", function () { P = PH.clean(defaults); syncControls(); recompute(false); });
    $("use-best").addEventListener("click", function () {
      if (!sweep) return; P.fill = sweep.best_fill; syncControls(); recompute(false); launch();
    });
    $("ask").addEventListener("click", function () { saveLocal(); $("ask-label").textContent = "Opening the chat…"; send("ask"); });
    $("back").addEventListener("click", function () { saveLocal(); send("chat"); });
  }
  function syncSegs() {
    Array.prototype.forEach.call(document.querySelectorAll(".seg"), function (seg) {
      var k = seg.getAttribute("data-k"), cur = k === "goal" ? goal : String(P[k]);
      Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) {
        var on = k === "goal" || k === "nose" ? b.getAttribute("data-v") === cur : +b.getAttribute("data-v") === +cur;
        b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    });
  }
  function syncControls() {
    Object.keys(SL).forEach(function (id) {
      var el = $(id); el.value = Math.round(P[SL[id][0]] * SL[id][1]); paintRange(el);
    });
    syncSegs(); showValues();
  }
  function showValues() {
    var ml = Math.round(P.bottle_l * 1000 * P.fill);
    $("o-fill").innerHTML = Math.round(P.fill * 100) + "% <small>" + ml + " mL</small>";
    $("o-psi").innerHTML = Math.round(P.psi) + " psi <small>" + (P.psi / 14.5038).toFixed(1) + " bar</small>";
    $("o-angle").textContent = Math.round(P.angle) + "°";
    $("o-dry").textContent = Math.round(P.dry_g) + " g";
    var h = 64 * P.fill;      // bottle drawing: water level
    $("bwater").setAttribute("y", 78 - h); $("bwater").setAttribute("height", h + 2);
  }

  var sweepTimer = null;
  function recompute(first, sweepOnly) {
    if (!sweepOnly) {
      if (fly && fly.done && res) ghost = res;     // keep the last flown path as a faint "ghost"
      res = PH.simulate(P, true);
      res.tApo = 0;
      var best = -1;
      res.samples.forEach(function (s) { if (s[2] > best) { best = s[2]; res.tApo = s[0]; } });
      if (fly && !fly.done) fly = null;
      else if (fly && fly.done) fly = null;
      setTarget();
      if (first) { cam.s = cam.ts; cam.y = cam.ty; }
      showStats(res, null);
      showWarnings();
      saveLocal();
    }
    clearTimeout(sweepTimer);
    sweepTimer = setTimeout(function () { sweep = PH.sweepFill(P, goal); drawSweep(); }, first ? 0 : 90);
    drawFlightChart();
  }
  function showWarnings() {
    var w = "";
    if (!res.flew) w = P.psi <= 0 ? "No pressure = no thrust. Pump it up!" : "Too heavy for this push: it never leaves the pad.";
    else if (res.water_left_ml > 0) w = "Air ran out with " + res.water_left_ml + " mL of water still inside";
    else if (P.psi > 90) w = "Over 90 psi: only if your bottle is rated for it";
    $("warn").textContent = w; $("warn").classList.toggle("on", !!w);
    var st = $("stab");
    st.className = "chip-stab " + (res.stable ? "ok" : "bad");
    st.textContent = res.stable ? "Stable ✓" : "Tumbles ⚠";
    st.title = res.stable ? "Fins keep it flying nose-first" : "No fins: it tumbles, so drag is much higher";
  }
  function fmt(v, d) { return (Math.round(v * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d); }
  function showStats(r, live) {
    var L = live || {};
    $("s-range").innerHTML = (live ? fmt(L.x, 1) : (r.flew ? fmt(r.range_m, 1) : "0")) + "<small>m</small>";
    $("s-apo").innerHTML = (live ? fmt(L.apo, 1) : (r.flew ? fmt(r.apogee_m, 1) : "0")) + "<small>m</small>";
    $("s-spd").innerHTML = (live ? fmt(L.v, 0) : fmt(r.max_speed_ms, 0)) + "<small>m/s</small>";
    $("s-push").innerHTML = Math.round(r.thrust_s * 1000) + "<small>ms</small>";
  }

  // ---------------------------------------------------------------- flight playback
  function launch() {
    if (!res) return;
    if (fly && fly.done && res) ghost = { samples: res.samples, flew: res.flew };
    fly = { res: res, t: 0, i: 0, done: false, apo: 0, landedAt: 0 };
    parts = [];
    $("go").classList.add("flying"); $("go-label").textContent = res.flew ? "Flying…" : "Launch";
    if (!res.flew) { fly.done = true; $("go").classList.remove("flying"); puff(); }
  }
  function warp(t, r) { return t < r.thrust_s + 0.03 ? 0.06 : (t < r.thrust_s + 0.25 ? 0.35 : 1); }
  function sampleAt(r, t) {
    var s = r.samples, i = fly ? fly.i : 0;
    if (!s.length) return null;
    while (i < s.length - 1 && s[i + 1][0] < t) i++;
    if (fly) fly.i = i;
    var a = s[i], b = s[Math.min(i + 1, s.length - 1)];
    var k = b[0] > a[0] ? Math.min(1, Math.max(0, (t - a[0]) / (b[0] - a[0]))) : 0;
    return { t: t, x: a[1] + (b[1] - a[1]) * k, y: a[2] + (b[2] - a[2]) * k, v: a[3] + (b[3] - a[3]) * k,
             f: a[4], phase: a[5], vx: b[1] - a[1], vy: b[2] - a[2], idx: i };
  }

  // ---------------------------------------------------------------- canvas
  var sky = $("sky"), ctx = sky.getContext("2d"), W = 0, H = 0;
  var stars = [];
  for (var si = 0; si < 70; si++) stars.push([Math.random(), Math.random() * 0.75, Math.random() * 1.2 + 0.3, Math.random() * 6.28]);
  function resize() {
    var r = sky.getBoundingClientRect();
    W = r.width; H = r.height;
    sky.width = Math.round(W * DPR); sky.height = Math.round(H * DPR);
    ["ch-flight", "ch-sweep"].forEach(function (id) {
      var c = $(id), b = c.getBoundingClientRect();
      c.width = Math.round(b.width * DPR); c.height = Math.round(b.height * DPR);
    });
    setTarget(); cam.s = cam.ts; cam.y = cam.ty;
    drawSweep(); drawFlightChart(); fitHeight();
  }
  var PAD_L = 34, PAD_R = 22, PAD_T = 46, GROUND = 38;
  // Fit the whole flight on screen. Height may be stretched up to 2.2x (flat flights on a narrow phone);
  // the grid labels always show the real metres.
  function setTarget() {
    if (!W || !res) { cam.ts = cam.ty = 4; return; }
    var rx = Math.max(res.range_m, 10) * 1.06 + 2;
    var ry = Math.max(res.apogee_m, 4) * 1.12 + 1;
    var bx = (W - PAD_L - PAD_R) / rx, by = (H - PAD_T - GROUND) / ry;
    cam.ts = Math.min(bx, by * 1.0);
    cam.ty = Math.min(by, cam.ts * 2.2);
  }
  function padAngle() { var a = P.angle * Math.PI / 180; return screenAngle(Math.cos(a), Math.sin(a)); }
  function sx(x) { return PAD_L + x * cam.s; }
  function sy(y) { return H - GROUND - y * cam.y; }
  function screenAngle(vx, vy) { return Math.atan2(vy * cam.y, vx * cam.s); }
  function niceStep(span, n) {
    var raw = span / n, m = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / m;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * m;
  }

  function drawBackground(time) {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#dbe8fb"); g.addColorStop(0.6, "#eef4fd"); g.addColorStop(1, "#f8fbff");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // soft horizon glow
    var hg = ctx.createRadialGradient(W * 0.5, H - GROUND, 10, W * 0.5, H - GROUND, W * 0.7);
    hg.addColorStop(0, "rgba(255,255,255,.75)"); hg.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = hg; ctx.fillRect(0, 0, W, H);
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i], a = 0.35 + 0.35 * Math.sin(time * 0.0012 + s[3]);
      if (i % 9) continue;   // light theme: a few soft clouds instead of stars
      var cxp = ((s[0] * W + time * 0.004 * (1 + s[2])) % (W + 120)) - 60, cyp = 24 + s[1] * (H - GROUND - 90) * 0.6;
      ctx.fillStyle = "rgba(255,255,255," + (0.55 + 0.25 * a).toFixed(3) + ")";
      ctx.beginPath(); ctx.ellipse(cxp, cyp, 34 + 10 * s[2], 9 + 2 * s[2], 0, 0, 6.283);
      ctx.ellipse(cxp + 14, cyp - 6, 18 + 4 * s[2], 9, 0, 0, 6.283); ctx.fill();
    }
    // height grid
    var maxY = (H - GROUND - 10) / cam.y, st = niceStep(maxY, 4);
    ctx.font = "600 10px Inter, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    for (var y = st; y < maxY; y += st) {
      var py = sy(y);
      if (py < 30) break;
      ctx.strokeStyle = "rgba(15,23,42,.06)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PAD_L, py); ctx.lineTo(W, py); ctx.stroke();
      ctx.fillStyle = "#94a3b8"; ctx.fillText(Math.round(y) + " m", 4, py);
    }
    // ground
    var gg = ctx.createLinearGradient(0, H - GROUND, 0, H);
    gg.addColorStop(0, "#eef2f6"); gg.addColorStop(1, "#e2e8f0");
    ctx.fillStyle = gg; ctx.fillRect(0, H - GROUND, W, GROUND);
    ctx.fillStyle = "#cbd5e1"; ctx.fillRect(0, H - GROUND, W, 1.5);
    var maxX = (W - PAD_L) / cam.s, xs = niceStep(maxX, 6);
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (var x = 0; x < maxX; x += xs) {
      var px = sx(x);
      ctx.fillStyle = "#cbd5e1"; ctx.fillRect(px, H - GROUND, 1, 6);
      ctx.fillStyle = "#94a3b8"; ctx.fillText(Math.round(x) + (x === 0 ? "" : " m"), px, H - GROUND + 9);
    }
    // launch pad
    var a = padAngle(), rl = 18;
    ctx.strokeStyle = "#64748b"; ctx.lineWidth = 3; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(sx(0) - Math.cos(a) * 4, sy(0) + Math.sin(a) * 4);
    ctx.lineTo(sx(0) + Math.cos(a) * rl, sy(0) - Math.sin(a) * rl); ctx.stroke();
    ctx.fillStyle = "#64748b"; ctx.fillRect(sx(0) - 9, H - GROUND - 3, 18, 3);
  }

  function path(samples, upto, style) {
    if (!samples || samples.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(sx(samples[0][1]), sy(samples[0][2]));
    for (var i = 1; i < samples.length && samples[i][0] <= upto; i++) ctx.lineTo(sx(samples[i][1]), sy(samples[i][2]));
    style();
  }
  function trail(r, upto, now) {
    path(r.samples, upto, function () {
      ctx.strokeStyle = "rgba(59,130,246,.16)"; ctx.lineWidth = 7; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
      ctx.strokeStyle = "#2563eb"; ctx.lineWidth = 2.4; ctx.stroke();
    });
    if (now) { ctx.lineTo(sx(now.x), sy(now.y)); }
  }
  function label(x, y, text, color, align) {
    ctx.font = "700 12px Inter, sans-serif";
    var w = ctx.measureText(text).width + 14, h = 22;
    var bx = align === "right" ? x - w : align === "center" ? x - w / 2 : x;
    bx = Math.max(4, Math.min(W - w - 4, bx));
    var by = Math.max(4, y - h / 2);
    ctx.fillStyle = "rgba(255,255,255,.94)"; roundRect(bx, by, w, h, 11); ctx.fill();
    ctx.strokeStyle = color; ctx.lineWidth = 1; roundRect(bx, by, w, h, 11); ctx.stroke();
    ctx.fillStyle = color; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(text, bx + 7, by + h / 2 + 0.5);
  }
  function roundRect(x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function markers(r, showApo, showLand, alpha) {
    ctx.globalAlpha = alpha;
    if (showApo && r.flew) {
      var ax = 0;
      for (var i = 0; i < r.samples.length; i++) if (r.samples[i][0] >= r.tApo) { ax = r.samples[i][1]; break; }
      var px = sx(ax), py = sy(r.apogee_m);
      ctx.setLineDash([3, 4]); ctx.strokeStyle = "rgba(30,58,138,.4)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px, H - GROUND); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#1e3a8a"; ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 6.283); ctx.fill();
      label(px + 9, py - 14, "↑ " + fmt(r.apogee_m, 1) + " m high", "#1e3a8a", "left");
    }
    if (showLand && r.flew) {
      var lx = sx(r.range_m), gy = H - GROUND;
      ctx.strokeStyle = "#94a3b8"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(sx(0), gy + 26); ctx.lineTo(lx, gy + 26); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(lx, gy + 21); ctx.lineTo(lx, gy + 31); ctx.moveTo(sx(0), gy + 21); ctx.lineTo(sx(0), gy + 31); ctx.stroke();
      ctx.strokeStyle = "#334155"; ctx.lineWidth = 2;   // flag
      ctx.beginPath(); ctx.moveTo(lx, gy); ctx.lineTo(lx, gy - 20); ctx.stroke();
      ctx.fillStyle = "#22c55e"; ctx.beginPath(); ctx.moveTo(lx, gy - 20); ctx.lineTo(lx + 11, gy - 16); ctx.lineTo(lx, gy - 12); ctx.fill();
      label(lx, gy - 46, fmt(r.range_m, 1) + " m", "#0f172a", "center");
    }
    ctx.globalAlpha = 1;
  }

  function drawRocket(x, y, ang, waterFrac, flame) {
    var L = 34, R = 6;
    ctx.save(); ctx.translate(x, y); ctx.rotate(-ang);
    // fins
    ctx.fillStyle = "#1e3a8a";
    if (P.fins > 0) {
      ctx.beginPath(); ctx.moveTo(-L / 2 + 2, -R); ctx.lineTo(-L / 2 - 3, -R - 7); ctx.lineTo(-L / 2 + 9, -R); ctx.fill();
      ctx.beginPath(); ctx.moveTo(-L / 2 + 2, R); ctx.lineTo(-L / 2 - 3, R + 7); ctx.lineTo(-L / 2 + 9, R); ctx.fill();
      if (P.fins === 4) { ctx.fillStyle = "#3b5bb5"; ctx.fillRect(-L / 2 - 2, -1.2, 10, 2.4); }
    }
    // body (clear bottle)
    var bx = -L / 2 + 2, bw = L - 13;
    ctx.fillStyle = "rgba(255,255,255,.9)"; roundRect(bx, -R, bw, 2 * R, 4); ctx.fill();
    if (waterFrac > 0.002) {
      ctx.save(); roundRect(bx, -R, bw, 2 * R, 4); ctx.clip();
      ctx.fillStyle = "#3b82f6"; ctx.fillRect(bx, -R, bw * Math.min(1, waterFrac), 2 * R); ctx.restore();
    }
    ctx.strokeStyle = "#334155"; ctx.lineWidth = 1.4; roundRect(bx, -R, bw, 2 * R, 4); ctx.stroke();
    // nozzle
    ctx.fillStyle = "#94a3b8"; ctx.fillRect(bx - 3, -2.4, 3, 4.8);
    // nose
    var nx = bx + bw;
    ctx.fillStyle = "#1e3a8a"; ctx.beginPath();
    if (P.nose === "flat") { ctx.moveTo(nx, -R); ctx.lineTo(nx + 5, -R + 1.5); ctx.lineTo(nx + 5, R - 1.5); ctx.lineTo(nx, R); }
    else if (P.nose === "ogive") { ctx.moveTo(nx, -R); ctx.quadraticCurveTo(nx + 11, -R + 1, nx + 12, 0); ctx.quadraticCurveTo(nx + 11, R - 1, nx, R); }
    else { ctx.moveTo(nx, -R); ctx.lineTo(nx + 12, 0); ctx.lineTo(nx, R); }
    ctx.closePath(); ctx.fill();
    ctx.restore();
  }

  function spawnSpray(x, y, ang, strength, kind, dt) {
    var n = Math.round((kind === "water" ? 260 : 110) * strength * dt * 60 / 60 * 1.0);
    n = Math.min(n, 14);
    var bxv = -Math.cos(ang), byv = Math.sin(ang);
    for (var i = 0; i < n; i++) {
      var sp = (kind === "water" ? 260 : 180) * (0.55 + Math.random() * 0.7) * (0.5 + strength * 0.5);
      var spread = (Math.random() - 0.5) * (kind === "water" ? 0.5 : 1.1);
      var cx = bxv * Math.cos(spread) - byv * Math.sin(spread), cy = bxv * Math.sin(spread) + byv * Math.cos(spread);
      parts.push({ x: x + bxv * 16, y: y + byv * 16, vx: cx * sp, vy: cy * sp, life: 0, max: 0.45 + Math.random() * 0.5,
                   r: kind === "water" ? 1.2 + Math.random() * 2.2 : 3 + Math.random() * 5, kind: kind });
    }
  }
  function splash(x, y) {
    for (var i = 0; i < 46; i++) {
      var a = Math.PI * (0.08 + Math.random() * 0.84), sp = 60 + Math.random() * 170;
      parts.push({ x: x, y: y, vx: Math.cos(a) * sp, vy: -Math.sin(a) * sp, life: 0, max: 0.6 + Math.random() * 0.6,
                   r: 1 + Math.random() * 2.4, kind: Math.random() < 0.6 ? "water" : "dirt" });
    }
    parts.push({ x: x, y: y, vx: 0, vy: 0, life: 0, max: 0.9, r: 4, kind: "ring" });
  }
  function puff() { parts.push({ x: sx(0) + 8, y: sy(0) - 8, vx: 0, vy: -10, life: 0, max: 1.2, r: 6, kind: "ring" }); }
  function stepParticles(dt) {
    for (var i = parts.length - 1; i >= 0; i--) {
      var p = parts[i];
      p.life += dt;
      if (p.life > p.max) { parts.splice(i, 1); continue; }
      if (p.kind !== "ring") {
        p.vy += (p.kind === "mist" ? 40 : 520) * dt;
        p.vx *= (p.kind === "mist" ? 0.94 : 0.995); p.x += p.vx * dt; p.y += p.vy * dt;
        if (p.y > H - GROUND) { p.y = H - GROUND; p.vy *= -0.25; p.vx *= 0.6; }
      }
    }
  }
  function drawParticles() {
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i], k = 1 - p.life / p.max;
      if (p.kind === "ring") {
        ctx.strokeStyle = "rgba(59,130,246," + (0.7 * k).toFixed(3) + ")"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.ellipse(p.x, p.y, 4 + (1 - k) * 34, 2 + (1 - k) * 8, 0, 0, 6.283); ctx.stroke();
      } else if (p.kind === "mist") {
        ctx.fillStyle = "rgba(148,163,184," + (0.3 * k).toFixed(3) + ")";
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r * (1.6 - k), 0, 6.283); ctx.fill();
      } else {
        ctx.fillStyle = p.kind === "dirt" ? "rgba(120,113,108," + k.toFixed(3) + ")" : "rgba(59,130,246," + (0.85 * k).toFixed(3) + ")";
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fill();
      }
    }
  }
  function hud(now) {
    ctx.font = "700 11px Inter, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "top";
    var rows = [["T+", fmt(now.t, 2) + " s"], ["ALT", fmt(Math.max(0, now.y), 1) + " m"], ["SPD", fmt(now.v, 1) + " m/s"]];
    ctx.fillStyle = "rgba(255,255,255,.88)"; roundRect(PAD_L + 6, 10, 118, 54, 10); ctx.fill(); ctx.strokeStyle = "#e5e7eb"; ctx.lineWidth = 1; roundRect(PAD_L + 6, 10, 118, 54, 10); ctx.stroke();
    for (var i = 0; i < rows.length; i++) {
      ctx.fillStyle = "#64748b"; ctx.fillText(rows[i][0], PAD_L + 15, 16 + i * 15);
      ctx.fillStyle = "#0f172a"; ctx.fillText(rows[i][1], PAD_L + 48, 16 + i * 15);
    }
  }

  var last = 0;
  function loop(time) {
    var dt = Math.min(0.05, last ? (time - last) / 1000 : 0.016); last = time;
    cam.s += (cam.ts - cam.s) * Math.min(1, dt * 8); cam.y += (cam.ty - cam.y) * Math.min(1, dt * 8);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawBackground(time);
    var r = res, now = null, pdt = dt;
    if (ghost && ghost.samples && ghost.flew) {
      ctx.setLineDash([2, 5]);
      path(ghost.samples, 1e9, function () { ctx.strokeStyle = "rgba(30,58,138,.16)"; ctx.lineWidth = 1.5; ctx.stroke(); });
      ctx.setLineDash([]);
    }
    if (fly && r && fly.res === r) {
      if (!fly.done) {
        var w = warp(fly.t, r);
        pdt = dt * Math.max(w, 0.3);
        fly.t += dt * w;
        var end = r.samples[r.samples.length - 1][0];
        if (fly.t >= end) {
          fly.t = end; fly.done = true; fly.landedAt = time;
          splash(sx(r.range_m), H - GROUND);
          $("go").classList.remove("flying"); $("go-label").textContent = "Launch again";
          showStats(r, null);
        }
      }
      now = sampleAt(r, fly.t);
      if (now) {
        fly.apo = Math.max(fly.apo, now.y);
        trail(r, fly.t, now);
        markers(r, fly.t >= r.tApo, fly.done, 1);
        var ang = screenAngle(now.vx, now.vy);
        if (now.idx === 0 || (now.vx === 0 && now.vy === 0)) ang = padAngle();
        if (!r.stable && fly.t > 0.15) ang = fly.t * 9;                       // no fins: it tumbles
        var px = sx(now.x), py = sy(Math.max(0, now.y));
        var thrusting = now.phase !== "coast" && !fly.done;
        var waterFrac = now.phase === "water" ? P.fill * Math.max(0, 1 - now.t / Math.max(r.water_thrust_s, 1e-3)) / Math.max(P.fill, 1e-3) : 0;
        if (fly.done) { ang = r.stable ? -0.6 : ang; }
        if (thrusting) spawnSpray(px, py, ang, Math.min(1, now.f / Math.max(r.peak_thrust_n, 1)) + 0.2, now.phase === "water" ? "water" : "mist", dt);
        if (now.phase === "air" && !fly.done) for (var m = 0; m < 2; m++) parts.push({ x: px - Math.cos(ang) * 16, y: py + Math.sin(ang) * 16,
          vx: -Math.cos(ang) * 90 + (Math.random() - .5) * 60, vy: Math.sin(ang) * 90 + (Math.random() - .5) * 60, life: 0, max: .6, r: 4, kind: "mist" });
        stepParticles(pdt);
        drawParticles();
        drawRocket(px, py - (fly.done ? 4 : 0), ang, waterFrac * P.fill, thrusting);
        if (!fly.done) {
          hud(now);
          showStats(r, { x: now.x, apo: fly.apo, v: now.v });
        } else hud({ t: r.flight_time_s, y: 0, v: 0 });
        $("slowmo").classList.toggle("on", !fly.done && fly.t < r.thrust_s + 0.03 && r.flew);
        drawFlightChart(fly.t);
      }
    } else if (r) {
      // waiting on the pad: show where it WILL go (dotted preview), updated live while you drag the sliders
      ctx.setLineDash([2, 6]);
      path(r.samples, 1e9, function () { ctx.strokeStyle = "rgba(37,99,235,.45)"; ctx.lineWidth = 2; ctx.stroke(); });
      ctx.setLineDash([]);
      markers(r, true, true, 0.75);
      stepParticles(dt); drawParticles();
      drawRocket(sx(0) + Math.cos(padAngle()) * 12, sy(0) - Math.sin(padAngle()) * 12 - 2, padAngle(), P.fill, false);
      ctx.font = "600 12px Inter, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillStyle = "#64748b"; ctx.fillText("Preview · press Launch", PAD_L + 8, 14);
      $("slowmo").classList.remove("on");
    }
    requestAnimationFrame(loop);
  }

  // ---------------------------------------------------------------- charts
  function chartFrame(c) {
    var g = c.getContext("2d"), w = c.width / DPR, h = c.height / DPR;
    g.setTransform(DPR, 0, 0, DPR, 0, 0); g.clearRect(0, 0, w, h);
    return { g: g, w: w, h: h, l: 34, r: w - 34, t: 10, b: h - 22 };
  }
  function axes(f, xmax, ymax, xlabel, ylabelL, ylabelR, ymaxR) {
    var g = f.g; g.font = "600 10px Inter, sans-serif"; g.lineWidth = 1;
    var ys = niceStep(ymax, 3);
    g.textAlign = "right"; g.textBaseline = "middle";
    for (var y = 0; y <= ymax + 1e-9; y += ys) {
      var py = f.b - y / ymax * (f.b - f.t);
      g.strokeStyle = "rgba(15,23,42,.06)"; g.beginPath(); g.moveTo(f.l, py); g.lineTo(f.r, py); g.stroke();
      g.fillStyle = "#94a3b8"; g.fillText(Math.round(y) + ylabelL, f.l - 5, py);
    }
    if (ymaxR) {
      g.textAlign = "left";
      var ys2 = niceStep(ymaxR, 3);
      for (var y2 = 0; y2 <= ymaxR + 1e-9; y2 += ys2) {
        g.fillStyle = "#60a5fa"; g.fillText(Math.round(y2) + ylabelR, f.r + 5, f.b - y2 / ymaxR * (f.b - f.t));
      }
    }
    var xs = niceStep(xmax, 4); g.textAlign = "center"; g.textBaseline = "top";
    for (var x = 0; x <= xmax + 1e-9; x += xs) {
      g.fillStyle = "#94a3b8"; g.fillText((xs < 1 ? x.toFixed(1) : Math.round(x)) + xlabel, f.l + x / xmax * (f.r - f.l), f.b + 6);
    }
  }
  function drawFlightChart(upto) {
    var c = $("ch-flight"); if (!c.width || !res) return;
    var f = chartFrame(c), g = f.g, s = res.samples;
    if (!res.flew || s.length < 2) {
      g.fillStyle = "#94a3b8"; g.font = "600 13px Inter, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText("No lift-off with this setup", f.w / 2, f.h / 2); return;
    }
    var T = s[s.length - 1][0], Y = Math.max(res.apogee_m, 1) * 1.1, V = Math.max(res.max_speed_ms, 1) * 1.1;
    axes(f, T, Y, "s", "", "", V);
    var lim = upto === undefined ? 1e9 : upto;
    function line(col, idx, max, fill) {
      g.beginPath();
      var lx = f.l, n = 0;
      for (var i = 0; i < s.length && s[i][0] <= lim; i++) {
        var px = f.l + s[i][0] / T * (f.r - f.l), py = f.b - s[i][idx] / max * (f.b - f.t);
        if (!n) g.moveTo(px, py); else g.lineTo(px, py); lx = px; n++;
      }
      g.strokeStyle = col; g.lineWidth = 2; g.lineJoin = "round"; g.stroke();
      if (fill && n) {
        g.lineTo(lx, f.b); g.lineTo(f.l, f.b); g.closePath();
        var gr = g.createLinearGradient(0, f.t, 0, f.b); gr.addColorStop(0, "rgba(30,58,138,.14)"); gr.addColorStop(1, "rgba(30,58,138,0)");
        g.fillStyle = gr; g.fill();
      }
      return lx;
    }
    line("#1e3a8a", 2, Y, true);
    var lx = line("#7dd3fc", 3, V, false);
    if (upto !== undefined && fly && !fly.done) { g.strokeStyle = "rgba(15,23,42,.25)"; g.beginPath(); g.moveTo(lx, f.t); g.lineTo(lx, f.b); g.stroke(); }
  }
  function drawSweep() {
    var c = $("ch-sweep"); if (!c.width || !sweep) return;
    var f = chartFrame(c), g = f.g, cv = sweep.curve, unit = " m";
    var Y = Math.max.apply(null, cv.map(function (q) { return q[1]; }).concat([1])) * 1.15, X = 80;
    axes(f, X, Y, "%", "", "", 0);
    g.beginPath();
    cv.forEach(function (q, i) { var px = f.l + q[0] * 100 / X * (f.r - f.l), py = f.b - q[1] / Y * (f.b - f.t); if (!i) g.moveTo(px, py); else g.lineTo(px, py); });
    g.strokeStyle = "#2563eb"; g.lineWidth = 2; g.stroke();
    g.lineTo(f.l + cv[cv.length - 1][0] * 100 / X * (f.r - f.l), f.b); g.lineTo(f.l + cv[0][0] * 100 / X * (f.r - f.l), f.b); g.closePath();
    var gr = g.createLinearGradient(0, f.t, 0, f.b); gr.addColorStop(0, "rgba(37,99,235,.12)"); gr.addColorStop(1, "rgba(37,99,235,0)");
    g.fillStyle = gr; g.fill();
    // you are here
    var cur = goal === "height" ? res.apogee_m : res.range_m;
    var cx = f.l + Math.min(P.fill * 100, X) / X * (f.r - f.l), cy = f.b - cur / Y * (f.b - f.t);
    g.strokeStyle = "rgba(15,23,42,.25)"; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(cx, f.t); g.lineTo(cx, f.b); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#0f172a"; g.beginPath(); g.arc(cx, cy, 4, 0, 6.283); g.fill();
    // best
    var bx = f.l + sweep.best_fill * 100 / X * (f.r - f.l), by = f.b - sweep.best_value / Y * (f.b - f.t);
    g.fillStyle = "#1e3a8a"; g.beginPath(); g.arc(bx, by, 5, 0, 6.283); g.fill();
    g.strokeStyle = "rgba(30,58,138,.2)"; g.lineWidth = 6; g.beginPath(); g.arc(bx, by, 8, 0, 6.283); g.stroke();
    var ml = Math.round(sweep.best_fill * P.bottle_l * 1000);
    $("sweep-txt").innerHTML = "Best ≈ <b>" + Math.round(sweep.best_fill * 100) + "% (" + ml + " mL)</b> → " + fmt(sweep.best_value, 1) + unit +
      (goal === "height" ? " high" : "");
    var near = Math.abs(sweep.best_fill - P.fill) < 0.025;
    $("use-best").disabled = near; $("use-best").textContent = near ? "You're there ✓" : "Use it";
  }
})();

// hide the loading screen once the Lab has drawn its first frame
(function () { function done() { var b = document.getElementById("boot"); if (!b) return;
  b.style.opacity = "0"; setTimeout(function () { if (b.parentNode) b.parentNode.removeChild(b); }, 320); }
  if (document.readyState === "complete") requestAnimationFrame(done); else window.addEventListener("load", function () { requestAnimationFrame(done); });
  setTimeout(done, 2500); })();
