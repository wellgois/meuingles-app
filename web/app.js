(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LEVEL_NAMES = { 1: "Sounds & Words", 2: "Sentences", 3: "Explain it", 4: "Your projects", 5: "Interview" };
  const SHORT_NAMES = { 1: "Sounds", 2: "Sentences", 3: "Explain it", 4: "Projects", 5: "Interview" };
  const KEY = "meuingles.session";

  const state = {
    auth: null,
    level: 1,
    userLevel: 1,
    items: {},
    index: {},
    adhoc: null,
    homeDirty: true,
    progressDirty: true,
    azure: false,
    llm: false,
    forceBrowser: false,
    queue: null,
    qIdx: 0,
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
    if (state.auth) headers.Authorization = "Bearer " + state.auth.token;
    const res = await fetch("api/" + path, { ...opts, headers });
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (res.status === 401 && !path.startsWith("auth/") && path !== "me/delete") { logout("Sua sessão expirou. Entre novamente."); throw new Error("401"); }
    if (!res.ok) throw new Error((data && data.detail) || "Erro " + res.status + ". Tente de novo.");
    return data;
  }

  /* ---------- navegação ---------- */
  const SCREENS = ["login", "home", "practice", "interview", "progress", "billing"];
  function show(name) {
    SCREENS.forEach((n) => ($("#s-" + n).hidden = n !== name));
    $$("#tabs [data-tab]").forEach((t) => t.setAttribute("aria-selected", t.dataset.tab === name));
    if (name === "home" && state.homeDirty) loadHome();
    if (name === "progress" && state.progressDirty) loadProgress();
    if (name === "billing" && state.account) renderBilling(state.account);
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

  /* ---------- conta: cadastro, login e senha ---------- */
  let authMode = "signup", resetToken = null;
  function setAuthMode(mode, msg) {
    authMode = mode;
    $("#tabSignup").setAttribute("aria-pressed", String(mode === "signup"));
    $("#tabLogin").setAttribute("aria-pressed", String(mode === "login"));
    $("#authTabs").hidden = mode === "forgot" || mode === "reset";
    $("#fName").hidden = mode !== "signup";
    $("#fTerms").hidden = mode !== "signup";
    $("#fTrack").hidden = mode !== "signup";
    $("#fEmail").hidden = mode === "reset";
    $("#fPass").hidden = mode === "forgot";
    $("#passLabel").textContent = mode === "login" ? "Senha" : mode === "reset" ? "Nova senha (mínimo 8 caracteres)" : "Senha (mínimo 8 caracteres)";
    $("#passInput").setAttribute("autocomplete", mode === "login" ? "current-password" : "new-password");
    $("#forgotBtn").hidden = mode !== "login";
    $("#authSubmit").textContent = { signup: "Criar conta grátis", login: "Entrar", forgot: "Enviar link", reset: "Salvar nova senha" }[mode];
    const intro = { forgot: "Digite o e-mail da sua conta. Enviaremos um link para criar uma nova senha.", reset: "Crie uma nova senha para sua conta." }[mode];
    $("#authIntro").textContent = intro || ""; $("#authIntro").hidden = !intro;
    $("#authError").hidden = true; $("#authOk").hidden = !msg; $("#authOk").textContent = msg || "";
  }
  $("#tabSignup").addEventListener("click", () => setAuthMode("signup"));
  $("#tabLogin").addEventListener("click", () => setAuthMode("login"));
  $("#forgotBtn").addEventListener("click", () => setAuthMode("forgot"));

  function logout(msg) {
    if (state.auth) fetch("api/auth/logout", { method: "POST", headers: { Authorization: "Bearer " + state.auth.token } }).catch(() => {});
    clearAuth(); state.auth = null;
    $("#tabs").hidden = true; $("#levelPill").hidden = true; $("#logoutBtn").hidden = true;
    show("login");
    setAuthMode("login");
    if (msg) { $("#authError").textContent = msg; $("#authError").hidden = false; }
  }
  $("#logoutBtn").addEventListener("click", () => logout());

  $("#authForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#authError"), ok = $("#authOk");
    err.hidden = true; ok.hidden = true;
    const name = $("#nameInput").value.trim(), email = $("#emailInput").value.trim(), password = $("#passInput").value;
    const fail = (m) => { err.textContent = m; err.hidden = false; };
    if (authMode !== "reset" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail("Digite um e-mail válido.");
    if (authMode === "signup" && !name) return fail("Digite seu nome.");
    const track = $("#trackInput").value;
    if ((authMode === "signup" || authMode === "reset") && password.length < 8) return fail("A senha precisa ter pelo menos 8 caracteres.");
    if (authMode === "login" && !password) return fail("Digite sua senha.");
    if (authMode === "signup" && !track) return fail("Escolha a vaga que você busca.");
    if (authMode === "signup" && !$("#termsInput").checked) return fail("Para criar a conta, aceite os termos de uso e a política de privacidade.");
    $("#authSubmit").disabled = true;
    try {
      if (authMode === "forgot") {
        await api("auth/forgot", { method: "POST", body: JSON.stringify({ email }) });
        setAuthMode("login", "Se existir uma conta com esse e-mail, enviamos o link. Confira também o spam.");
        return;
      }
      const path = { signup: "auth/signup", login: "auth/login", reset: "auth/reset" }[authMode];
      const body = authMode === "signup" ? { name, email, password, accept_terms: true, track, ...(window.miAttr ? window.miAttr() : {}) }
        : authMode === "reset" ? { token: resetToken, password } : { email, password };
      const r = await api(path, { method: "POST", body: JSON.stringify(body) });
      state.auth = { token: r.token }; saveAuth(state.auth);
      $("#passInput").value = "";
      start();
      if (authMode === "signup") toast(r.email_sent ? "Conta criada! Confirme seu e-mail para começar." : "Conta criada!");
      if (authMode === "reset") toast("Senha alterada.");
    } catch (ex) { if (ex.message !== "401") fail(ex.message); }
    finally { $("#authSubmit").disabled = false; }
  });

  /* ---------- situação da conta ---------- */
  function renderAccount(a) {
    state.account = a;
    $("#accEmail").textContent = a.email || "";
    $("#trackSel").value = a.track || "";
    $("#delWrap").hidden = a.plan === "owner";
    $("#cancelWrap").hidden = !(a.plan === "active" && !a.canceled && a.mp_status === "authorized");
    const price = "R$ " + Number(a.price || 29.9).toFixed(2).replace(".", ",");
    const subForm = (label) => a.billing
      ? '<div class="subform"><label class="field"><span class="label">E-mail da sua conta do Mercado Pago</span>' +
        '<input id="payerInput" type="email" autocomplete="email" maxlength="200" value="' + esc(a.mp_payer_email || a.email || "") + '"></label>' +
        '<button class="btn small" id="subBtn">' + label + "</button></div>"
      : (a.wants_subscription ? "<br>Você está na lista: avisaremos por e-mail." : '<br><button class="btn small" id="wantBtn">Quero assinar quando abrir</button>');
    const pending = a.mp_status === "pending" && a.plan !== "active"
      ? '<p class="sub-pending">Começou a assinatura e já pagou? <button class="linkbtn" id="syncBtn">Verificar pagamento</button></p>' : "";
    let h = "";
    if (a.plan !== "owner" && !a.email_verified) {
      h = '<div class="banner warn"><b>Confirme seu e-mail para começar a treinar.</b> Enviamos um link para ' + esc(a.email) +
        '. <button class="linkbtn" id="resendBtn">Reenviar e-mail</button></div>';
    } else if (a.plan === "trial") {
      h = '<div class="banner"><b>Teste grátis:</b> ' + (a.days_left === 1 ? "último dia" : "faltam " + a.days_left + " dias") +
        " · " + a.audio_used_min + " de " + a.audio_limit_min + " min de áudio avaliado" +
        (a.billing && a.days_left <= 2 ? "<br>Para continuar depois do teste, assine por " + price + " por mês." + subForm("Assinar com Mercado Pago") : "") +
        (a.billing && a.days_left > 2 ? '<br><button class="linkbtn" id="goBilling">Assinar agora</button>' : "") +
        pending + "</div>";
    } else if (a.plan === "active" && a.canceled) {
      h = '<div class="banner"><b>Assinatura cancelada.</b> Você tem acesso até ' + new Date(a.paid_until).toLocaleDateString("pt-BR") +
        "." + subForm("Assinar de novo") + "</div>";
    } else if (a.plan === "active" && a.mp_status !== "authorized") {
      h = '<div class="banner"><b>Acesso ativo até ' + new Date(a.paid_until).toLocaleDateString("pt-BR") + "</b> · pago por Pix · " +
        a.audio_used_min + " de " + a.audio_limit_min + " min de áudio avaliado este mês</div>";
    } else if (a.plan === "active") {
      h = '<div class="banner"><b>Plano mensal ativo</b> · ' + a.audio_used_min + " de " + a.audio_limit_min + " min de áudio avaliado este mês</div>";
    } else if (a.plan === "expired") {
      h = '<div class="banner warn"><b>Seu acesso terminou.</b> Seu histórico continua salvo. Para continuar treinando, assine por ' +
        price + " por mês e cancele quando quiser." + subForm("Assinar com Mercado Pago") + pending + "</div>";
    }
    $("#accountBanner").innerHTML = h;
    if ($("#subBtn")) $("#subBtn").addEventListener("click", async (e) => {
      const payer = $("#payerInput").value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(payer)) { toast("Digite o e-mail da sua conta do Mercado Pago."); return; }
      e.target.disabled = true;
      try { const r = await api("billing/subscribe", { method: "POST", body: JSON.stringify({ payer_email: payer }) }); location.href = r.url; }
      catch (ex) { e.target.disabled = false; if (ex.message !== "401") toast(ex.message); }
    });
    if ($("#syncBtn")) $("#syncBtn").addEventListener("click", () => syncBilling());
    if ($("#goBilling")) $("#goBilling").addEventListener("click", () => show("billing"));
    if ($("#resendBtn")) $("#resendBtn").addEventListener("click", async () => {
      try { const r = await api("auth/resend", { method: "POST" }); toast(r.already ? "Seu e-mail já está confirmado." : r.sent ? "E-mail reenviado. Confira também o spam." : "Não consegui enviar agora. Tente mais tarde."); }
      catch (e) { if (e.message !== "401") toast(e.message); }
    });
    if ($("#wantBtn")) $("#wantBtn").addEventListener("click", async () => {
      try { await api("me/interest", { method: "POST" }); a.wants_subscription = true; renderAccount(a); toast("Anotado! Avisaremos quando a assinatura abrir."); }
      catch (e) { if (e.message !== "401") toast(e.message); }
    });
    renderBilling(a);
    if (a.is_admin) loadAdmin(); else $("#adminBox").innerHTML = "";
  }
  /* ---------- aba Assinatura ---------- */
  function renderBilling(a) {
    const box = $("#billingBox");
    if (!box) return;
    const price = "R$ " + Number(a.price || 29.9).toFixed(2).replace(".", ",");
    const until = a.paid_until ? new Date(a.paid_until).toLocaleDateString("pt-BR") : "";
    const form = (label) => '<div class="subform"><label class="field"><span class="label">E-mail da sua conta do Mercado Pago</span>' +
      '<input id="bPayer" type="email" autocomplete="email" maxlength="200" value="' + esc(a.mp_payer_email || a.email || "") + '"></label>' +
      '<button class="btn" id="bSubBtn">' + label + "</button></div>" + pixBlock;
    const sync = (a.mp_status === "pending" && a.plan !== "active")
      ? '<p class="muted">Começou a assinatura e já pagou? <button class="linkbtn" id="bSyncBtn">Verificar pagamento</button></p>' : "";
    const pixBlock = '<div class="subform pix"><p class="muted">Prefere pagar sem cartão? O Pix libera 30 dias de acesso, sem renovação automática.</p>' +
      '<button class="btn ghost" id="bPixBtn">Pix · pagar ' + price + '</button><div id="pixBox"></div></div>';
    let h = '<span class="label">Assinatura</span><h3>Plano mensal · ' + price + "</h3>";
    if (a.plan === "owner") {
      h += '<p class="muted">A conta do dono não precisa de assinatura.</p>';
    } else if (!a.email_verified) {
      h += '<p class="muted">Confirme seu e-mail para poder assinar.</p>';
    } else if (!a.billing) {
      h += '<p class="muted">A assinatura ainda não está disponível.</p>';
    } else if (a.plan === "active" && !a.canceled && a.mp_status !== "authorized") {
      h += "<p><b>Acesso ativo" + (until ? " até " + until : "") + ".</b></p>" +
        '<p class="muted">Pago por Pix, sem renovação automática. Para continuar depois dessa data, pague outro Pix (os dias se somam) ou assine no cartão: a primeira cobrança só acontece em ' + until + '.</p>' + form("Assinar no cartão");
    } else if (a.plan === "active" && !a.canceled) {
      h += '<p><b>Assinatura ativa.</b>' + (until ? " Acesso garantido até " + until + "." : "") + "</p>" +
        '<p class="muted">A cobrança é mensal e você pode cancelar quando quiser. O acesso continua até o fim do período já pago.</p>' +
        '<button class="btn ghost" id="bCancelBtn">Cancelar assinatura</button>';
    } else if (a.plan === "active" && a.canceled) {
      h += "<p><b>Assinatura cancelada.</b>" + (until ? " Você tem acesso até " + until + "." : "") + "</p>" + form("Assinar de novo") + sync;
    } else if (a.plan === "trial") {
      h += "<p><b>Teste grátis:</b> " + (a.days_left === 1 ? "último dia" : "faltam " + a.days_left + " dias") + ".</p>" +
        '<p class="muted">Quer garantir o acesso sem interrupção? Você pode assinar agora. A cobrança de ' + price +
        " por mês começa assim que você autorizar no Mercado Pago, e dá para cancelar a qualquer momento.</p>" + form("Assinar com Mercado Pago") + sync;
    } else {
      h += "<p><b>Seu acesso terminou.</b> Seu histórico continua salvo.</p>" +
        '<p class="muted">Assine por ' + price + " por mês e cancele quando quiser.</p>" + form("Assinar com Mercado Pago") + sync;
    }
    box.innerHTML = h;
    if ($("#bSubBtn")) $("#bSubBtn").addEventListener("click", async (e) => {
      const payer = $("#bPayer").value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(payer)) { toast("Digite o e-mail da sua conta do Mercado Pago."); return; }
      e.target.disabled = true;
      try { const r = await api("billing/subscribe", { method: "POST", body: JSON.stringify({ payer_email: payer }) }); location.href = r.url; }
      catch (ex) { e.target.disabled = false; if (ex.message !== "401") toast(ex.message); }
    });
    if ($("#bSyncBtn")) $("#bSyncBtn").addEventListener("click", () => syncBilling());
    if ($("#bCancelBtn")) $("#bCancelBtn").addEventListener("click", () => $("#cancelSubBtn").click());
    if ($("#bPixBtn")) $("#bPixBtn").addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { showPix(await api("billing/pix", { method: "POST", body: "{}" })); }
      catch (ex) { e.target.disabled = false; if (ex.message !== "401") toast(ex.message); }
    });
  }
  let pixTimer = null;
  function showPix(r) {
    const box = $("#pixBox");
    if (!box) return;
    const img = r.qr_base64 ? '<img alt="QR Code Pix" class="pix-qr" src="data:image/png;base64,' + r.qr_base64 + '">' : "";
    box.innerHTML = img + '<p class="muted">Abra o app do seu banco, escolha Pix e leia o QR Code, ou use o código copia e cola:</p>' +
      '<textarea id="pixCode" class="pix-code" readonly rows="3"></textarea>' +
      '<button class="btn small" id="pixCopy">Copiar código</button>' +
      '<p class="muted" id="pixState">Aguardando o pagamento…</p>';
    $("#pixCode").value = r.qr_code;
    $("#pixCopy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(r.qr_code); toast("Código copiado."); }
      catch (_) { $("#pixCode").select(); toast("Selecione e copie o código."); }
    });
    clearInterval(pixTimer);
    let tries = 0;
    pixTimer = setInterval(async () => {
      tries++;
      if (!$("#pixState") || tries > 120) { clearInterval(pixTimer); return; }
      try {
        const s = await api("billing/pix/check", { method: "POST", body: JSON.stringify({ payment_id: r.payment_id }) });
        if (s.status === "approved") {
          clearInterval(pixTimer);
          toast("Pagamento confirmado! Bom treino.");
          state.homeDirty = true; loadHome();
        }
      } catch (_) { /* tenta de novo no próximo ciclo */ }
    }, 5000);
  }
  async function syncBilling(silent) {
    try {
      const r = await api("billing/sync", { method: "POST", body: "{}" });
      if (r.status === "authorized") toast("Assinatura ativa! Bom treino.");
      else if (!silent) toast(r.status === "pending" ? "O Mercado Pago ainda não confirmou o pagamento. Tente de novo em alguns minutos." : "Nenhuma assinatura ativa encontrada.");
      state.homeDirty = true; loadHome();
    } catch (ex) { if (ex.message !== "401") toast(ex.message); }
  }
  $("#cancelSubBtn").addEventListener("click", async () => {
    if (!confirm("Cancelar a assinatura? Não haverá novas cobranças e você continua com acesso até o fim do período pago.")) return;
    try { await api("billing/cancel", { method: "POST" }); toast("Assinatura cancelada."); state.homeDirty = true; loadHome(); }
    catch (ex) { if (ex.message !== "401") toast(ex.message); }
  });
  $("#trackSel").addEventListener("change", async (e) => {
    try {
      await api("me/track", { method: "POST", body: JSON.stringify({ track: e.target.value }) });
      if (state.account) state.account.track = e.target.value;
      delete state.items[4]; delete state.index[4];
      if (state.level === 4) selectLevel(4, true);
      toast("Trilha atualizada. As perguntas do nível 4 já mudaram.");
    } catch (ex) { if (ex.message !== "401") toast(ex.message); }
  });
  /* ---------- painel do administrador: estatísticas comerciais e leads ---------- */
  const adm = { seg: "all", q: "", order: "created_at", desc: true, offset: 0, limit: 25 };
  const aEsc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const SEG_LABEL = { all: "Todos", trial: "Em teste", trial_expiring: "Teste acaba em 2 dias", trial_inactive: "Em teste parados 3d+",
    near_quota: "Perto do limite de minutos", expired: "Teste vencido", expired_engaged: "Vencidos que treinaram", paying: "Assinantes",
    churned: "Cancelados", unverified: "E-mail não confirmado", want_to_pay: "Querem assinar", never_practiced: "Nunca treinaram" };
  const SEG_BADGE = { trial: "Teste", expired: "Vencido", paying: "Assinante", churned: "Cancelado" };
  const TRACK_LABEL = { junior: "Júnior", pleno: "Pleno", senior: "Sênior", especialista: "Especialista" };
  const aPct = (n, d) => (Number(d) ? Math.round((Number(n) / Number(d)) * 100) + "%" : "–");
  const aDate = (v) => (v ? new Date(v).toLocaleDateString("pt-BR") : "–");
  const aAgo = (v) => {
    if (!v) return "nunca";
    const d = Math.floor((Date.now() - new Date(v).getTime()) / 86400000);
    return d <= 0 ? "hoje" : d === 1 ? "ontem" : "há " + d + " dias";
  };
  const aDelta = (now, prev) => {
    now = Number(now); prev = Number(prev);
    if (!prev) return "";
    const p = Math.round(((now - prev) / prev) * 100);
    return (p > 0 ? "+" : "") + p + "% vs. semana anterior";
  };
  function fillSegSelect(counts) {
    const sel = $("#admSeg");
    if (!sel) return;
    sel.innerHTML = Object.keys(SEG_LABEL).map((k) => '<option value="' + k + '"' + (k === adm.seg ? " selected" : "") + ">" +
      SEG_LABEL[k] + (counts && counts[k] != null ? " (" + counts[k] + ")" : "") + "</option>").join("");
  }
  function leadCard(l) {
    const seg = l.segment;
    const wants = l.wants_subscription_at ? ' <span class="badge">quer assinar</span>' : "";
    const mail = l.email ? '<a href="mailto:' + aEsc(l.email) + '">' + aEsc(l.email) + "</a>" : "sem e-mail";
    const when = seg === "paying" || seg === "churned" ? "pago até " + aDate(l.paid_until) : "teste até " + aDate(l.trial_ends_at);
    return '<div class="lead"><div class="lead-top"><strong>' + aEsc(l.name) + '</strong><span><span class="badge b-' + seg + '">' +
      (SEG_BADGE[seg] || seg) + "</span>" + wants + "</span></div>" +
      '<div class="lead-mail">' + mail + (l.email_verified ? "" : " · e-mail não confirmado") + "</div>" +
      '<div class="lead-meta">cadastro ' + aDate(l.created_at) + " · nível " + l.level + " · trilha " + aEsc(TRACK_LABEL[l.target_level] || "–") + " · " + when + "</div>" +
      '<div class="lead-meta">origem ' + aEsc(SRC_LABEL[l.signup_source] || l.signup_source || "não registrada") + (l.signup_campaign ? " · campanha " + aEsc(l.signup_campaign) + (l.signup_content ? " / " + aEsc(l.signup_content) : "") : "") + "</div>" +
      '<div class="lead-meta">' + l.attempts + " treinos · último " + aAgo(l.last_at) + " · " + Number(l.azure_min) + " min de áudio" +
      (l.avg_score != null ? " · nota média " + l.avg_score : "") + "</div></div>";
  }
  function leadsQuery(limit, offset) {
    return "admin/leads?seg=" + encodeURIComponent(adm.seg) + "&q=" + encodeURIComponent(adm.q) + "&order=" + adm.order +
      "&desc=" + adm.desc + "&limit=" + limit + "&offset=" + offset;
  }
  async function loadLeads(reset) {
    if (reset) adm.offset = 0;
    try {
      const r = await api(leadsQuery(adm.limit, adm.offset));
      fillSegSelect(r.counts);
      const list = $("#admList");
      const html = r.items.map(leadCard).join("");
      if (reset) list.innerHTML = html || '<p class="muted">Nenhum lead neste filtro.</p>';
      else list.insertAdjacentHTML("beforeend", html);
      $("#admTotal").textContent = r.total + (r.total === 1 ? " lead" : " leads");
      $("#admMore").hidden = adm.offset + adm.limit >= r.total;
    } catch (e) { if (e.message !== "401") toast(e.message); }
  }
  async function exportLeads() {
    try {
      const r = await api(leadsQuery(2000, 0));
      const cols = [["nome", "name"], ["email", "email"], ["email_confirmado", "email_verified"], ["situacao", "segment"], ["nivel", "level"],
        ["trilha", "target_level"], ["cadastro", "created_at"], ["teste_ate", "trial_ends_at"], ["pago_ate", "paid_until"], ["treinos", "attempts"],
        ["primeiro_treino", "first_at"], ["ultimo_treino", "last_at"], ["min_audio", "azure_min"], ["nota_media", "avg_score"], ["quer_assinar", "wants_subscription_at"],
        ["origem", "signup_source"], ["campanha", "signup_campaign"], ["post", "signup_content"]];
      const cell = (v) => {
        let s = v == null ? "" : String(v);
        if (/^[=+\-@]/.test(s)) s = "'" + s;
        return '"' + s.replace(/"/g, '""') + '"';
      };
      const lines = [cols.map((c) => c[0]).join(",")].concat(r.items.map((l) => cols.map((c) => cell(l[c[1]])).join(",")));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
      a.download = "leads-meuingles-" + new Date().toISOString().slice(0, 10) + ".csv";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1500);
    } catch (e) { if (e.message !== "401") toast(e.message); }
  }
  /* ---------- painel do administrador: custos do mês ---------- */
  async function loadCosts() {
    const box = $("#admCosts");
    if (!box) return;
    try {
      const c = await api("admin/costs");
      const brl = (v) => "R$ " + Number(v || 0).toFixed(2).replace(".", ",");
      const usd = (v) => "US$ " + Number(v || 0).toFixed(2);
      const cell = (n, l, note) => '<div class="stat"><strong>' + aEsc(n) + "</strong><span>" + aEsc(l) + (note ? '<em class="delta">' + aEsc(note) + "</em>" : "") + "</span></div>";
      const tbl = (head, body) => '<div class="tbl-wrap"><table class="table"><thead><tr>' + head.map((x) => "<th>" + x + "</th>").join("") + "</tr></thead><tbody>" + body + "</tbody></table></div>";
      const T = c.totals, P = c.paying, K = c.caps, R = c.rates;
      const segName = (s) => aEsc(SEG_BADGE[s] || s);
      let h = '<div class="block"><span class="label">Custos do mês (' + aEsc(c.month) + ')</span><div class="stats stats-admin">' +
        cell(brl(T.total_brl), "custo total", usd(T.total_usd)) + cell(brl(T.azure_brl), "áudio avaliado (Azure)", (T.azure_h * 60).toFixed(1).replace(".", ",") + " min") +
        cell(brl(T.llm_brl), "correções com IA", T.llm_calls + " chamadas") +
        cell(brl(T.avg_brl), "custo por usuário ativo", T.active_users + " ativos") +
        cell(brl(c.unconverted_brl), "gasto com quem ainda não assinou") +
        cell(P.margin_pct == null ? "–" : P.margin_pct + "%", "margem dos assinantes", brl(P.margin_brl) + " no mês") + "</div>" +
        '<span class="label">Teto de custo por conta</span><div class="stats stats-admin">' +
        cell(brl(K.paying_brl), "assinante com a franquia cheia", K.paying_pct_net == null ? "" : K.paying_pct_net + "% da receita líquida") +
        cell(brl(K.trial_brl), "teste com a franquia cheia") + cell(brl(P.net_per_user_brl), "receita líquida por assinante") + "</div>" +
        '<span class="label">Custo por situação da conta</span>' + tbl(["Situação", "Contas", "Áudio", "IA", "Total"],
          c.segments.map((s) => "<tr><td>" + segName(s.seg) + "</td><td>" + s.users + "</td><td>" + brl(s.azure_brl) + "</td><td>" + brl(s.llm_brl) + "</td><td>" + brl(s.total_brl) + "</td></tr>").join("")) +
        '<span class="label">Quem mais custa no mês</span>' + tbl(["Nome", "Situação", "Min", "IA", "Custo"],
          c.top.map((t) => "<tr><td>" + aEsc(t.name) + "</td><td>" + segName(t.seg) + "</td><td>" + String(t.azure_min).replace(".", ",") + "</td><td>" + t.llm_calls + "</td><td>" + brl(t.brl) + "</td></tr>").join("")) +
        '<p class="adm-sub">Premissas: Azure US$ ' + R.azure_h + "/h · IA US$ " + R.llm_in + " e US$ " + R.llm_out + " por milhão de tokens (entrada e saída) · dólar R$ " + String(R.usd_brl).replace(".", ",") +
        " · taxa de pagamento " + R.fee_pct + "% · valores antes de imposto. Tokens medidos em " + (T.measured_pct == null ? "–" : T.measured_pct + "%") + " das correções; as demais usam uma média estimada.</p></div>";
      box.innerHTML = h;
    } catch (e) { box.innerHTML = ""; }
  }
  /* ---------- painel do administrador: visitas ao site ---------- */
  const trf = { days: 7 };
  const fmtDur = (s) => { s = Math.round(Number(s) || 0); return s < 60 ? s + "s" : (Math.floor(s / 60) + "min " + (s % 60 ? (s % 60) + "s" : "")).trim(); };
  const SRC_LABEL = { linkedin: "LinkedIn", direto: "Direto / sem origem", google: "Google", x: "X (Twitter)", meta: "Facebook / Instagram",
    whatsapp: "WhatsApp", facebook: "Facebook", instagram: "Instagram" };
  async function loadTraffic() {
    const box = $("#admTraffic");
    if (!box) return;
    try {
      const t = await api("admin/traffic?days=" + trf.days);
      const S = Number(t.sessions) || 0;
      const cell = (n, l, note) => '<div class="stat"><strong>' + aEsc(n) + "</strong><span>" + aEsc(l) + (note ? '<em class="delta">' + aEsc(note) + "</em>" : "") + "</span></div>";
      const rows = (arr, cols) => arr.map((r) => "<tr>" + cols.map((c) => "<td>" + c(r) + "</td>").join("") + "</tr>").join("");
      const wrap = (head, body) => '<div class="tbl-wrap"><table class="table"><thead><tr>' + head.map((x) => "<th>" + x + "</th>").join("") + "</tr></thead><tbody>" + body + "</tbody></table></div>";
      const lbl = (k) => aEsc(SRC_LABEL[k] || k || "–");
      let h = '<div class="block"><div class="adm-row"><span class="label">Visitas ao site</span><select id="trfDays" class="mini-sel">' +
        [7, 30, 90].map((d) => '<option value="' + d + '"' + (d === trf.days ? " selected" : "") + ">Últimos " + d + " dias</option>").join("") + "</select></div>";
      if (!S) {
        h += '<p class="muted">Ainda sem visitas registradas neste período. Use o gerador de links abaixo nas suas publicações.</p>';
      } else {
        h += '<div class="stats stats-admin">' +
          cell(t.visitors, "visitantes únicos", t.new_visitors + " novos") + cell(S, "sessões") + cell(t.pageviews, "páginas vistas") +
          cell(fmtDur(t.avg_dur), "tempo médio por visita") + cell(fmtDur(t.med_dur), "tempo mediano") + cell(aPct(t.bounces, S), "saíram em menos de 10s") +
          cell(aPct(t.cta, S), "clicaram em entrar") + cell(t.signups, "cadastros (todas as origens)") + cell(t.online, "online agora") + "</div>";
        const funnel = [["Sessões", S], ["Clicaram em entrar", t.cta], ["Abriram o app", t.app_open], ["Cadastros com origem rastreada", t.signups_tracked]].map((p) =>
          '<div class="fun"><div class="fun-l"><span>' + p[0] + "</span><b>" + p[1] + " · " + aPct(p[1], S) + '</b></div><div class="fun-bar"><i style="width:' +
          Math.min(100, Math.max(2, Math.round((p[1] / S) * 100))) + '%"></i></div></div>').join("");
        h += '<span class="label">Do clique ao cadastro</span><div class="fun-wrap">' + funnel + "</div>";
        const mx = Math.max(1, ...t.by_day.map((d) => Number(d.sessions)));
        h += '<span class="label">Sessões por dia</span><div class="spark">' + t.by_day.map((d) => '<i title="' + aDate(d.day + "T12:00:00") + ": " + d.sessions + ' sessões" style="height:' +
          Math.max(3, Math.round((Number(d.sessions) / mx) * 100)) + '%"></i>').join("") + "</div>";
        h += '<span class="label">De onde vêm</span>' + wrap(["Origem", "Visitas", "Tempo", "Saíram", "Entrar"],
          rows(t.by_source, [(r) => lbl(r.k), (r) => r.sessions, (r) => fmtDur(r.avg_dur), (r) => r.bounce_pct + "%", (r) => aPct(r.cta, r.sessions)]));
        if (t.by_campaign.length) h += '<span class="label">Por campanha e post</span>' + wrap(["Campanha", "Post", "Visitas", "Tempo", "Entrar", "App"],
          rows(t.by_campaign, [(r) => aEsc(r.campaign), (r) => aEsc(r.content || "–"), (r) => r.sessions, (r) => fmtDur(r.avg_dur), (r) => aPct(r.cta, r.sessions), (r) => aPct(r.app_open, r.sessions)]));
        h += '<span class="label">Cadastros e assinaturas por origem</span>' + wrap(["Origem", "Cadastros", "Confirmaram", "Treinaram", "Assinaram"],
          rows(t.su_source, [(r) => lbl(r.k), (r) => r.n, (r) => aPct(r.verified, r.n), (r) => aPct(r.practiced, r.n), (r) => r.paid]));
        if (t.su_campaign.length) h += '<span class="label">Cadastros por campanha e post</span>' + wrap(["Campanha", "Post", "Cadastros", "Treinaram", "Assinaram"],
          rows(t.su_campaign, [(r) => aEsc(r.campaign), (r) => aEsc(r.content || "–"), (r) => r.n, (r) => aPct(r.practiced, r.n), (r) => r.paid]));
        const hh = Array.from({ length: 24 }, (_, k) => Number((t.by_hour.find((x) => x.h === k) || {}).n || 0));
        const hm = Math.max(1, ...hh);
        h += '<span class="label">Horários com mais visitas (Brasília)</span><div class="spark">' + hh.map((n, k) => '<i title="' + k + "h: " + n + ' visitas" style="height:' + Math.max(3, Math.round((n / hm) * 100)) + '%"></i>').join("") + "</div>" +
          '<p class="adm-sub">0h à esquerda, 23h à direita. Toque numa barra para ver o valor.</p>';
        h += '<span class="label">Páginas</span>' + wrap(["Página", "Vistas", "Tempo", "Rolagem"], rows(t.pages, [(r) => aEsc(r.path), (r) => r.views, (r) => fmtDur(r.avg_dur), (r) => r.scroll + "%"]));
        h += '<p class="adm-sub">Aparelhos: ' + t.by_device.map((d) => aEsc(d.k) + " " + aPct(d.n, S)).join(" · ") + "</p>";
      }
      h += '<span class="label">Gerador de link rastreado</span><div class="adm-ctl"><input id="gCmp" placeholder="Campanha (ex.: lancamento)" maxlength="40">' +
        '<input id="gPost" placeholder="Post ou versão (ex.: post1)" maxlength="40"><input id="gOut" readonly></div>' +
        '<button type="button" class="btn ghost" id="gCopy">Copiar link</button>' +
        '<p class="adm-sub">Use um link diferente em cada publicação do LinkedIn para saber qual traz mais gente.</p></div>';
      box.innerHTML = h;
      $("#trfDays").addEventListener("change", (e) => { trf.days = Number(e.target.value); loadTraffic(); });
      const slug = (v) => v.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const gen = () => {
        const c = slug($("#gCmp").value) || "campanha", p = slug($("#gPost").value);
        $("#gOut").value = location.origin + "/?utm_source=linkedin&utm_medium=post&utm_campaign=" + c + (p ? "&utm_content=" + p : "");
      };
      $("#gCmp").addEventListener("input", gen); $("#gPost").addEventListener("input", gen); gen();
      $("#gCopy").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText($("#gOut").value); toast("Link copiado."); }
        catch (e) { $("#gOut").select(); toast("Selecione e copie o link."); }
      });
    } catch (e) { box.innerHTML = ""; }
  }
  async function loadAdmin() {
    const box = $("#adminBox");
    try { localStorage.setItem("mi_notrack", "1"); } catch (e) {}
    try {
      const [s, i] = await Promise.all([api("admin/stats"), api("admin/insights").catch(() => null)]);
      const cell = (n, l, note) => '<div class="stat"><strong>' + aEsc(n) + "</strong><span>" + aEsc(l) + (note ? '<em class="delta">' + aEsc(note) + "</em>" : "") + "</span></div>";
      let h = '<div class="block"><div class="row"><span class="label">Painel do administrador</span></div><div class="stats stats-admin">' +
        cell(s.signups, "cadastros") + cell(s.verified, "e-mails confirmados") + cell(s.trial_active, "em teste") +
        cell(s.trial_ended, "teste vencido") + cell(s.want_to_pay, "querem assinar") + cell(s.paying, "assinantes") +
        cell(s.active_users_7d, "ativos em 7 dias") + cell(s.azure_min_month, "min de Azure no mês") + cell(s.llm_calls_7d, "correções IA em 7 dias") + "</div></div>";
      if (i) {
        const money = "R$ " + Number(i.mrr || 0).toFixed(2).replace(".", ",");
        const funnel = [["Cadastros", i.signups], ["E-mail confirmado", i.verified], ["Fizeram 1 treino", i.practiced],
          ["Engajados (5+ treinos)", i.engaged], ["Já assinaram", i.paid_ever]].map((p) =>
          '<div class="fun"><div class="fun-l"><span>' + p[0] + "</span><b>" + p[1] + " · " + aPct(p[1], i.signups) + '</b></div><div class="fun-bar"><i style="width:' +
          (Number(i.signups) ? Math.max(2, Math.round((p[1] / i.signups) * 100)) : 0) + '%"></i></div></div>').join("");
        const mx = Math.max(1, ...i.signups_by_day.map((d) => Number(d.n)));
        const spark = i.signups_by_day.map((d) => '<i title="' + aDate(d.day + "T12:00:00") + ": " + d.n + '" style="height:' +
          Math.max(3, Math.round((Number(d.n) / mx) * 100)) + '%"></i>').join("");
        const att = [["trial_expiring", i.trial_expiring, "testes acabam em até 2 dias"], ["trial_inactive", i.trial_inactive, "em teste sem treinar há 3+ dias"],
          ["near_quota", i.near_quota, "perto do limite de minutos do teste"], ["expired_engaged", i.expired_engaged, "vencidos que treinaram 3+ vezes e não assinaram"],
          ["want_to_pay", i.want_to_pay, "pediram aviso da assinatura"], ["unverified", i.unverified, "não confirmaram o e-mail"]].map((a) =>
          '<button type="button" class="chip-att" data-seg="' + a[0] + '"><b>' + a[1] + "</b> " + a[2] + "</button>").join("");
        const tracks = i.by_track.map((t) => "<tr><td>" + aEsc(TRACK_LABEL[t.k] || t.k) + "</td><td>" + t.n + "</td><td>" + t.paid + "</td><td>" + aPct(t.paid, t.n) + "</td></tr>").join("");
        const levels = i.by_level.map((l) => "nível " + l.k + ": " + l.n).join(" · ");
        h += '<div class="block"><span class="label">Estatísticas comerciais</span><div class="stats stats-admin">' +
          cell(money, "receita mensal (assinantes ativos)") + cell(aPct(i.paid_ever, i.signups), "cadastro → assinatura") + cell(aPct(i.paid_ever, i.trial_decided), "conversão após o teste") +
          cell(aPct(i.activated_24h, i.signups), "treinam nas primeiras 24h") + cell(i.hours_to_first == null ? "–" : i.hours_to_first + " h", "até o 1º treino (média)") +
          cell(i.days_to_pay == null ? "–" : i.days_to_pay + " d", "até assinar (média)") +
          cell(i.signups_7d, "cadastros em 7 dias", aDelta(i.signups_7d, i.signups_prev_7d)) + cell(i.active_7d, "ativos em 7 dias", aDelta(i.active_7d, i.active_prev_7d)) +
          cell(i.paying_now, "assinantes agora") + "</div>" +
          '<span class="label">Funil</span><div class="fun-wrap">' + funnel + "</div>" +
          '<span class="label">Cadastros nos últimos 30 dias</span><div class="spark">' + spark + "</div>" +
          '<span class="label">Quem abordar hoje</span><div class="chips-att">' + att + "</div>" +
          '<span class="label">Conversão por trilha</span><table class="table"><thead><tr><th>Trilha</th><th>Leads</th><th>Pagaram</th><th>Conv.</th></tr></thead><tbody>' + tracks + "</tbody></table>" +
          '<p class="adm-sub">Leads por nível: ' + levels + "</p></div>";
      }
      h += '<div id="admCosts"></div>';
      h += '<div id="admTraffic"></div>';
      h += '<div class="block"><span class="label">Leads</span><div class="adm-ctl"><select id="admSeg"></select>' +
        '<select id="admOrder"><option value="created_at:desc">Mais recentes</option><option value="last_at:desc">Última atividade</option>' +
        '<option value="attempts:desc">Mais treinos</option><option value="trial_ends_at:asc">Teste acaba primeiro</option></select>' +
        '<input id="admQ" type="search" placeholder="Buscar nome ou e-mail" maxlength="80"></div>' +
        '<div class="adm-row"><span class="muted" id="admTotal"></span><button type="button" class="linkbtn" id="admCsv">Exportar CSV</button></div>' +
        '<div id="admList"></div><button type="button" class="btn ghost" id="admMore" hidden>Carregar mais</button></div>';
      box.innerHTML = h;
      fillSegSelect(null);
      $("#admOrder").value = adm.order + ":" + (adm.desc ? "desc" : "asc");
      $("#admQ").value = adm.q;
      $("#admSeg").addEventListener("change", (e) => { adm.seg = e.target.value; loadLeads(true); });
      $("#admOrder").addEventListener("change", (e) => { const p = e.target.value.split(":"); adm.order = p[0]; adm.desc = p[1] === "desc"; loadLeads(true); });
      let tmr = null;
      $("#admQ").addEventListener("input", (e) => { clearTimeout(tmr); tmr = setTimeout(() => { adm.q = e.target.value.trim(); loadLeads(true); }, 350); });
      $("#admMore").addEventListener("click", () => { adm.offset += adm.limit; loadLeads(false); });
      $("#admCsv").addEventListener("click", exportLeads);
      box.querySelectorAll(".chip-att").forEach((b) => b.addEventListener("click", () => {
        adm.seg = b.dataset.seg; loadLeads(true);
        $("#admSeg").scrollIntoView({ behavior: "smooth", block: "center" });
      }));
      loadLeads(true); loadTraffic(); loadCosts();
    } catch (e) { box.innerHTML = ""; }
  }
  $("#deleteBtn").addEventListener("click", () => { $("#deleteForm").hidden = false; $("#deletePass").focus(); });
  $("#deleteCancel").addEventListener("click", () => { $("#deleteForm").hidden = true; $("#deletePass").value = ""; });
  $("#deleteForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("me/delete", { method: "POST", body: JSON.stringify({ password: $("#deletePass").value }) });
      clearAuth(); state.auth = null; $("#deleteForm").hidden = true;
      $("#tabs").hidden = true; $("#levelPill").hidden = true; $("#logoutBtn").hidden = true;
      show("login"); setAuthMode("signup", "Sua conta e seus dados foram excluídos.");
    } catch (ex) { $("#deleteError").textContent = ex.message; $("#deleteError").hidden = false; }
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
      renderAccount(h.account);
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
    state.level = lv; state.adhoc = null; state.queue = null; practiceView(true);
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
    $("#pCounter").textContent = state.queue ? (state.qIdx + 1) + "/" + state.queue.length : state.adhoc || !list ? "" : (state.index[state.level] + 1) + "/" + list.length;
    const open = it.kind === "explain" || it.kind === "star";
    $("#recNote").textContent = open ? "Toque para começar e toque de novo quando terminar" : "Toque para gravar";
    $("#listenBtn").lastChild.textContent = open ? "Ouvir a pergunta" : "Ouvir pronúncia";
    $("#liveText").textContent = "";
    $("#result").innerHTML = "";
  }
  function step(d) {
    if (state.queue) {
      state.qIdx = (state.qIdx + d + state.queue.length) % state.queue.length;
      state.adhoc = state.queue[state.qIdx];
      renderItem();
      return;
    }
    const list = state.items[state.level];
    if (!list) return;
    if (!state.adhoc) state.index[state.level] = (state.index[state.level] + d + list.length) % list.length;
    state.adhoc = null;
    renderItem();
  }
  $("#prevBtn").addEventListener("click", () => step(-1));
  $("#nextBtn").addEventListener("click", () => step(1));
  function practiceAdhoc(item) {
    state.adhoc = item; state.queue = null; practiceView(true);
    $$("#levelChips [data-lv]").forEach((c) => c.setAttribute("aria-pressed", "false"));
    show("practice");
  }

  /* ---------- treino por som ---------- */
  function practiceView(on) {
    $(".prompt").hidden = !on; $(".recorder").hidden = !on; $("#result").hidden = !on;
    $("#soundsPanel").hidden = on;
    $("#soundChip").setAttribute("aria-pressed", String(!on && !$("#soundsPanel").hidden));
  }
  async function openSounds() {
    if (rec.active || (typeof aud !== "undefined" && aud.active)) return;
    $$("#levelChips [data-lv]").forEach((c) => c.setAttribute("aria-pressed", "false"));
    practiceView(false);
    $("#soundChip").setAttribute("aria-pressed", "true");
    const box = $("#soundsPanel");
    box.innerHTML = '<p class="empty">Calculando seus sons mais fracos…</p>';
    let r;
    try { r = await api("sounds"); } catch (e) { if (e.message !== "401") box.innerHTML = '<div class="notice">' + esc(e.message) + "</div>"; return; }
    if (!r.sounds.length) {
      box.innerHTML = '<div class="block"><span class="label">Treino por som</span><p class="muted">' + (r.has_data
        ? "Todos os seus sons estão com média 80 ou mais. Continue nos níveis para manter o ritmo."
        : "Ainda não há dados suficientes. Faça treinos nos níveis 1 e 2: cada som precisa aparecer pelo menos 3 vezes nas avaliações do Azure.") + "</p></div>";
      return;
    }
    box.innerHTML = '<p class="muted">Seus sons com a menor média nas avaliações do Azure. Escolha um para treinar.</p>' +
      r.sounds.map((s, i) => '<div class="block sound"><div class="row"><span class="sound-p">/' + esc(s.p) + '/</span>' +
        '<span class="label">média ' + s.avg + " · " + s.n + " vezes</span></div>" +
        '<div class="bar"><i style="width:' + Math.max(4, s.avg) + "%;background:" + color(s.avg) + '"></i></div>' +
        (s.tip ? '<p class="muted">' + esc(s.tip) + "</p>" : "") +
        '<button class="btn" data-sound="' + i + '">Treinar /' + esc(s.p) + "/ · " + s.items.length + " exercícios</button></div>").join("");
    box.querySelectorAll("[data-sound]").forEach((b) => b.addEventListener("click", () => {
      const snd = r.sounds[+b.dataset.sound];
      state.queue = snd.items; state.qIdx = 0; state.adhoc = snd.items[0];
      practiceView(true);
      $("#soundChip").setAttribute("aria-pressed", "true");
      renderItem();
      window.scrollTo(0, 0);
    }));
  }
  $("#soundChip").addEventListener("click", openSounds);

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
      const loop = (now) => { if (!rec.active && !aud.active) { drawWave(0, false); return; } drawWave(now - rec.started, true); if (!reduce) requestAnimationFrame(loop); };
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

  /* ---------- gravação em áudio para o Azure (níveis 1 e 2) ---------- */
  const aud = { active: false, stream: null, ctx: null, src: null, node: null, chunks: [], rate: 48000, started: 0, speech: false, lastLoud: 0 };

  function useAzure(it) { return state.azure && !state.forceBrowser && it && (it.kind === "word" || it.kind === "sentence"); }

  async function startAudio() {
    const it = currentItem();
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !AC) { startRec(); return; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    try {
      aud.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      $("#result").innerHTML = '<div class="notice">Permita o uso do microfone para este site nas configurações do navegador.</div>';
      return;
    }
    aud.ctx = new AC(); aud.rate = aud.ctx.sampleRate;
    aud.src = aud.ctx.createMediaStreamSource(aud.stream);
    aud.node = aud.ctx.createScriptProcessor(4096, 1, 1);
    aud.chunks = []; aud.speech = false; aud.started = performance.now(); aud.lastLoud = aud.started;
    aud.node.onaudioprocess = (e) => {
      if (!aud.active) return;
      const d = e.inputBuffer.getChannelData(0);
      aud.chunks.push(new Float32Array(d));
      let sum = 0; for (let i = 0; i < d.length; i += 4) sum += d[i] * d[i];
      const rms = Math.sqrt(sum / (d.length / 4)), now = performance.now();
      if (rms > 0.02) { aud.speech = true; aud.lastLoud = now; }
      if ((aud.speech && now - aud.lastLoud > 1400) || now - aud.started > 25000) stopAudio();
    };
    aud.src.connect(aud.node); aud.node.connect(aud.ctx.destination);
    aud.active = true; rec.started = aud.started;
    setRecUI(true);
    $("#recNote").textContent = "Gravando… fale agora (para sozinho quando você terminar)";
    $("#liveText").textContent = "";
    $("#result").innerHTML = "";
  }

  function stopAudio() { if (aud.active) { aud.active = false; finishAudio(); } }

  function encodeWav(chunks, rate) {
    let len = 0; chunks.forEach((c) => (len += c.length));
    const all = new Float32Array(len); let o = 0; chunks.forEach((c) => { all.set(c, o); o += c.length; });
    const ratio = rate / 16000, outLen = Math.floor(all.length / ratio), pcm = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const a = Math.floor(i * ratio), b = Math.min(all.length, Math.floor((i + 1) * ratio));
      let sum = 0; for (let j = a; j < b; j++) sum += all[j];
      const v = Math.max(-1, Math.min(1, sum / Math.max(1, b - a)));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    const buf = new ArrayBuffer(44 + pcm.length * 2), dv = new DataView(buf);
    const str = (off, t) => { for (let i = 0; i < t.length; i++) dv.setUint8(off + i, t.charCodeAt(i)); };
    str(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
    dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, 16000, true);
    dv.setUint32(28, 32000, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); str(36, "data");
    dv.setUint32(40, pcm.length * 2, true);
    new Int16Array(buf, 44).set(pcm);
    return buf;
  }

  async function finishAudio() {
    setRecUI(false);
    try { aud.node.disconnect(); aud.src.disconnect(); aud.stream.getTracks().forEach((t) => t.stop()); aud.ctx.close(); } catch (e) {}
    const it = currentItem();
    const duration = Math.round(performance.now() - aud.started);
    $("#recNote").textContent = "Toque para gravar";
    if (!aud.speech) { $("#result").innerHTML = '<div class="notice">Não ouvi nada. Fale um pouco mais alto e perto do microfone.</div>'; return; }
    const wav = encodeWav(aud.chunks, aud.rate); aud.chunks = [];
    $("#recNote").textContent = "Avaliando a pronúncia…";
    $("#recBtn").disabled = true;
    try {
      const res = await fetch("api/attempts/audio?item_id=" + encodeURIComponent(it.id) + "&duration_ms=" + duration, {
        method: "POST", body: wav,
        headers: { "Content-Type": "audio/wav", Authorization: "Bearer " + state.auth.token },
      });
      let r = null; try { r = await res.json(); } catch (e) {}
      if (res.status === 401) { logout("Sua sessão expirou. Entre novamente."); return; }
      if (!res.ok && res.status < 500) {
        $("#result").innerHTML = '<div class="notice">' + esc((r && r.detail) || "Erro " + res.status) + "</div>";
        return;
      }
      if (!res.ok) {
        $("#result").innerHTML = '<div class="notice">' + esc((r && r.detail) || "Erro " + res.status) +
          '<br><button class="btn ghost small" id="useBrowser" style="margin-top:8px">Usar o reconhecimento do navegador</button></div>';
        $("#useBrowser").addEventListener("click", () => { state.forceBrowser = true; $("#result").innerHTML = ""; toast("Modo navegador ativado até você recarregar a página."); });
        return;
      }
      state.homeDirty = state.progressDirty = true;
      $("#liveText").textContent = r.transcript || "";
      renderResult(r, it);
      if (r.level_up) { setPill(r.level_up); toast("Você subiu para o nível " + r.level_up + " · " + r.level_up_name); }
    } catch (e) {
      $("#result").innerHTML = '<div class="notice">Sem conexão com o servidor. Tente de novo.</div>';
    } finally {
      $("#recBtn").disabled = false;
      $("#recNote").textContent = "Toque para gravar";
    }
  }

  $("#recBtn").addEventListener("click", () => {
    if (rec.active) return stopRec();
    if (aud.active) return stopAudio();
    return useAzure(currentItem()) ? startAudio() : startRec();
  });

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
  function azureBlock(r) {
    const s = r.scores;
    const worst = r.words.filter((w) => w.status !== "extra").sort((a, b) => (a.score ?? 0) - (b.score ?? 0))[0];
    return '<div class="block"><div class="row"><span class="label">Resultado · Azure, som por som</span></div>' +
      '<div class="scores scores4">' + ring(s.pron, "Pronúncia") + ring(s.accuracy, "Precisão") + ring(s.fluency, "Fluência") + ring(s.completeness, "Completude") + "</div>" +
      '<div class="words">' + r.words.map((w, i) => '<button class="w ' + w.status + '" data-ph="' + i + '" aria-label="Ver os sons de ' + esc(w.display) + '">' + esc(w.display) + "</button>").join("") + "</div>" +
      '<p class="heard">Toque numa palavra para ver a nota de cada som.</p>' +
      '<div class="phon" id="phonBox">' + (worst ? phonemeHtml(worst) : "") + "</div>" +
      '<p class="heard">O Azure entendeu: <b>“' + esc(r.transcript) + '”</b></p></div>';
  }
  function phonemeHtml(w) {
    if (w.status === "missing") return '<p class="heard"><b>' + esc(w.display) + "</b>: palavra não falada.</p>";
    if (!w.phonemes || !w.phonemes.length) return '<p class="heard"><b>' + esc(w.display) + "</b>: nota " + (w.score ?? "–") + ".</p>";
    return '<div class="phon-title"><b>' + esc(w.display) + '</b> <span class="ipa">/' + esc(w.phonemes.map((p) => p.p).join("")) + "/</span></div>" +
      w.phonemes.map((p) => '<div class="phon-row"><span class="ph">/' + esc(p.p) + '/</span><div class="bar"><i style="width:' + Math.max(4, p.score ?? 0) + "%;background:" + color(p.score ?? 0) + '"></i></div><span class="n">' + (p.score ?? "–") + "</span></div>").join("");
  }
  function llmBlock(l) {
    let h = '<div class="block"><div class="row"><span class="label">Correção · Claude</span><span class="label">gramática ' + l.score + "</span></div>";
    if (l.errors.length) h += '<ul class="fixes">' + l.errors.map((e) => '<li><span class="wrong">' + esc(e.wrong) + '</span> → <span class="right">' + esc(e.right) + "</span>" + (e.why ? '<br><span class="why">' + esc(e.why) + "</span>" : "") + "</li>").join("") + "</ul>";
    else h += '<p class="heard">Nenhum erro de gramática importante.</p>';
    if (l.natural) h += '<div class="natural"><span class="label">Versão mais natural</span><p>' + esc(l.natural) + '</p><button class="btn ghost small listen" id="sayNatural"><svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1l7 4-7 4z"/></svg>Ouvir</button></div>';
    return h + "</div>";
  }
  function renderResult(r, it) {
    const s = r.scores;
    let html = "";
    if (r.level_up) html += '<div class="block levelup"><span class="label">Novo nível</span><h3>Nível ' + r.level_up + " · " + esc(r.level_up_name) + "</h3><p class=\"muted\">Cinco tentativas seguidas com 80 ou mais. O nível novo já aparece nos chips acima.</p></div>";
    if (r.engine === "azure") {
      html += azureBlock(r);
    } else if (it.kind === "word" || it.kind === "sentence") {
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
    if (r.llm) html += llmBlock(r.llm);
    if (r.tips.length) html += '<div class="block"><div class="row"><span class="label">Onde melhorar</span></div><ul class="tips">' +
      r.tips.map((t) => "<li>" + (t.word ? '<span class="tw">' + esc(t.word) + "</span>" + (t.ipa ? '<span class="tipa">' + esc(t.ipa) + "</span>" : "") + "<br>" : "") + esc(t.text) + "</li>").join("") + "</ul></div>";
    if (r.drills.length) html += '<div class="block"><div class="row"><span class="label">Treine agora</span></div><ul class="drills">' +
      r.drills.map((d, i) => "<li><span>" + esc(d.text) + '</span><span class="acts"><button class="play" data-say="' + i + '" aria-label="Ouvir"><svg viewBox="0 0 10 10"><path d="M2 1l7 4-7 4z"/></svg></button><button class="btn ghost small" data-drill="' + i + '">Treinar</button></span></li>').join("") + "</ul></div>";
    const box = $("#result");
    box.innerHTML = html;
    box.querySelectorAll("[data-ph]").forEach((b) => b.addEventListener("click", () => { $("#phonBox").innerHTML = phonemeHtml(r.words[+b.dataset.ph]); }));
    if (r.llm && $("#sayNatural")) $("#sayNatural").addEventListener("click", () => say(r.llm.natural));
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
  async function loadHealth() {
    try { const h = await (await fetch("api/health")).json(); state.azure = !!h.azure_configured; state.llm = !!h.llm_configured; } catch (e) {}
  }
  function start() {
    loadHealth();
    $("#tabs").hidden = false; $("#logoutBtn").hidden = false;
    state.homeDirty = state.progressDirty = true;
    show("home");
  }
  const params = new URLSearchParams(location.search);
  if (params.has("verified") || params.has("reset") || params.has("m") || params.has("assinatura")) history.replaceState(null, "", location.pathname);
  try { localStorage.removeItem("meuingles.auth"); } catch (e) {}
  state.auth = loadAuth();
  if (params.get("reset")) {
    resetToken = params.get("reset"); show("login"); setAuthMode("reset");
  } else if (state.auth && state.auth.token) {
    start();
    if (params.get("verified") === "1") toast("E-mail confirmado! Bom treino.");
    if (params.get("verified") === "0") toast("Esse link de confirmação venceu. Peça um novo no aviso da tela inicial.");
    if (params.has("assinatura")) syncBilling(true);
  } else {
    show("login");
    setAuthMode(params.has("verified") || params.get("m") === "login" ? "login" : "signup",
      params.get("verified") === "1" ? "E-mail confirmado! Entre para começar." : params.get("verified") === "0" ? "Link vencido. Entre e peça um novo." : "");
  }
})();
