/* physics.js - the Launch Lab flight model (same maths as launchlab.py, line for line).
   Runs in the browser (window.AFPhysics) and in Node (module.exports) so the tests can check
   that the JavaScript and the Python give the same answers. Units: SI inside, psi/mL/g outside. */
(function (root) {
  "use strict";
  var G = 9.81, RHO_W = 1000.0, RHO_AIR = 1.2, P_ATM = 101325.0, GAMMA = 1.4, R_AIR = 287.05, T0 = 293.15;
  var PSI = 6894.757, RAIL_M = 0.6, DT_THRUST = 1e-4, DT_COAST = 2e-3, T_MAX = 60.0;
  var NOSE_CD = { cone: 0.34, ogive: 0.30, flat: 0.55 };
  var FIN_CD = { 0: 0.0, 3: 0.04, 4: 0.06 };
  var TUMBLE_CD = 1.1, TUMBLE_THRUST = 0.7;
  var STABILITY_CAL = { 0: -0.5, 3: 1.5, 4: 1.8 };
  var DEFAULTS = { bottle_l: 1.5, fill: 1 / 3, psi: 60.0, angle: 45.0, dry_g: 115.0, nose: "cone", fins: 3, nozzle_mm: 21.5 };

  function r(v, n) { var k = Math.pow(10, n); return Math.round(v * k) / k; }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function clean(params) {
    var p = {}, k;
    for (k in DEFAULTS) p[k] = DEFAULTS[k];
    params = params || {};
    for (k in DEFAULTS) if (params[k] !== undefined && params[k] !== null) p[k] = params[k];
    p.bottle_l = clamp(+p.bottle_l, 0.3, 3.0);
    p.fill = clamp(+p.fill, 0.0, 0.95);
    p.psi = clamp(+p.psi, 0.0, 150.0);
    p.angle = clamp(+p.angle, 5.0, 90.0);
    p.dry_g = clamp(+p.dry_g, 20.0, 2000.0);
    p.nozzle_mm = clamp(+p.nozzle_mm, 3.0, 30.0);
    if (!(p.nose in NOSE_CD)) p.nose = "cone";
    p.fins = (+p.fins in FIN_CD) ? +p.fins : 3;
    return p;
  }

  function bodyDiameter(bottle_l) { return 0.09 * Math.pow(bottle_l / 1.5, 1 / 3); }

  function simulate(params, wantSamples) {
    var p = clean(params);
    var vb = p.bottle_l / 1000.0, vw = vb * p.fill, va0 = vb - vw;
    var p0 = p.psi * PSI + P_ATM;
    var an = Math.PI * Math.pow(p.nozzle_mm / 1000.0, 2) / 4;
    var ab = Math.PI * Math.pow(bodyDiameter(p.bottle_l), 2) / 4;
    var m_dry = p.dry_g / 1000.0;
    var m_air = va0 > 0 ? p0 * va0 / (R_AIR * T0) : 0.0;
    var stable = p.fins > 0;
    var cd = NOSE_CD[p.nose] + FIN_CD[p.fins];
    var th = p.angle * Math.PI / 180, ux = Math.cos(th), uy = Math.sin(th);
    var x = 0, y = 0, vx = 0, vy = 0, t = 0, s_rail = 0, on_rail = true;
    var phase = vw > 0 ? "water" : "air";
    var p_air = p0, t_air = T0, rho_end = null, p_end = null;
    var apogee = 0, max_v = 0, max_f = 0, max_a = 0, t_water = null, t_air_end = null, water_left = 0;
    var lifted = false, pts = [], next_sample = 0, landed_x = null;
    var f, dt, va, dp, u, q, rho, mdot, te, pe, ve, m, v, cd_now, drag, a, vr, dx, dy, ax, ay, nx, ny, k;
    var CH = Math.pow((GAMMA + 1) / 2, GAMMA / (GAMMA - 1));
    while (t < T_MAX) {
      f = 0.0;
      if (phase === "water") {
        va = vb - vw;
        p_air = va0 > 0 ? p0 * Math.pow(va0 / va, GAMMA) : P_ATM;
        dp = p_air - P_ATM;
        if (dp <= 0 || vw <= 0) {
          water_left = Math.max(vw, 0.0);
          t_water = t;
          rho_end = m_air / vb; p_end = Math.max(p_air, P_ATM);
          phase = (dp > 0 && m_air > 0) ? "air" : "coast";
          if (phase === "air") t_air = T0 * Math.pow(va0 / Math.max(va, 1e-12), GAMMA - 1);
          continue;
        }
        u = Math.sqrt(2 * dp / RHO_W);
        q = an * u;
        f = 2 * an * dp;
        dt = DT_THRUST;
        vw -= q * dt;
        if (vw < 0) vw = 0.0;
      } else if (phase === "air") {
        if (rho_end === null) { rho_end = m_air / vb; p_end = p0; }
        rho = m_air / vb;
        p_air = rho_end > 0 ? p_end * Math.pow(rho / rho_end, GAMMA) : P_ATM;
        if (p_air <= P_ATM * 1.001 || m_air <= 1e-7) { phase = "coast"; t_air_end = t; continue; }
        t_air = p_air / (rho * R_AIR);
        if (p_air / P_ATM > CH) {
          mdot = an * p_air * Math.sqrt(GAMMA / (R_AIR * t_air)) * Math.pow(2 / (GAMMA + 1), (GAMMA + 1) / (2 * (GAMMA - 1)));
          te = t_air * 2 / (GAMMA + 1);
          pe = p_air * Math.pow(2 / (GAMMA + 1), GAMMA / (GAMMA - 1));
          f = mdot * Math.sqrt(GAMMA * R_AIR * te) + (pe - P_ATM) * an;
        } else {
          ve = Math.sqrt(2 * GAMMA / (GAMMA - 1) * R_AIR * t_air * (1 - Math.pow(P_ATM / p_air, (GAMMA - 1) / GAMMA)));
          mdot = rho * Math.pow(P_ATM / p_air, 1 / GAMMA) * an * ve;
          f = mdot * ve;
        }
        dt = DT_THRUST;
        m_air = Math.max(0.0, m_air - mdot * dt);
      } else {
        dt = DT_COAST;
      }
      if (!stable && !on_rail) f *= TUMBLE_THRUST;
      m = m_dry + RHO_W * vw + m_air;
      v = Math.hypot(vx, vy);
      cd_now = (stable || on_rail) ? cd : TUMBLE_CD;
      drag = 0.5 * RHO_AIR * cd_now * ab * v * v;
      max_f = Math.max(max_f, f);
      if (on_rail) {
        a = (f - drag) / m - G * uy;
        vr = vx * ux + vy * uy;
        if (vr <= 0 && a <= 0) {
          a = 0.0;
          if (f <= 0 && phase === "coast") break;
        }
        vr += a * dt;
        vx = vr * ux; vy = vr * uy;
        x += vx * dt; y += vy * dt;
        s_rail += vr * dt;
        if (s_rail >= RAIL_M) on_rail = false;
        max_a = Math.max(max_a, a);
      } else {
        if (v > 1e-9) { dx = vx / v; dy = vy / v; } else { dx = ux; dy = uy; }
        ax = (f - drag) / m * dx;
        ay = (f - drag) / m * dy - G;
        max_a = Math.max(max_a, (f - drag) / m);
        vx += ax * dt; vy += ay * dt;
        nx = x + vx * dt; ny = y + vy * dt;
        if (ny < 0 && lifted) {
          k = y !== ny ? y / (y - ny) : 1.0;
          landed_x = x + (nx - x) * k;
          t += dt * k;
          x = landed_x; y = 0.0;
          pts.push([r(t, 4), r(x, 3), 0.0, r(v, 3), r(f, 2), phase]);
          break;
        }
        x = nx; y = ny;
      }
      if (y > 0.05) lifted = true;
      t += dt;
      v = Math.hypot(vx, vy);
      apogee = Math.max(apogee, y);
      max_v = Math.max(max_v, v);
      if (wantSamples && t >= next_sample) {
        pts.push([r(t, 4), r(x, 3), r(y, 3), r(v, 3), r(f, 2), phase]);
        next_sample = t + (phase !== "coast" ? 0.002 : 0.02);
      }
    }
    var flew = lifted && landed_x !== null;
    return {
      params: p, flew: flew,
      range_m: flew ? r(landed_x, 2) : 0.0,
      apogee_m: flew ? r(apogee, 2) : 0.0,
      flight_time_s: flew ? r(t, 2) : 0.0,
      max_speed_ms: r(max_v, 2),
      peak_thrust_n: r(max_f, 1),
      max_accel_g: r(max_a / G, 1),
      water_thrust_s: t_water !== null ? r(t_water, 3) : 0.0,
      thrust_s: r(t_air_end !== null ? t_air_end : (t_water || 0.0), 3),
      water_left_ml: Math.round(water_left * 1e6),
      water_ml: Math.round(vb * p.fill * 1e6),
      stable: stable, stability_cal: STABILITY_CAL[p.fins],
      cd: r(stable ? cd : TUMBLE_CD, 2),
      samples: wantSamples ? pts : null
    };
  }

  function score(res, goal) { return goal === "height" ? res.apogee_m : res.range_m; }

  function sweepFill(params, goal, lo, hi, step) {
    var p = clean(params), curve = [], f, res, best = null, i, q;
    lo = lo === undefined ? 0.02 : lo; hi = hi === undefined ? 0.8 : hi; step = step || 0.02;
    for (f = lo; f <= hi + 1e-9; f += step) {
      q = {}; for (i in p) q[i] = p[i];
      q.fill = r(f, 4);
      res = simulate(q);
      curve.push([r(f, 4), score(res, goal)]);
    }
    for (i = 0; i < curve.length; i++) if (!best || curve[i][1] > best[1]) best = curve[i];
    if (!best) best = [p.fill, 0];
    return { curve: curve, best_fill: best[0], best_value: best[1], goal: goal || "range" };
  }

  var api = { simulate: simulate, sweepFill: sweepFill, clean: clean, DEFAULTS: DEFAULTS, bodyDiameter: bodyDiameter };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AFPhysics = api;
})(typeof window !== "undefined" ? window : this);
