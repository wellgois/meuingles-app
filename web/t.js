(function () {
  try {
    var ls = window.localStorage, ss = window.sessionStorage;
    var q = new URLSearchParams(location.search);
    if (q.get("notrack") === "1") ls.setItem("mi_notrack", "1");
    if (q.get("notrack") === "0") ls.removeItem("mi_notrack");
    if (ls.getItem("mi_notrack") === "1" || navigator.doNotTrack === "1") return;
    if (/bot|crawl|spider|preview|headless|slurp|facebookexternalhit/i.test(navigator.userAgent)) return;

    function uid() {
      if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
      return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 3) | 8).toString(16);
      });
    }

    var vid = ls.getItem("mi_vid"), isNew = false;
    if (!vid) { vid = uid(); ls.setItem("mi_vid", vid); isNew = true; }

    var now = Date.now(), sess = null;
    try { sess = JSON.parse(ss.getItem("mi_s") || "null"); } catch (e) {}
    var utmNow = (q.get("utm_source") || "").toLowerCase();
    if (!sess || now - sess.t > 1800000 || (utmNow && utmNow !== sess.us)) {
      var ref = "";
      try {
        var rh = document.referrer ? new URL(document.referrer).hostname.replace(/^www\./, "") : "";
        if (rh && rh !== location.hostname.replace(/^www\./, "")) ref = rh;
      } catch (e) {}
      sess = { id: uid(), t: now, ref: ref, us: utmNow, um: q.get("utm_medium") || "", uc: q.get("utm_campaign") || "", ut: q.get("utm_content") || "" };
    }
    var ua = navigator.userAgent, inapp = /LinkedInApp/i.test(ua) ? "linkedin" : /FBAN|FBAV/i.test(ua) ? "facebook" : /Instagram/i.test(ua) ? "instagram" : "";

    try {
      var at = null; try { at = JSON.parse(ls.getItem("mi_attr") || "null"); } catch (e) {}
      var expired = !at || now - at.t > 2592000000;
      if (sess.us || (expired && (sess.ref || inapp))) {
        ls.setItem("mi_attr", JSON.stringify({ t: now, us: sess.us, uc: sess.uc, ut: sess.ut, ref: sess.ref, ia: inapp }));
      }
    } catch (e) {}
    window.miAttr = function () {
      var a = null; try { a = JSON.parse(ls.getItem("mi_attr") || "null"); } catch (e) {}
      a = a || {};
      return { vid: vid, utm_source: a.us || "", utm_campaign: a.uc || "", utm_content: a.ut || "", ref: a.ref || "", inapp: a.ia || "" };
    };
    var pv = uid();
    var path = location.pathname.replace(/index\.html$/, "") || "/";
    var active = 0, last = document.hidden ? null : Date.now(), scroll = 0, cta = 0;

    function tick() { if (last) { var n = Date.now(); active += n - last; last = n; } }
    function send() {
      tick();
      sess.t = Date.now();
      try { ss.setItem("mi_s", JSON.stringify(sess)); } catch (e) {}
      var body = JSON.stringify({ pv: pv, vid: vid, sid: sess.id, path: path, ref: sess.ref, us: sess.us, um: sess.um, uc: sess.uc, ut: sess.ut,
        ia: inapp, w: window.innerWidth, nw: isNew ? 1 : 0, dur: Math.round(active / 1000), sc: scroll, cta: cta });
      if (navigator.sendBeacon) navigator.sendBeacon("/api/t", new Blob([body], { type: "application/json" }));
      else fetch("/api/t", { method: "POST", body: body, headers: { "Content-Type": "application/json" }, keepalive: true });
    }

    window.addEventListener("scroll", function () {
      var h = document.documentElement;
      var p = Math.round((100 * (window.scrollY + window.innerHeight)) / Math.max(h.scrollHeight, 1));
      if (p > scroll) scroll = Math.min(p, 100);
    }, { passive: true });
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a");
      if (!a) return;
      if (/(^|\/)app\/?($|[?#])/.test(a.getAttribute("href") || "")) { cta = 1; send(); }
    }, true);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { send(); last = null; } else { last = Date.now(); }
    });
    window.addEventListener("pagehide", send);
    setInterval(function () { if (!document.hidden) send(); }, 20000);
    send();
  } catch (e) {}
})();
