(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LEVEL_NAMES = { 1: "Sounds & Words", 2: "Sentences", 3: "Explain it", 4: "Your projects", 5: "Interview" };
  const SHORT_NAMES = { 1: "Sounds", 2: "Sentences", 3: "Explain it", 4: "Projects", 5: "Interview" };
  const KEY = "meuingles.auth";

  const state = {
    auth: null,
    level: 1,
    userLevel: 1,
    items: {},
    index: {},
    adhoc: null,
    homeDirty: true,
    progressDirty: true,
  };

  /* ---------- utilidades ---------- */
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function toast(msg, ms = 3200) {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
  }
  function loadAuth() { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } }
  function saveAuth(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} }
  function clearAuth() { try { localStorage.removeItem(KEY); } catch (e) {} }

  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (state.auth) { headers["X-User-Id"] = state.auth.uid; headers["X-Access-Code"] = state.auth.code; }
    const res = await fetch("api/" + path, { ...opts, headers });
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (res.status === 401 && path !== "signin") { logout("Sua sessão expirou. Entre novamente."); throw new Error("401"); }
    if (!res.ok) throw new Error((data && data.detail) || "Erro " + res.status + ". Tente de novo.");
    return data;
  }

  /* ---------- navegação ---------- */
  const SCREENS = ["login", "home", "practice", "interview", "progress"];
  function show(name) {
    SCREENS.forEach((n) => ($("#s-" + n).hidden = n !== name));
    $$("#tabs [data-tab]").forEach((t) => t.setAttribute("aria-selected", t.dataset.tab === name));
    if (name === "home" && state.homeDirty) loadHome();
    if (name === "progress" && state.progressDirty) loadProgress();
    if (name === "practice") { renderItem(); drawWave(0, false); }
    window.scrollTo(0, 0);
  }
  $$("#tabs [data-tab]").forEach((t) => t.addEventListener("click", () => show(t.dataset.tab)));
  $$("[data-go]").forEach((b) => b.addEventListener("click", () => show(b.dataset.go)));
  $("#goStar").addEventListener("click", () => { selectLevel(4); show("practice"); });

  function setPill(level) {
    state.userLevel = level;
    const p = $("#levelPill");
    p.textContent = "Nível " + level + " · " + SHORT_NAMES[level];
    p.hidden = false;
  }

  /* ---------- login ---------- */
  function logout(msg) {
    clearAuth(); state.auth = null;
    $("#tabs").hidden = true; $("#levelPill").hidden = true; $("#logoutBtn").hidden = true;
    show("login");
    if (msg) { $("#loginError").textContent = msg; $("#loginError").hidden = false; }
  }
  $("#logoutBtn").addEventListener("click", () => logout());
  $("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("#nameInput").value.trim();
    const code = $("#codeInput").value;
    const err = $("#loginError");
    if (!name || !code) { err.textContent = "Preencha o nome e o código de acesso."; err.hidden = false; return; }
    err.hidden = true;
    try {
      const prev = loadAuth();
      const r = await api("signin", { method: "POST", body: JSON.stringify({ name, access_code: code, user_id: prev && prev.uid }) });
      state.auth = { uid: r.user_id, code, name };
      saveAuth(state.auth);
      start();
    } catch (ex) { err.textContent = ex.message; err.hidden = false; }
  });

  /* ---------- início ---------- */
  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }
  async function loadHome() {
    try {
      const h = await api("home");
      state.homeDirty = false;
      setPill(h.level);
      $("#helloTitle").textContent = greeting() + ", " + h.name.split(" ")[0];
      const left = h.to_next.needed - h.to_next.done;
      $("#helloSub").textContent = h.to_next.max_level
        ? "Você está no nível 4. O nível 5 chega com o simulador de entrevista."
        : "Faltam " + left + " tentativa" + (left === 1 ? "" : "s") + " seguidas com 80 ou mais para subir ao nível " + (h.level + 1) + ".";
      $("#trackLabel").textContent = h.level + " de 5";
      const bar = $("#levelsBar"); bar.innerHTML = "";
      for (let i = 1; i <= 5; i++) {
        const d = document.createElement("div");
        d.className = "lv" + (i < h.level ? " done" : "");
        if (i === h.level) {
          const pct = Math.round((h.to_next.done / h.to_next.needed) * 100);
          d.style.background = "linear-gradient(90deg, var(--accent) " + pct + "%, var(--line) " + pct + "%)";
        }
        bar.appendChild(d);
      }
      $("#stStreak").textContent = h.streak;
      $("#stAvg").textContent = h.avg7 ?? "–";
      $("#stTotal").textContent = h.total;
      const ul = $("#reviewList");
      ul.innerHTML = h.review.map((r) =>
        '<li><button data-review="' + esc(r.word) + '" data-ipa="' + esc(r.ipa) + '"><span><b>' + esc(r.word) + "</b> " +
        (r.ipa ? '<span class="ipa">' + esc(r.ipa) + "</span>" : "") + '</span><span class="due">intervalo ' + r.interval + "d</span></button></li>").join("");
      $("#reviewEmpty").hidden = h.review.length > 0;
      ul.querySelectorAll("[data-review]").forEach((b) => b.addEventListener("click", () => {
        practiceAdhoc({ id: "r:" + b.dataset.review, text: b.dataset.review, ipa: b.dataset.ipa, kind: "word", hint: "Revisão do caderno de erros.", label: "Revisão" });
      }));
      if (!state.items[state.level]) selectLevel(Math.min(h.level, 4), true);
    } catch (e) { if (e.message !== "401") toast(e.message); }
  }

  /* ---------- treino ---------- */
  async function selectLevel(lv, silent) {
    state.level = lv; state.adhoc = null;
    $$("#levelChips [data-lv]").forEach((c) => c.setAttribute("aria-pressed", String(+c.dataset.lv === lv)));
    if (!state.items[lv]) {
      try {
        const r = await api("content/" + lv);
        state.items[lv] = r.items;
        state.index[lv] = state.index[lv] ?? Math.floor(Math.random() * r.items.length);
      } catch (e) { if (e.message !== "401") toast(e.message); return; }
    }
    if (!silent || !$("#s-practice").hidden) renderItem();
  }
  $$("#levelChips [data-lv]").forEach((c) => c.addEventListener("click", () => selectLevel(+c.dataset.lv)));

  function currentItem() {
    if (state.adhoc) return state.adhoc;
    const list = state.items[state.level];
    return list ? list[state.index[state.level]] : null;
  }
  const LABELS = { word: "Pronuncie a palavra", sentence: "Repita a frase", explain: "Explique em inglês", star: "Responda no formato STAR" };
  function renderItem() {
    const it = currentItem();
    if (!it) return;
    $("#pLabel").textContent = it.label || LABELS[it.kind];
    $("#pText").textContent = it.text;
    $("#pIpa").textContent = it.ipa || "";
    $("#pIpa").hidden = !it.ipa;
    $("#pHint").textContent = it.hint || "";
    const list = state.items[state.level];
    $("#pCounter").textContent = state.adhoc || !list ? "" : (state.index[state.level] + 1) + "/" + list.length;
    const open = it.kind === "explain" || it.kind === "star";
    $("#recNote").textContent = open ? "Toque para começar e toque de novo quando terminar" : "Toque para gravar";
    $("#listenBtn").lastChild.textContent = open ? "Ouvir a pergunta" : "Ouvir pronúncia";
    $("#liveText").textContent = "";
    $("#result").innerHTML = "";
  }
  function step(d) {
    const list = state.items[state.level];
    if (!list) return;
    if (!state.adhoc) state.index[state.level] = (state.index[state.level] + d + list.length) % list.length;
    state.adhoc = null;
    renderItem();
  }
  $("#prevBtn").addEventListener("click", () => step(-1));
  $("#nextBtn").addEventListener("click", () => step(1));
  function practiceAdhoc(item) {
    state.adhoc = item;
    $$("#levelChips [data-lv]").forEach((c) => c.setAttribute("aria-pressed", "false"));
    show("practice");
  }

  /* ---------- voz nativa (TTS do navegador) ---------- */
  let voice = null;
  function pickVoice() {
    try {
      const vs = speechSynthesis.getVoices().filter((v) => /^en[-_]US/i.test(v.lang));
      voice = vs.find((v) => /Google/.test(v.name)) || vs[0] || null;
    } catch (e) {}
  }
  if ("speechSynthesis" in window) { pickVoice(); speechSynthesis.onvoiceschanged = pickVoice; }
  function say(text) {
    if (!("speechSynthesis" in window)) { toast("Este navegador não tem voz em inglês."); return; }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = 0.9; if (voice) u.voice = voice;
    speechSynthesis.speak(u);
  }
  $("#listenBtn").addEventListener("click", () => { const it = currentItem(); if (it) say(it.text); });

  /* ---------- onda (decorativa) ---------- */
  const cv = $("#wave"), cx = cv.getContext("2d");
  function drawWave(t, live) {
    const W = cv.width, H = cv.height, n = 64, bw = W / n;
    cx.clearRect(0, 0, W, H);
    const st = getComputedStyle(document.documentElement);
    cx.fillStyle = (live ? st.getPropertyValue("--rec") : st.getPropertyValue("--line")).trim() || "#999";
    for (let i = 0; i < n; i++) {
      const base = Math.abs(Math.sin(i * 0.45) + Math.sin(i * 0.17 + 1.3)) * 0.4;
      const amp = live ? 0.25 + 0.75 * Math.abs(Math.sin(i * 0.6 + t * 0.012) * Math.cos(i * 0.21 - t * 0.007)) : 0.12 + base * 0.35;
      const h = Math.max(4, amp * H * 0.9);
      cx.beginPath();
      if (cx.roundRect) cx.roundRect(i * bw + 2, (H - h) / 2, bw - 4, h, 3); else cx.rect(i * bw + 2, (H - h) / 2, bw - 4, h);
      cx.fill();
    }
  }

  /* ---------- gravação (reconhecimento de voz do navegador) ---------- */
  const rec = { active: false, userStopped: false, fatal: null, finals: [], confs: [], session: "", started: 0, sr: null, timer: null, open: false };

  function setRecUI(on) {
    const b = $("#recBtn");
    b.classList.toggle("on", on);
    b.setAttribute("aria-label", on ? "Parar" : "Gravar");
    if (on) {
      const loop = (now) => { if (!rec.active) { drawWave(0, false); return; } drawWave(now - rec.started, true); if (!reduce) requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
    } else drawWave(0, false);
  }

  function startRec() {
    const it = currentItem();
    if (!it) return;
    if (!SR) {
      $("#result").innerHTML = '<div class="notice">Este navegador não reconhece fala. Use o Google Chrome no Android ou no computador.</div>';
      return;
    }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    Object.assign(rec, { active: true, userStopped: false, fatal: null, finals: [], confs: [], session: "", started: performance.now(), open: it.kind === "explain" || it.kind === "star" });
    const sr = new SR();
    sr.lang = "en-US"; sr.interimResults = true; sr.continuous = false; sr.maxAlternatives = 1;
    rec.sr = sr;
    sr.onresult = (e) => {
      let fin = "", interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) { fin += r[0].transcript + " "; if (r[0].confidence > 0) rec.confs.push(r[0].confidence); }
        else interim += r[0].transcript;
      }
      rec.session = fin.trim();
      $("#liveText").textContent = (rec.finals.join(" ") + " " + rec.session + " " + interim).trim();
    };
    sr.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") rec.fatal = "Permita o uso do microfone para este site nas configurações do navegador.";
      else if (e.error === "network") rec.fatal = "O reconhecimento de voz precisa de internet. Verifique a conexão.";
      else if (e.error === "audio-capture") rec.fatal = "Nenhum microfone encontrado.";
    };
    sr.onend = () => {
      if (rec.session) { rec.finals.push(rec.session); rec.session = ""; }
      const elapsed = performance.now() - rec.started;
      if (rec.open && !rec.userStopped && !rec.fatal && elapsed < 180000) {
        try { sr.start(); return; } catch (e) {}
      }
      finishRec();
    };
    try { sr.start(); } catch (e) { rec.active = false; toast("Não foi possível iniciar o microfone."); return; }
    setRecUI(true);
    $("#recNote").textContent = rec.open ? "Gravando… toque para terminar" : "Gravando… fale agora";
    $("#liveText").textContent = "";
    $("#result").innerHTML = "";
    clearTimeout(rec.timer);
    rec.timer = setTimeout(() => { rec.userStopped = true; try { sr.stop(); } catch (e) {} }, rec.open ? 180000 : 15000);
  }

  function stopRec() { rec.userStopped = true; try { rec.sr && rec.sr.stop(); } catch (e) { finishRec(); } }

  async function finishRec() {
    if (!rec.active) return;
    rec.active = false;
    clearTimeout(rec.timer);
    setRecUI(false);
    const it = currentItem();
    const transcript = rec.finals.join(" ").trim();
    const duration = Math.round(performance.now() - rec.started);
    $("#recNote").textContent = it && (it.kind === "explain" || it.kind === "star") ? "Toque para começar e toque de novo quando terminar" : "Toque para gravar";
    if (rec.fatal) { $("#result").innerHTML = '<div class="notice">' + esc(rec.fatal) + "</div>"; return; }
    if (!transcript) { $("#result").innerHTML = '<div class="notice">Não ouvi nada. Fale um pouco mais alto e perto do microfone.</div>'; return; }
    const conf = rec.confs.length ? rec.confs.reduce((a, b) => a + b, 0) / rec.confs.length : null;
    $("#recNote").textContent = "Analisando…";
    $("#recBtn").disabled = true;
    try {
      const r = await api("attempts", { method: "POST", body: JSON.stringify({ item_id: it.id, transcript, confidence: conf, duration_ms: duration }) });
      state.homeDirty = state.progressDirty = true;
      renderResult(r, it);
      if (r.level_up) { setPill(r.level_up); toast("Você subiu para o nível " + r.level_up + " · " + r.level_up_name); }
    } catch (e) {
      if (e.message !== "401") $("#result").innerHTML = '<div class="notice">' + esc(e.message) + "</div>";
    } finally {
      $("#recBtn").disabled = false;
      $("#recNote").textContent = it.kind === "explain" || it.kind === "star" ? "Toque para começar e toque de novo quando terminar" : "Toque para gravar";
    }
  }

  $("#recBtn").addEventListener("click", () => (rec.active ? stopRec() : startRec()));

  /* ---------- resultado ---------- */
  function color(v) { return v >= 80 ? "var(--good)" : v >= 60 ? "var(--warn)" : "var(--bad)"; }
  function ring(v, name, suffix) {
    if (v === null || v === undefined) return '<div class="score"><svg class="ring" viewBox="0 0 58 58" role="img" aria-label="' + name + ' indisponível"><circle cx="29" cy="29" r="24" fill="none" stroke="var(--line)" stroke-width="5"/><text x="29" y="34" text-anchor="middle" font-size="16" fill="var(--muted)">–</text></svg><span>' + name + "</span></div>";
    const C = 2 * Math.PI * 24, d = (C * Math.min(v, 100)) / 100;
    return '<div class="score"><svg class="ring" viewBox="0 0 58 58" role="img" aria-label="' + name + " " + v + '">' +
      '<circle cx="29" cy="29" r="24" fill="none" stroke="var(--line)" stroke-width="5"/>' +
      (suffix === "num" ? "" : '<circle cx="29" cy="29" r="24" fill="none" stroke="' + color(v) + '" stroke-width="5" stroke-linecap="round" stroke-dasharray="' + d + " " + C + '" transform="rotate(-90 29 29)"/>') +
      '<text x="29" y="34" text-anchor="middle" font-family="Bricolage Grotesque, sans-serif" font-weight="700" font-size="16" fill="var(--ink)">' + v + "</text></svg><span>" + name + "</span></div>";
  }
  function renderResult(r, it) {
    const s = r.scores;
    let html = "";
    if (r.level_up) html += '<div class="block levelup"><span class="label">Novo nível</span><h3>Nível ' + r.level_up + " · " + esc(r.level_up_name) + "</h3><p class=\"muted\">Cinco tentativas seguidas com 80 ou mais. O nível novo já aparece nos chips acima.</p></div>";
    if (it.kind === "word" || it.kind === "sentence") {
      html += '<div class="block"><div class="row"><span class="label">Resultado · reconhecimento do navegador</span></div>' +
        '<div class="scores">' + ring(s.accuracy, "Acerto") + ring(s.completeness, "Completude") + ring(s.confidence, "Confiança") + "</div>" +
        '<div class="words">' + r.words.map((w) => '<span class="w ' + w.status + '" title="' + esc(w.heard || "") + '">' + esc(w.display) + "</span>").join("") + "</div>" +
        '<p class="heard">O reconhecedor entendeu: <b>“' + esc(r.transcript) + '”</b></p></div>';
    } else {
      const d = r.detail || {};
      let chips = "";
      if (d.keywords_used) chips = d.keywords_used.map((k) => '<span class="w ok">' + esc(k) + "</span>").join("") + (d.keywords_missing || []).map((k) => '<span class="w missing">' + esc(k) + "</span>").join("");
      if (d.star) { const nm = { situation: "Situação", task: "Tarefa", action: "Ação", result: "Resultado" }; chips = Object.entries(d.star).map(([k, ok]) => '<span class="w ' + (ok ? "ok" : "missing") + '">' + nm[k] + "</span>").join(""); }
      html += '<div class="block"><div class="row"><span class="label">Resultado · ' + (it.kind === "explain" ? "termos técnicos" : "estrutura STAR") + "</span></div>" +
        '<div class="scores">' + ring(s.coverage, it.kind === "explain" ? "Cobertura" : "Estrutura") + ring(s.words, "Palavras", "num") + ring(s.wpm, "Palavras/min", "num") + "</div>" +
        '<div class="words">' + chips + "</div>" +
        '<p class="heard">Transcrição: <b>“' + esc(r.transcript) + '”</b></p></div>';
    }
    if (r.tips.length) html += '<div class="block"><div class="row"><span class="label">Onde melhorar</span></div><ul class="tips">' +
      r.tips.map((t) => "<li>" + (t.word ? '<span class="tw">' + esc(t.word) + "</span>" + (t.ipa ? '<span class="tipa">' + esc(t.ipa) + "</span>" : "") + "<br>" : "") + esc(t.text) + "</li>").join("") + "</ul></div>";
    if (r.drills.length) html += '<div class="block"><div class="row"><span class="label">Treine agora</span></div><ul class="drills">' +
      r.drills.map((d, i) => "<li><span>" + esc(d.text) + '</span><span class="acts"><button class="play" data-say="' + i + '" aria-label="Ouvir"><svg viewBox="0 0 10 10"><path d="M2 1l7 4-7 4z"/></svg></button><button class="btn ghost small" data-drill="' + i + '">Treinar</button></span></li>').join("") + "</ul></div>";
    const box = $("#result");
    box.innerHTML = html;
    box.querySelectorAll("[data-say]").forEach((b) => b.addEventListener("click", () => say(r.drills[+b.dataset.say].text)));
    box.querySelectorAll("[data-drill]").forEach((b) => b.addEventListener("click", () => {
      const d = r.drills[+b.dataset.drill];
      const isWord = d.id.startsWith("r:");
      const ipa = (r.tips.find((t) => t.word.toLowerCase() === d.text.toLowerCase()) || {}).ipa || "";
      practiceAdhoc({ id: d.id, text: d.text, ipa, kind: isWord ? "word" : "sentence", hint: "Exercício sugerido pelo seu último resultado.", label: "Treino sugerido" });
    }));
    box.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }

  /* ---------- evolução ---------- */
  async function loadProgress() {
    try {
      const p = await api("progress");
      state.progressDirty = false;
      $("#chartBox").innerHTML = p.daily.length ? chart(p.daily) : '<p class="empty">O gráfico aparece depois do seu primeiro dia de treino nos níveis 1 e 2.</p>';
      const max = Math.max(1, ...p.missed.map((m) => m.n));
      $("#errs").innerHTML = p.missed.length
        ? p.missed.map((m) => '<span class="p">' + esc(m.word) + (m.ipa ? ' <span class="ipa">' + esc(m.ipa) + "</span>" : "") + '</span><div class="bar"><i style="width:' + (m.n / max) * 100 + '%"></i></div><span>' + m.n + "</span>").join("")
        : '<p class="empty" style="grid-column:1/-1">Nenhum erro registrado ainda.</p>';
      $("#levelTable").innerHTML = p.by_level.length
        ? p.by_level.map((l) => "<tr><td>" + l.level + " · " + esc(l.name) + "</td><td>" + l.n + "</td><td>" + l.avg + "</td></tr>").join("")
        : '<tr><td colspan="3" class="empty">Sem tentativas ainda.</td></tr>';
    } catch (e) { if (e.message !== "401") toast(e.message); }
  }
  function chart(days) {
    const W = 380, H = 190, L = 30, R = 14, T = 14, B = 26;
    const vals = days.map((d) => d.avg);
    const min = Math.max(0, Math.min(50, Math.floor((Math.min(...vals) - 5) / 10) * 10)), max = 100;
    const n = days.length;
    const x = (i) => (n === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (n - 1));
    const y = (v) => T + ((max - v) * (H - T - B)) / (max - min);
    const ticks = []; for (let v = min; v <= max; v += min <= 30 ? 20 : 10) ticks.push(v);
    const fmt = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7);
    let g = ticks.map((v) => '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--line)"/><text x="' + (L - 6) + '" y="' + (y(v) + 3.5) + '" text-anchor="end">' + v + "</text>").join("");
    const pts = days.map((d, i) => x(i) + "," + y(d.avg)).join(" ");
    const last = n - 1;
    let area = n > 1 ? '<path d="M' + x(0) + "," + y(min) + " L" + pts.replace(/ /g, " L") + " L" + x(last) + "," + y(min) + ' Z" fill="var(--accent)" fill-opacity=".12"/>' : "";
    return '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Acerto médio por dia">' + g +
      '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(80) + '" y2="' + y(80) + '" stroke="var(--good)" stroke-dasharray="4 4" stroke-width="1.2"/>' +
      '<text x="' + (L + 4) + '" y="' + (y(80) - 5) + '" style="fill:var(--good)">meta do nível · 80</text>' + area +
      (n > 1 ? '<polyline points="' + pts + '" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round"/>' : "") +
      '<circle cx="' + x(last) + '" cy="' + y(vals[last]) + '" r="4.5" fill="var(--accent)"/>' +
      '<text x="' + (x(last) - 8) + '" y="' + (y(vals[last]) - 9) + '" text-anchor="end" style="fill:var(--ink);font-weight:600">' + vals[last] + "</text>" +
      '<text x="' + x(0) + '" y="' + (H - 8) + '"' + (n === 1 ? ' text-anchor="middle"' : "") + ">" + fmt(days[0].day) + "</text>" +
      (n > 1 ? '<text x="' + x(last) + '" y="' + (H - 8) + '" text-anchor="end">' + fmt(days[last].day) + "</text>" : "") + "</svg>";
  }

  /* ---------- início do app ---------- */
  function start() {
    $("#tabs").hidden = false; $("#logoutBtn").hidden = false;
    state.homeDirty = state.progressDirty = true;
    show("home");
  }
  state.auth = loadAuth();
  if (state.auth && state.auth.uid && state.auth.code) start();
  else { const prev = loadAuth(); if (prev && prev.name) $("#nameInput").value = prev.name; show("login"); }
})();
