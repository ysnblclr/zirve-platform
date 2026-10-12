"use strict";
/* Zirve Platformu arayüzü. Derleme adımı yoktur.
   Hedef: WCAG 2.2 AA. Bildirimler sayfa açılışından beri var olan canlı bölgelere yazılır,
   onaylar <dialog> ile sorulur, sayfa değişince odak başlığa taşınır. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const main = $("#icerik");

const SUB_NAMES = {
  teknik: "Teknik model", momentum: "Momentum", trend: "Trend", buyume: "Büyüme", kalite: "Kalite",
  degerleme: "Değerleme", sahiplik: "Kurum ve analist", grup: "Endüstri gücü", fon_akisi: "Fon akışı",
  tema: "Tema", likidite: "Likidite", maliyet: "Maliyet",
};
const ICON = {
  ok: '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  sira: '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false"><path d="M6 2l4 6H2z" fill="currentColor"/></svg>',
};

// ------------------------------------------------------------------ sunucu
async function api(path, opts = {}) {
  const r = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    let msg = `Sunucu ${r.status} döndürdü.`;
    try { msg = (await r.json()).detail || msg; } catch { /* metin yanıt */ }
    throw new Error(msg);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}
const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b || {}) });
const put = (p, b) => api(p, { method: "PUT", body: JSON.stringify(b || {}) });
const del = p => api(p, { method: "DELETE" });

// ------------------------------------------------------------------ biçimlendirme
const BOS = '<span class="bos"><span aria-hidden="true">-</span><span class="sr-only">veri yok</span></span>';
const nf = (v, d = 0) => v == null || isNaN(v) ? BOS : Number(v).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const signed = (v, d) => `${v > 0 ? "+" : v < 0 ? "−" : ""}%${Number(Math.abs(v)).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const pct = (v, d = 0) => v == null ? BOS : `<span class="${v > 0 ? "olumlu" : v < 0 ? "olumsuz" : ""}">${signed(v, d)}</span>`;
const ret = (r, d = 1) => r == null ? BOS : pct(r * 100, d);
const prob = p => p == null ? BOS : "%" + Number(p * 100).toLocaleString("tr-TR", { maximumFractionDigits: 0 });
const money = v => v == null ? BOS : v >= 1e12 ? nf(v / 1e12, 2) + " Tn $" : v >= 1e9 ? nf(v / 1e9, 1) + " Mr $" : v >= 1e6 ? nf(v / 1e6, 0) + " M $" : nf(v);
const vol = v => v == null ? BOS : v >= 1e6 ? nf(v / 1e6, 1) + " M" : nf(v / 1e3) + " bin";
const when = s => s ? `<time datetime="${esc(s.replace(" ", "T"))}">${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)} ${s.slice(11, 16)}</time>` : BOS;
const day = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "";
const tick = t => `<a href="#/hisse/${encodeURIComponent(t)}">${esc(t)}</a>`;
const riskBadge = (r, p) => {
  if (!r || r === "Bilinmiyor") return BOS;
  const cls = r === "Yüksek" ? "rozet--olumsuz" : r === "Düşük" ? "rozet--olumlu" : "";
  return `<span class="rozet ${cls}">${esc(r)}</span>${p != null ? `<span class="sr-only">, 12 ayda yüzde 30 düşüş olasılığı ${Math.round(p * 100)}</span>` : ""}`;
};
const TAG_WARN = /Spekülatif|Döngüsel|Kaldıraçlı|Tavanlı|Emtia/;
const tagBadges = arr => (arr || []).length ? `<span class="rozetler">${arr.map(t => `<span class="rozet ${TAG_WARN.test(t) ? "rozet--uyari" : ""}">${esc(t)}</span>`).join("")}</span>` : "";
const score = s => `<span class="puan"><span class="cubuk" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, s))}%"></i></span>${nf(s, 1)}</span>`;
const scopeName = m => m === "genis" ? "geniş kapsam" : "zirve kapsamı";

// ------------------------------------------------------------------ duyuru, bildirim, onay
function announce(msg) {
  const el = $("#canli");
  el.textContent = "";
  setTimeout(() => { el.textContent = msg; }, 80);
}

function notify(msg, { hata = false, eylem = null, sure = 7000 } = {}) {
  const box = $("#bildirimler");
  const el = document.createElement("div");
  el.className = "bildirim" + (hata ? " bildirim--hata" : "");
  const text = document.createElement("span");
  text.className = "metin";
  text.textContent = msg;
  el.append(text);
  const close = () => el.remove();
  if (eylem) {
    const b = document.createElement("button");
    b.className = "dugme dugme--kucuk";
    b.type = "button";
    b.textContent = eylem.etiket;
    b.onclick = async () => { close(); await eylem.fn(); };
    el.append(b);
  }
  const x = document.createElement("button");
  x.className = "dugme dugme--kucuk";
  x.type = "button";
  x.textContent = "Kapat";
  x.onclick = close;
  el.append(x);
  box.append(el);
  // Fare üstündeyken ya da odaktayken kaybolmaz (WCAG 2.2.1)
  let t = setTimeout(close, sure);
  const pause = () => clearTimeout(t);
  const resume = () => { clearTimeout(t); t = setTimeout(close, sure); };
  el.addEventListener("mouseenter", pause);
  el.addEventListener("mouseleave", resume);
  el.addEventListener("focusin", pause);
  el.addEventListener("focusout", resume);
}

function confirmAction({ baslik, metin, tamam }) {
  const d = $("#onay");
  const opener = document.activeElement;
  $("#onay-baslik").textContent = baslik;
  $("#onay-metin").textContent = metin;
  $("#onay-tamam").textContent = tamam;
  d.returnValue = "";
  return new Promise(resolve => {
    d.addEventListener("close", () => {
      resolve(d.returnValue === "tamam");
      if (opener && document.contains(opener)) opener.focus();
    }, { once: true });
    d.showModal();
    $("#onay-iptal").focus();   // geri alınamaz işlemde güvenli seçenek önce
  });
}

// ------------------------------------------------------------------ yönlendirme
const ROUTES = [
  [/^#?\/?$/, pagePanel, "panel"],
  [/^#\/taramalar$/, pageScans, "taramalar"],
  [/^#\/tarama\/(\w+)$/, pageScan, "taramalar"],
  [/^#\/hisse\/([A-Za-z0-9.\-]+)$/, pageTicker, null],
  [/^#\/izleme$/, pageWatch, "izleme"],
  [/^#\/performans$/, pagePerf, "performans"],
  [/^#\/analiz$/, pageAnalysis, "analiz"],
  [/^#\/ayarlar$/, pageSettings, "ayarlar"],
  [/^#\/uyarilar$/, pageAlerts, "uyarilar"],
  [/^#\/yardim$/, pageHelp, "yardim"],
];

function render(html) {
  main.innerHTML = `<div class="kap">${html}</div>`;
  setTimeout(scrollRegions, 0);
}

// Yatay kaydırılan tablolar klavyeyle de kaydırılabilsin: odaklanabilir, adlandırılmış bölge yapılır
function scrollRegions() {
  $$(".tablo-kap", main).forEach(el => {
    const scrolls = el.scrollWidth > el.clientWidth + 1;
    if (scrolls && !el.hasAttribute("tabindex")) {
      el.tabIndex = 0;
      el.dataset.oto = "1";
      if (!el.hasAttribute("role")) el.setAttribute("role", "region");
      if (!el.hasAttribute("aria-label") && !el.hasAttribute("aria-labelledby")) {
        const heading = el.closest("section")?.querySelector("h2, h3")?.textContent.trim();
        const cap = $("caption", el)?.textContent.trim() || (heading ? `${heading} tablosu` : "Tablo");
        el.setAttribute("aria-label", cap);
      }
    } else if (!scrolls && el.dataset.oto) {
      el.removeAttribute("tabindex");
      el.removeAttribute("role");
      delete el.dataset.oto;
    }
  });
}
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(scrollRegions, 200); });

async function route({ focus = true } = {}) {
  const h = location.hash || "#/";
  for (const [re, fn, nav] of ROUTES) {
    const m = h.match(re);
    if (!m) continue;
    $$("[data-r]").forEach(a => {
      if (a.dataset.r === nav) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (focus) render('<p class="ikincil">Yükleniyor</p>');
    let title;
    try {
      title = await fn(...m.slice(1).map(decodeURIComponent));
    } catch (e) {
      title = "Hata";
      render(`<h1>Sayfa açılamadı</h1><div class="kutu kutu--hata ust-bosluk"><p>${esc(e.message)}</p>
        <p>Platformun açık olduğundan emin olup sayfayı yenileyin. Sorun sürerse <a href="#/yardim">Yardım</a> sayfasındaki sorun giderme adımlarına bakın.</p></div>`);
    }
    document.title = `${title || "Zirve Platformu"} | Zirve Platformu`;
    if (focus) {
      window.scrollTo(0, 0);
      const h1 = $("h1", main);
      if (h1) { h1.tabIndex = -1; h1.focus({ preventScroll: true }); }
    }
    return;
  }
  render('<h1>Sayfa bulunamadı</h1><p class="ust-bosluk"><a href="#/">Panele dönün</a>.</p>');
  document.title = "Sayfa bulunamadı | Zirve Platformu";
}
window.addEventListener("hashchange", () => route());

$("#ara").addEventListener("submit", e => {
  e.preventDefault();
  const q = $("#q").value.trim().toUpperCase();
  if (!q) { $("#q").focus(); return; }
  location.hash = "#/hisse/" + encodeURIComponent(q);
  $("#q").value = "";
});
// Kısayol: "/" arama kutusuna gider (yazı yazılan alanlarda çalışmaz)
document.addEventListener("keydown", e => {
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t.closest("input, textarea, select, [contenteditable]")) return;
  e.preventDefault();
  $("#q").focus();
});

// ------------------------------------------------------------------ iş (tarama/analiz) takibi
let lastJob = null;
const liveJobs = new Set();
let lastStep = -1;

function jobPanel(j) {
  if (!j) return "";
  const done = j.durum !== "calisiyor";
  const pctDone = Math.round((j.durum === "tamam" ? 1 : j.oran) * 100);
  const state = j.durum === "tamam" ? "tamamlandı" : j.durum === "hata" ? "başarısız oldu" : "sürüyor";
  const link = j.durum === "tamam" && j.sonuc && j.sonuc.tarama_id ? ` <a href="#/tarama/${j.sonuc.tarama_id}">Sonuçları açın</a>.` : "";
  return `<section class="bolum alt-bosluk" aria-labelledby="is-baslik">
    <h2 id="is-baslik">${esc(j.baslik)} ${state}</h2>
    <p class="ikincil kucuk">Başlangıç ${when(j.baslangic)}${j.bitis ? `, bitiş ${when(j.bitis)}` : ""}.${link}</p>
    <label class="sr-only" for="is-pb">İlerleme</label>
    <progress id="is-pb" max="100" value="${pctDone}" style="width:100%">${pctDone}%</progress>
    <p>${esc(j.durum === "hata" ? "Hata: " + j.hata : j.mesaj)}</p>
    <details ${done ? "" : "open"}><summary>İşlem günlüğü</summary><div class="gunluk" tabindex="0">${esc((j.log || []).slice(-80).join("\n"))}</div></details>
  </section>`;
}

async function poll() {
  let running = false;
  try {
    const s = await api("/durum");
    const n = s.okunmamis_uyari;
    const badge = $("#uyari-sayi");
    badge.hidden = !n;
    badge.innerHTML = n ? `${n}<span class="sr-only"> okunmamış</span>` : "";
    const j = s.is;
    running = !!(j && j.durum === "calisiyor");
    const bar = $("#is-durumu");
    bar.hidden = !running;
    if (running) {
      liveJobs.add(j.id);
      $("#is-metin").textContent = `${j.baslik} sürüyor: ${j.mesaj}`;
      $("#is-ilerleme").value = Math.round(j.oran * 100);
      $("#is-bag").href = j.tur === "analiz" ? "#/analiz" : "#/taramalar";
      // Sık duyuru yapmamak için yalnızca yarıda bir kez haber verilir
      const step = j.oran >= 0.5 ? 1 : 0;
      if (lastJob?.id === j.id && step > lastStep) announce(`${j.baslik} yarıya geldi.`);
      lastStep = lastJob?.id === j.id ? Math.max(lastStep, step) : step;
    }
    const panel = $("[data-is-paneli]", main);
    if (panel && j && liveJobs.has(j.id) && panel.dataset.isPaneli === j.tur) panel.innerHTML = jobPanel(j);
    if (lastJob && j && lastJob.id === j.id && lastJob.durum === "calisiyor" && !running) {
      if (j.durum === "tamam") {
        const id = j.sonuc && j.sonuc.tarama_id;
        notify(`${j.baslik} tamamlandı.`, id ? { eylem: { etiket: "Sonuçları aç", fn: () => { location.hash = `#/tarama/${id}`; } } } : {});
        const h = location.hash || "#/";
        if ((j.tur === "tarama" && /^#?\/?$|^#\/taramalar$/.test(h)) || (j.tur === "analiz" && h === "#/analiz")) route({ focus: false });
      } else {
        notify(`${j.baslik} başarısız oldu: ${j.hata}`, { hata: true, sure: 15000 });
      }
    }
    if (!lastJob && running) announce(`${j.baslik} sürüyor.`);
    lastJob = j;
  } catch { /* sunucu kapalıysa sessizce yeniden dener */ }
  setTimeout(poll, running ? 1500 : 6000);
}

async function startScan(opts) {
  try {
    await post("/tarama", opts);
    announce("Tarama başladı. Yaklaşık 2 dakika sürer; ilerleme sayfanın üstünde görünür.");
    poll();
    return true;
  } catch (e) {
    notify(e.message, { hata: true });
    return false;
  }
}

// ------------------------------------------------------------------ sekmeler (ARIA tabs)
function tabs(root) {
  const list = $('[role="tablist"]', root);
  const tabsEls = $$('[role="tab"]', list);
  const select = (t, focus) => {
    tabsEls.forEach(x => {
      const on = x === t;
      x.setAttribute("aria-selected", on);
      x.tabIndex = on ? 0 : -1;
      $("#" + x.getAttribute("aria-controls")).hidden = !on;
    });
    if (focus) t.focus();
  };
  list.addEventListener("click", e => { const t = e.target.closest('[role="tab"]'); if (t) select(t, false); });
  list.addEventListener("keydown", e => {
    const i = tabsEls.indexOf(document.activeElement);
    if (i < 0) return;
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabsEls.length - 1 }[e.key];
    if (next == null) return;
    e.preventDefault();
    select(tabsEls[(next + tabsEls.length) % tabsEls.length], true);
  });
  select(tabsEls[0], false);
}

// ------------------------------------------------------------------ sonuç tablosu
const STOCK_COLS = [
  { h: "Sıra", v: it => it.sira, f: it => it.sira },
  { h: "Puan", v: it => it.puan, f: it => score(it.puan), sort: true },
  { h: "Zirve Durumu", v: it => it.is_true_ath ? 1 : 0, f: it => it.is_true_ath
    ? '<span class="rozet rozet--ath" title="Tarihsel zirve (Dirençsiz mavi gökyüzü)">Gerçek ATH</span>'
    : `<span class="rozet rozet--uyari" title="Tarihsel Zirve: ${nf(it.ath_fiyat, 2)} $ (${it.ath_tarih || ''})">52H Zirve</span> <span class="ikincil kucuk">(-%${nf(it.ath_uzaklik_yuzde, 1)})</span>`, sort: true },
  { h: "Arketip", l: 1, v: it => it.arketip || "", f: it => it.arketip ? `<span class="rozet rozet--arketip">${esc(it.arketip)}</span>` : BOS, sort: true },
  { h: "+%50 olasılığı", v: it => it.p_up, f: it => prob(it.p_up), sort: true },
  { h: "Risk", v: it => it.p_down, f: it => riskBadge(it.risk, it.p_down), sort: true },
  { h: "Şirket", l: 1, v: it => it.sirket, f: it => esc((it.sirket || "").slice(0, 26)) },
  { h: "Profil", l: 1, v: it => (it.etiketler || []).join(), f: it => tagBadges(it.etiketler) },
  { h: "Endüstri", l: 1, v: it => it.endustri, f: it => esc(it.endustri), sort: true },
  { h: "Fiyat ($)", v: it => it.veri["Fiyat"], f: it => nf(it.veri["Fiyat"], 2) },
  { h: "6 ay", v: it => it.veri["6 Ay"], f: it => pct(it.veri["6 Ay"]), sort: true },
  { h: "1 yıl", v: it => it.veri["1 Yıl"], f: it => pct(it.veri["1 Yıl"]), sort: true },
  { h: "Satış büyümesi", v: it => it.veri["Satış Ç/Ç"], f: it => pct(it.veri["Satış Ç/Ç"]), sort: true },
  { h: "Gelecek yıl kâr", v: it => it.veri["EPS Gelecek Yıl"], f: it => pct(it.veri["EPS Gelecek Yıl"]), sort: true },
  { h: "İleri F/K", v: it => it.veri["İleri F/K"], f: it => nf(it.veri["İleri F/K"], 1), sort: true },
  { h: "Hacim artışı", v: it => it.veri["Hacim Artışı (x)"], f: it => it.veri["Hacim Artışı (x)"] == null ? BOS : nf(it.veri["Hacim Artışı (x)"], 1) + " kat", sort: true },
  { h: "Açığa Satış", v: it => it.veri["Açığa Satış"], f: it => it.veri["Açığa Satış"] == null ? BOS : "%" + nf(it.veri["Açığa Satış"], 1), sort: true },
  { h: "Bilanço", v: it => it.bilanco, f: it => it.bilanco ? day(it.bilanco) : BOS, sort: true },
];
const ETF_COLS = [
  { h: "Sıra", v: it => it.sira, f: it => it.sira },
  { h: "Puan", v: it => it.puan, f: it => score(it.puan), sort: true },
  { h: "Zirve Durumu", v: it => it.is_true_ath ? 1 : 0, f: it => it.is_true_ath
    ? '<span class="rozet rozet--ath" title="Tüm zamanların zirvesi">Gerçek ATH</span>'
    : `<span class="rozet rozet--uyari">52H Zirve</span> <span class="ikincil kucuk">(-%${nf(it.ath_uzaklik_yuzde, 1)})</span>`, sort: true },
  { h: "Risk", v: it => it.p_down, f: it => riskBadge(it.risk, it.p_down), sort: true },
  { h: "Fon", l: 1, v: it => it.sirket, f: it => esc((it.sirket || "").slice(0, 34)) },
  { h: "Profil", l: 1, v: it => (it.etiketler || []).join(), f: it => tagBadges(it.etiketler) },
  { h: "Kategori", l: 1, v: it => it.sektor, f: it => esc(it.sektor), sort: true },
  { h: "Varlık", v: it => it.veri["Varlık (AUM)"], f: it => money(it.veri["Varlık (AUM)"]), sort: true },
  { h: "3 ay", v: it => it.veri["3 Ay"], f: it => pct(it.veri["3 Ay"]), sort: true },
  { h: "1 yıl", v: it => it.veri["1 Yıl"], f: it => pct(it.veri["1 Yıl"]), sort: true },
  { h: "Fon girişi (1 ay)", v: it => it.veri["Akış 1A %"], f: it => pct(it.veri["Akış 1A %"], 1), sort: true },
  { h: "Gider oranı", v: it => it.veri["Gider %"], f: it => it.veri["Gider %"] == null ? BOS : "%" + nf(it.veri["Gider %"], 2), sort: true },
];

const ARCHETYPES = [
  { v: "", l: "Tüm Tipler" },
  { v: "Yapay Zeka ve Yazılım", l: "Yapay Zeka" },
  { v: "Short Squeeze", l: "Short Squeeze" },
  { v: "Mavi Gökyüzü Kırılımı", l: "Mavi Gökyüzü" },
  { v: "Döngüsel ve Emtia", l: "Döngüsel" },
  { v: "Biyoteknoloji", l: "Biyotek" },
];

let tableSeq = 0;
function resultsTable(el, items, kind, captionText) {
  const id = "t" + (++tableSeq);
  const cols = kind === "ETF" ? ETF_COLS : STOCK_COLS;
  let sortI = null, dir = -1, q = "", tag = "", risk = "", arketip = "", athOnly = false;
  const tags = [...new Set(items.flatMap(i => i.etiketler || []))].sort((a, b) => a.localeCompare(b, "tr"));
  const head = cols.map((c, i) => c.sort
    ? `<th scope="col" class="${c.l ? "sol" : ""}" data-i="${i}"><button type="button" class="siralama">${c.h}${ICON.sira}</button></th>`
    : `<th scope="col" class="${c.l ? "sol" : ""}">${c.h}</th>`).join("");
  el.innerHTML = `
    <div class="suzgecler">
      <div class="alan"><label class="etiket" for="${id}-q">Ara</label>
        <input type="search" id="${id}-q" class="genislik-orta" placeholder="Sembol, şirket ya da endüstri"></div>
      <div class="secenek" style="align-self:center;padding-top:1.2rem">
        <input type="checkbox" id="${id}-ath">
        <label for="${id}-ath"><strong>Sadece Gerçek ATH</strong></label>
        <p class="ipucu" id="${id}-ath-ip">52 haftalık zirvede olup tarihi zirvesini geçememiş olanları gizler.</p>
      </div>
      ${kind === "Hisse" ? `
      <fieldset><legend>Fırsat Arketipi</legend>
        <div class="bolumlu">${ARCHETYPES.map((a, i) => `<input type="radio" name="${id}-arketip" id="${id}-a${i}" value="${a.v}" ${i ? "" : "checked"}><label for="${id}-a${i}">${a.l}</label>`).join("")}</div>
      </fieldset>` : ""}
      <fieldset><legend>Risk</legend>
        <div class="bolumlu">${["Tümü", "Düşük", "Orta", "Yüksek"].map((r, i) => `<input type="radio" name="${id}-risk" id="${id}-r${i}" value="${i ? r : ""}" ${i ? "" : "checked"}><label for="${id}-r${i}">${r}</label>`).join("")}</div>
      </fieldset>
      ${tags.length ? `<div class="alan"><label class="etiket" for="${id}-tag">Profil</label>
        <select id="${id}-tag"><option value="">Tüm profiller</option>${tags.map(t => `<option>${esc(t)}</option>`).join("")}</select></div>` : ""}
      <p class="ikincil" id="${id}-n"></p>
    </div>
    <div class="tablo-kap" role="region" aria-labelledby="${id}-cap" tabindex="0">
      <table class="tablo"><caption id="${id}-cap">${esc(captionText)}. Ayrıntı için satırdaki oku kullanın.</caption>
        <thead><tr><td></td><th scope="col" class="sol">Sembol</th>${head}</tr></thead><tbody></tbody></table>
    </div>`;
  const body = $("tbody", el);
  let timer;
  const sayCount = n => { clearTimeout(timer); timer = setTimeout(() => announce(`${n} sonuç gösteriliyor.`), 700); };
  $(`#${id}-q`).addEventListener("input", e => { q = e.target.value.toLowerCase(); draw(true); });
  $(`#${id}-ath`).addEventListener("change", e => { athOnly = e.target.checked; draw(true); });
  $$(`[name="${id}-risk"]`, el).forEach(r => r.addEventListener("change", e => { risk = e.target.value; draw(true); }));
  if (kind === "Hisse") {
    $$(`[name="${id}-arketip"]`, el).forEach(r => r.addEventListener("change", e => { arketip = e.target.value; draw(true); }));
  }
  if (tags.length) $(`#${id}-tag`).addEventListener("change", e => { tag = e.target.value; draw(true); });
  $("thead", el).addEventListener("click", e => {
    const th = e.target.closest("th[data-i]");
    if (!th) return;
    const i = +th.dataset.i;
    dir = sortI === i ? -dir : -1;
    sortI = i;
    $$("th[data-i]", el).forEach(x => x.removeAttribute("aria-sort"));
    th.setAttribute("aria-sort", dir === -1 ? "descending" : "ascending");
    draw(false);
    announce(`${cols[i].h} sütununa göre ${dir === -1 ? "büyükten küçüğe" : "küçükten büyüğe"} sıralandı.`);
  });
  function draw(fromFilter) {
    let rows = items.filter(it =>
      (!athOnly || it.is_true_ath)
      && (!q || `${it.sembol} ${it.sirket} ${it.endustri} ${it.sektor} ${it.arketip || ""}`.toLowerCase().includes(q))
      && (!tag || (it.etiketler || []).includes(tag))
      && (!risk || it.risk === risk)
      && (!arketip || it.arketip === arketip));
    if (sortI != null) {
      const c = cols[sortI];
      rows = [...rows].sort((a, b) => { const x = c.v(a), y = c.v(b); if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
    }
    $(`#${id}-n`).textContent = `${rows.length} / ${items.length} sonuç`;
    if (fromFilter) sayCount(rows.length);
    body.innerHTML = rows.map(it => {
      const rid = `${id}-${it.sembol.replace(/[^A-Za-z0-9]/g, "_")}`;
      return `<tr data-s="${esc(it.sembol)}">
        <td><button type="button" class="ac-kapa" aria-expanded="false" aria-controls="${rid}">${ICON.ok}<span class="sr-only">${esc(it.sembol)} ayrıntıları</span></button></td>
        <th scope="row" class="sol">${tick(it.sembol)}${it.izleniyor ? ' <span class="rozet">İzleniyor</span>' : ""}</th>
        ${cols.map(c => `<td class="${c.l ? "sol" : ""}">${c.f(it)}</td>`).join("")}</tr>`;
    }).join("") || `<tr><td colspan="${cols.length + 2}" class="sol ikincil">Süzgeçlere uyan sonuç yok.</td></tr>`;
  }
  const toggle = tr => {
    const btn = $(".ac-kapa", tr);
    const open = btn.getAttribute("aria-expanded") === "true";
    if (open) { $("#" + btn.getAttribute("aria-controls"))?.remove(); btn.setAttribute("aria-expanded", "false"); return; }
    const it = items.find(x => x.sembol === tr.dataset.s);
    const d = document.createElement("tr");
    d.className = "ayrinti";
    d.id = btn.getAttribute("aria-controls");
    d.innerHTML = `<td colspan="${cols.length + 2}">${detailHtml(it)}<p class="ust-bosluk"><a href="#/hisse/${encodeURIComponent(it.sembol)}">${esc(it.sembol)} sayfasını açın</a></p></td>`;
    tr.after(d);
    btn.setAttribute("aria-expanded", "true");
    scrollRegions();
  };
  body.addEventListener("click", e => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-s]");
    if (tr) toggle(tr);
  });
  draw(false);
}

function subBars(it) {
  const w = it.agirlik || {};
  return `<ul class="cubuklar">${Object.entries(it.alt_puan || {}).map(([k, v]) => {
    const wt = w[k] ?? 0;
    return `<li><span>${esc(SUB_NAMES[k] || k)} <span class="ikincil">(${nf(wt)})</span></span>
      <span class="iz" aria-hidden="true"><i style="width:${Math.round(v * 100)}%"></i></span><span class="deger">${nf(v * wt, 1)}</span></li>`;
  }).join("")}</ul>`;
}

function facts(it) {
  return `<dl class="ozet">${Object.entries(it.veri || {}).map(([k, v]) => {
    let s;
    if (v == null) s = BOS;
    else if (/Değer|AUM/.test(k)) s = money(v);
    else if (k === "Ort. Hacim") s = vol(v);
    else s = nf(v, Math.abs(v) < 10 ? 2 : 0);
    return `<div><dt>${esc(k)}</dt><dd class="kucuk">${s}</dd></div>`;
  }).join("")}</dl>`;
}

function newsList(news, empty = "Haber yok.") {
  if (!news || !news.length) return `<p class="ikincil">${empty}</p>`;
  return `<ul class="haberler">${news.map(n => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}<span class="sr-only"> (yeni sekmede açılır)</span></a>
    <span class="kaynak">${esc(n.source)}${n.date ? ", " + esc(n.date === "Today" ? "bugün" : n.date) : ""}</span></li>`).join("")}</ul>`;
}

function reasonsHtml(it, level = 3) {
  const h = `h${level}`;
  return `<${h}>Neden yükselebilir?</${h}>
    ${it.nedenler.length ? `<ul class="liste">${it.nedenler.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : '<p class="ikincil">Belirgin olumlu sinyal yok.</p>'}
    <${h} class="ust-bosluk">Riskler</${h}>
    ${it.riskler.length ? `<ul class="liste">${it.riskler.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : '<p class="ikincil">Belirgin risk işareti yok.</p>'}`;
}

function tradingPlanHtml(plan) {
  if (!plan || !plan.stop_loss) return "";
  const inv = plan.invalidation ? `<p class="not ust-bosluk" style="color:var(--olumsuz)"><strong>Senaryo İptali:</strong> ${esc(plan.invalidation)}</p>` : "";
  const poz = plan.pozisyon_onerisi ? `<p class="not" style="color:var(--metin-ikincil)"><strong>Pozisyon Önerisi:</strong> ${esc(plan.pozisyon_onerisi)}</p>` : "";
  return `<div class="plan-kartlari ust-bosluk">
    <div class="plan-kart"><dt>Önerilen Alım Aralığı</dt><dd class="kucuk">${esc(plan.alim_araligi)}</dd></div>
    <div class="plan-kart plan-kart--stop"><dt>Dinamik Stop-Loss</dt><dd>${nf(plan.stop_loss, 2)} $ <span class="kucuk">(-%${nf(plan.stop_loss_pct, 1)})</span></dd></div>
    <div class="plan-kart plan-kart--hedef"><dt>Hedef 1 (Kısa Vade)</dt><dd>${nf(plan.hedef_1, 2)} $ <span class="kucuk">(+%${nf(plan.hedef_1_pct, 0)})</span></dd></div>
    <div class="plan-kart plan-kart--hedef"><dt>Hedef 2 (1Y Multi-Bagger)</dt><dd>${nf(plan.hedef_2, 2)} $ <span class="kucuk">(+%${nf(plan.hedef_2_pct, 0)})</span></dd></div>
    ${plan.hedef_3 ? `<div class="plan-kart plan-kart--hedef"><dt>Hedef 3 (Moonshot Runner)</dt><dd>${nf(plan.hedef_3, 2)} $ <span class="kucuk">(+%${nf(plan.hedef_3_pct, 0)})</span></dd></div>` : ""}
    <div class="plan-kart"><dt>Risk / Ödül (R:R)</dt><dd>${esc(plan.risk_odul)}</dd></div>
  </div>${inv}${poz}`;
}

function opportunityReportHtml(it) {
  if (!it) return "";
  let rep = it.firsat_raporu;
  if (!rep) {
    const isAth = it.is_true_ath;
    const v = it.veri || {};
    const p = v["Fiyat"] || it.fiyat || 0;
    const athP = it.ath_fiyat || v["ATH Fiyat"] || p;
    const dist = it.ath_uzaklik_yuzde || v["ATH Uzaklık %"] || 0;
    const ark = it.arketip || "Zirve Kırılımı";
    const short = v["Açığa Satış"];
    const shortRatio = v["Short Ratio"];
    const sQQ = v["Satış Ç/Ç"];
    const eQQ = v["EPS Ç/Ç"];
    const eNY = v["EPS Gelecek Yıl"];
    const fpe = v["İleri F/K"];
    const pe = v["F/K"];

    rep = {
      baslik: `${it.sembol} - %120+ 1 Yıllık Multi-Bagger Fırsat Tezi (${ark})`,
      ozet: `${it.sirket || it.sembol}, ${ark} arketipinde konumlanmıştır. ` +
        (isAth
          ? `Tüm zamanların en yüksek seviyesinde (${nf(p, 2)} $) dirençsiz mavi gökyüzü kırılımı gerçekleştirmiştir. Satış baskısı sıfırlandığı için kurumsal alımlar doğrudan fiyat genişlemesine dönüşmektedir.`
          : `Son 52 haftanın en yükseğine çıkarak uzun vadeli taban dönüşü gerçekleştirmiştir. Tarihsel zirvesine (${nf(athP, 2)} $) -%${nf(dist, 1)} mesafededir.`),
      zirve_dinamigi: isAth
        ? `Tüm Zamanların Zirvesi (Mavi Gökyüzü): Hisse ${nf(p, 2)} $ seviyesinde tarihin en yüksek fiyatındadır. Üzerinde zararda bekleyen hiçbir maliyetli yatırımcı yoktur; dirençsiz serbest fiyat keşfi modundadır.`
        : `52 Haftalık Zirve (Taban Kırılımı): Hissenin tarihsel rekor tepe noktası ${nf(athP, 2)} $ olup hisse bu tepeye -%${nf(dist, 1)} mesafededir. Uzun süreli dip konsolidasyonunun tamamlandığını gösterir.`,
      smart_money: `Kurumsal ve Açığa Satış Dinamiği: Hissedeki açığa satış payı %${nf(short, 1)}, kapanma süresi ${nf(shortRatio, 1)} gündür. ` +
        (short >= 8 ? `Zirve kırılımında açıkçıların panik kapatma alımları short squeeze dalgası tetikleyebilir.` : `Yükseliş gerçek kurumsal taleple desteklenmektedir.`),
      temel_buyume: `Temel Büyüme ve Kâr Patlaması: Satış büyümesi %${nf(sQQ, 1)}, EPS büyümesi %${nf(eQQ, 1)}, gelecek yıl kâr beklentisi %${nf(eNY, 1)}. F/K: ${nf(pe, 1)}, İleri F/K: ${nf(fpe, 1)}. Çarpan genişlemesi potansiyeli taşımaktadır.`,
      sektorel_ruzgar: `Sektörel ve Makro Katalizör: ${it.sektor || ''} sektörü ve ${it.endustri || ''} endüstrisinde güçlü kurumsal fon akışı ve pazar liderliği ile pozitif ayrışmaktadır.`,
      taktik_eylem: `Taktik Eylem: İdeal alım aralığı ${it.plan?.alim_araligi || 'aktif bölge'}. Stop-loss ${nf(it.plan?.stop_loss, 2)} $ (-%${nf(it.plan?.stop_loss_pct, 1)}). Hedef 1 ${nf(it.plan?.hedef_1, 2)} $ (+%35), Hedef 2 ${nf(it.plan?.hedef_2, 2)} $ (+%120). Risk/Ödül: ${it.plan?.risk_odul || '1:12'}.`,
    };
  }

  return `<section class="firsat-karti" aria-labelledby="h-firsat-${it.sembol}">
    <h3 id="h-firsat-${it.sembol}">${esc(rep.baslik)}</h3>
    <p class="ozet-metin">${esc(rep.ozet)}</p>
    <div class="firsat-grid">
      <div class="firsat-sutun">
        <span class="firsat-sutun-baslik">Zirve ve Fiyat Dinamiği</span>
        <p>${esc(rep.zirve_dinamigi)}</p>
      </div>
      <div class="firsat-sutun">
        <span class="firsat-sutun-baslik">Smart Money ve Açığa Satış</span>
        <p>${esc(rep.smart_money)}</p>
      </div>
      <div class="firsat-sutun">
        <span class="firsat-sutun-baslik">Büyüme ve Kâr Patlaması</span>
        <p>${esc(rep.temel_buyume)}</p>
      </div>
      <div class="firsat-sutun">
        <span class="firsat-sutun-baslik">Sektörel Süper Döngü</span>
        <p>${esc(rep.sektorel_ruzgar)}</p>
      </div>
    </div>
    <div class="ust-bosluk">
      <span class="firsat-sutun-baslik">Taktik Eylem ve Pozisyon Stratejisi</span>
      <p class="ikincil ust-bosluk">${esc(rep.taktik_eylem)}</p>
    </div>
  </section>`;
}

function categorizedFactsHtml(it) {
  const v = it.veri || {};
  const groups = [
    {
      title: "Değerleme Çarpanları",
      keys: ["Piyasa Değeri", "Fiyat", "F/K", "İleri F/K", "PEG", "F/S", "P/B", "P/FCF", "Analist Öneri", "Hedef Potansiyel", "Hedef Fiyat", "Temettü %"]
    },
    {
      title: "Büyüme ve Kârlılık",
      keys: ["Satış Ç/Ç", "EPS Ç/Ç", "EPS Gelecek Yıl", "EPS Bu Yıl", "Brüt Marj %", "Faaliyet Marj %", "Kâr Marj %", "ROE %", "ROA %", "ROI %"]
    },
    {
      title: "Kurumsal Sahiplik ve Short",
      keys: ["Açığa Satış", "Short Ratio", "Kurum Alımı", "Kurumsal Pay %", "İçeriden Pay %", "İçeriden Alım %", "Borç/Özsermaye", "Cari Oran"]
    },
    {
      title: "Momentum ve Teknik Seviyeler",
      keys: ["1 Ay", "3 Ay", "6 Ay", "1 Yıl", "ATH Fiyat", "ATH Uzaklık %", "52H Yüksek", "52H Düşük", "RSI", "SMA20", "SMA50", "SMA200", "ATR", "Hacim Artışı (x)", "Ort. Hacim"]
    }
  ];

  const formatVal = (k, val) => {
    if (val == null) return BOS;
    if (/Değer|AUM/.test(k)) return money(val);
    if (k === "Ort. Hacim") return vol(val);
    if (/^(1 Ay|3 Ay|6 Ay|1 Yıl)$/.test(k)) return pct(val);
    if (/%|Marj|Satış Ç\/Ç|EPS|Kurum Alımı|Hedef Potansiyel|Temettü/.test(k)) return pct(val, 1);
    return nf(val, Math.abs(val) < 10 ? 2 : 0);
  };

  return `<div class="metrik-kategorileri">
    ${groups.map(g => {
      const items = g.keys.filter(k => v[k] !== undefined && v[k] !== null);
      if (!items.length) return "";
      return `<div class="metrik-kutu">
        <h4>${esc(g.title)}</h4>
        <dl class="ozet">
          ${items.map(k => `<div><dt>${esc(k)}</dt><dd class="kucuk">${formatVal(k, v[k])}</dd></div>`).join("")}
        </dl>
      </div>`;
    }).join("")}
  </div>`;
}

function detailHtml(it, level = 2) {
  const p = it.p_up == null ? "" : `<p class="alt-bosluk">Geçmişte benzer teknik profildeki hisselerin <strong>${prob(it.p_up)}</strong> kadarı 12 ayda yüzde 50'den fazla yükseldi, <strong>${prob(it.p_down)}</strong> kadarı yüzde 30'dan fazla düştü. <span class="ikincil">Bu oranlar iyimserdir; sıralama için kullanın.</span></p>`;
  const athBox = `<div class="kutu ${it.is_true_ath ? 'kutu--basari' : 'kutu--uyari'} alt-bosluk">
    <strong>${it.is_true_ath ? 'Tüm Zamanların Zirvesi (Gerçek ATH)' : '52 Haftalık Zirve (Tarihsel Zirve Değil)'}</strong>:
    ${it.is_true_ath
      ? `Hisse tarihin en yüksek fiyatında (${nf(it.veri?.["Fiyat"] ?? it.fiyat, 2)} $). Üstte zararda bekleyen maliyetli hissedar yok; dirençsiz mavi gökyüzü kırılımı.`
      : `Tarihsel zirve <strong>${nf(it.ath_fiyat, 2)} $</strong> (${it.ath_tarih || 'geçmiş'}), güncel fiyat bu zirvenin <strong>-%${nf(it.ath_uzaklik_yuzde, 1)}</strong> altında. Eski tepelerden kalan maliyetli yatırımcıların satış direnci oluşabilir.`}
  </div>`;
  const firsatHtml = it.tur === "Hisse" ? opportunityReportHtml(it) : "";
  const planBlock = it.plan && it.plan.stop_loss ? `<h${level} class="ust-bosluk">Eylem Planı ve Seviyeler</h${level}>${tradingPlanHtml(it.plan)}` : "";
  const factsBlock = it.tur === "Hisse" ? categorizedFactsHtml(it) : facts(it);
  return `${p}${athBox}${firsatHtml}<div class="duzen-esit">
    <div>${reasonsHtml(it, level)}</div>
    <div><h${level}>Puan bileşenleri</h${level}>${subBars(it)}</div>
    <div><h${level}>Haberler (tarama anı)</h${level}>${newsList(it.haberler, "Bu tarama için haber çekilmedi.")}</div>
  </div>${planBlock}<h${level} class="ust-bosluk">Kapsamlı Finansal ve Teknik Metrikler</h${level}>${factsBlock}`;
}


// ------------------------------------------------------------------ grafikler
function niceTicks(lo, hi, n) {
  const raw = (hi - lo) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}
const MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];

function priceChart(el, rows, ticker) {
  if (!rows.length) { el.innerHTML = '<p class="ikincil">Fiyat verisi yok.</p>'; return; }
  const W = 760, H = 300, L = 58, R = 14, T = 14, B = 28, n = rows.length;
  const athVal = rows.find(r => r.ath != null)?.ath;
  let lo = Math.min(...rows.map(r => r.c)), hi = Math.max(...rows.map(r => Math.max(r.c, r.h52)));
  if (athVal != null && athVal > 0) hi = Math.max(hi, athVal);
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const X = i => L + (W - L - R) * i / Math.max(1, n - 1);
  const Y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  const line = k => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(r[k]).toFixed(1)}`).join("");
  const yt = niceTicks(lo, hi, 4);
  const xt = rows.map((r, i) => ({ r, i })).filter(({ r, i }) => i > 0 && r.t.slice(5, 7) !== rows[i - 1].t.slice(5, 7) && ["01", "04", "07", "10"].includes(r.t.slice(5, 7)));
  const last = rows[n - 1], first = rows[0];
  const chg = last.c / first.c - 1;
  const highs = rows.filter(r => r.c >= r.h52).length;
  const plain = v => Number(v).toLocaleString("tr-TR", { maximumFractionDigits: 2 });
  const summary = `${ticker} haftalık kapanışı ${day(first.t)} ile ${day(last.t)} arasında ${plain(first.c)} dolardan ${plain(last.c)} dolara ${chg >= 0 ? "yükseldi" : "düştü"} (${signed(chg * 100, 0)}). Bu sürede ${highs} hafta önceki 52 haftanın zirvesinin üstünde kapandı.${athVal ? ` Tarihsel zirve (ATH): ${plain(athVal)} $.` : ""}`;
  const capId = "grafik-ozet";
  const athSvg = (athVal && Y(athVal) >= T && Y(athVal) <= H - B)
    ? `<line x1="${L}" x2="${W - R}" y1="${Y(athVal)}" y2="${Y(athVal)}" style="stroke:var(--renk-uyari-9)" stroke-width="1.75" stroke-dasharray="3 3"/>
       <text x="${W - R}" y="${Math.max(T + 12, Y(athVal) - 4)}" text-anchor="end" font-size="11" font-weight="700" style="fill:var(--renk-uyari-9)">ATH ${plain(athVal)} $</text>`
    : "";
  el.innerHTML = `<figure class="grafik">
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="${capId}">
      ${yt.map(v => `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:var(--kenar)"/><text x="${L - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="12" style="fill:var(--metin-ikincil)">${plain(v)}</text>`).join("")}
      ${xt.map(({ r, i }) => `<text x="${X(i)}" y="${H - 8}" text-anchor="middle" font-size="12" style="fill:var(--metin-ikincil)">${MONTHS[+r.t.slice(5, 7) - 1]} ${r.t.slice(2, 4)}</text>`).join("")}
      ${athSvg}
      <path d="${line("h52")}" fill="none" style="stroke:var(--renk-gri-9)" stroke-width="1.5" stroke-dasharray="5 4"/>
      <path d="${line("c")}" fill="none" style="stroke:var(--vurgu)" stroke-width="2.25"/>
      <line class="dikey" x1="0" x2="0" y1="${T}" y2="${H - B}" style="stroke:var(--metin-ikincil)" visibility="hidden"/>
    </svg>
    <div class="grafik-ipucu" aria-hidden="true" hidden></div>
    <figcaption id="${capId}">${esc(summary)} Düz mavi çizgi haftalık kapanış, kesikli gri çizgi 52 haftalık zirve${athVal ? ", noktalı sarı çizgi Tüm Zamanların Zirvesi (ATH)" : ""}.</figcaption>
  </figure>`;
  const svg = $("svg", el), tip = $(".grafik-ipucu", el), vline = $(".dikey", el);
  svg.addEventListener("mousemove", e => {
    const rect = svg.getBoundingClientRect();
    const x = (e.clientX - rect.left) * W / rect.width;
    const i = Math.max(0, Math.min(n - 1, Math.round((x - L) / (W - L - R) * (n - 1))));
    const r = rows[i];
    vline.setAttribute("x1", X(i)); vline.setAttribute("x2", X(i)); vline.setAttribute("visibility", "visible");
    tip.hidden = false;
    const athTxt = r.ath ? `, ATH ${plain(r.ath)} $` : "";
    tip.textContent = `${day(r.t)}: ${plain(r.c)} $ (52H zirve ${plain(r.h52)} $${athTxt})`;
    tip.style.left = Math.min(rect.width - 230, Math.max(0, X(i) * rect.width / W - 115)) + "px";
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; vline.setAttribute("visibility", "hidden"); });
}


function industryBars(groups, n = 8) {
  const top = (groups || []).slice(0, n);
  if (!top.length) return '<p class="ikincil">Veri yok.</p>';
  const max = Math.max(...top.map(g => g.adet), 1);
  return `<ul class="cubuklar">${top.map(g => `<li><span>${esc(g.endustri)}</span>
    <span class="iz" aria-hidden="true"><i style="width:${g.adet / max * 100}%"></i></span>
    <span class="deger">${g.adet}<span class="sr-only"> hisse</span></span></li>`).join("")}</ul>`;
}

// ================================================================== SAYFALAR
async function pagePanel() {
  const [st, mkt, alerts] = await Promise.all([api("/durum"), api("/piyasa").catch(() => []), api("/uyarilar").catch(() => [])]);
  const scan = st.son_tarama ? await api("/taramalar/son") : null;
  const running = st.is && st.is.durum === "calisiyor";
  const modelNote = st.model ? "" : `<div class="kutu kutu--uyari alt-bosluk"><p><strong>Teknik model henüz oluşturulmadı.</strong> Puanın en büyük bileşeni bu modelden gelir. <a href="#/analiz">Analiz sayfasından</a> bir kez oluşturun; ilk sefer 5 ila 10 dakika sürer.</p></div>`;
  const market = mkt.length ? `<section class="bolum" aria-labelledby="h-piyasa"><h2 id="h-piyasa">Piyasa</h2>
      <div class="tablo-kap"><table class="tablo tablo--sik"><caption class="sr-only">Endeks fonlarının günlük değişimi ve 52 haftalık zirveye uzaklığı</caption>
      <thead><tr><th scope="col" class="sol">Fon</th><th scope="col">Fiyat</th><th scope="col">Gün</th><th scope="col">Zirveye</th></tr></thead>
      <tbody>${mkt.map(m => `<tr><th scope="row" class="sol">${tick(m.sembol)}</th><td>${nf(m.fiyat, 2)}</td><td>${pct(m.degisim, 2)}</td><td>${pct(m.zirveye, 1)}</td></tr>`).join("")}</tbody></table></div>
      <p class="not">Zirveye: 52 haftalık en yüksek fiyata uzaklık.</p></section>` : "";
  const alertList = alerts.slice(0, 4);
  const alertsBox = `<section class="bolum" aria-labelledby="h-uyari"><h2 id="h-uyari">Son uyarılar</h2>
    ${alertList.length ? `<ul class="uyarilar">${alertList.map(a => `<li class="${a.seen ? "" : "yeni"}">${when(a.created_at)}<span>${a.ticker ? tick(a.ticker) + ": " : ""}${esc(a.message)}</span></li>`).join("")}</ul>
      <p class="ust-bosluk"><a href="#/uyarilar">Tüm uyarılar</a></p>` : '<p class="ikincil">Uyarı yok. Eşiği <a href="#/ayarlar">Ayarlar</a> sayfasından değiştirebilirsiniz.</p>'}</section>`;

  if (!scan) {
    render(`<div class="sayfa-bas"><div><h1>Panel</h1><p class="aciklama">Henüz tarama yapılmadı.</p></div></div>
      ${modelNote}<div data-is-paneli="tarama">${running ? jobPanel(st.is) : ""}</div>
      <div class="duzen"><section class="bolum bos-durum"><h2>İlk taramayı başlatın</h2>
        <p>Finviz'deki tüm zamanların ve 52 haftanın zirvesindeki hisseler ve ETF'ler puanlanıp burada listelenir. Yaklaşık 2 dakika sürer.</p>
        <button type="button" class="dugme dugme--birincil" data-tara>Taramayı başlat</button></section>
        <div class="yigin">${market}${alertsBox}</div></div>`);
  } else {
    const s = scan.hisseler, e = scan.etfler;
    const high = s.filter(x => x.risk === "Yüksek").length;
    render(`<div class="sayfa-bas"><div><h1>Panel</h1>
        <p class="aciklama">Son tarama ${when(scan.started_at)}, ${scopeName(scan.options.mod)}: ${scan.n_stocks} hisse ve ${scan.n_etfs} ETF puanlandı, ${high} hissenin riski yüksek.</p></div>
        <div class="dugmeler"><button type="button" class="dugme dugme--birincil" data-tara>Yeni tarama</button></div></div>
      ${modelNote}<div data-is-paneli="tarama">${running ? jobPanel(st.is) : ""}</div>
      <div class="duzen">
        <section class="bolum" aria-labelledby="h-enler">
          <div class="bolum-bas"><h2 id="h-enler">En yüksek puanlı 10 hisse</h2><a href="#/tarama/${scan.id}">Tarama ${scan.id}'in tüm sonuçları</a></div>
          <div class="tablo-kap" role="region" aria-label="En yüksek puanlı hisseler tablosu" tabindex="0"><table class="tablo">
            <thead><tr><th scope="col">Sıra</th><th scope="col" class="sol">Sembol</th><th scope="col">Puan</th><th scope="col">+%50 olasılığı</th><th scope="col">Risk</th><th scope="col" class="sol">Profil</th></tr></thead>
            <tbody>${s.slice(0, 10).map(x => `<tr><td>${x.sira}</td><th scope="row" class="sol">${tick(x.sembol)}</th><td>${score(x.puan)}</td><td>${prob(x.p_up)}</td><td>${riskBadge(x.risk, x.p_down)}</td><td class="sol">${tagBadges((x.etiketler || []).slice(0, 1))}</td></tr>`).join("")}</tbody>
          </table></div>
          <h2 class="ust-bosluk" id="h-endustri">Zirvedeki hisselerin endüstrileri</h2>
          ${industryBars(scan.groups, 8)}
        </section>
        <div class="yigin">
          ${market}
          <section class="bolum" aria-labelledby="h-etf"><h2 id="h-etf">En yüksek puanlı ETF'ler</h2>
            <ol class="uyarilar">${e.slice(0, 5).map(x => `<li>${tick(x.sembol)} <span class="ikincil kucuk">${esc(x.sirket.slice(0, 40))}</span><span class="kucuk">Puan ${nf(x.puan, 1)}, 1 yılda ${pct(x.veri["1 Yıl"])}</span></li>`).join("")}</ol></section>
          ${alertsBox}
        </div>
      </div>`);
  }
  $$("[data-tara]", main).forEach(b => b.addEventListener("click", async () => {
    if (await startScan({})) { b.setAttribute("aria-disabled", "true"); }
  }));
  return "Panel";
}

async function pageScans() {
  const [scans, settings, st] = await Promise.all([api("/taramalar"), api("/ayarlar"), api("/durum")]);
  const t = settings.tarama;
  const running = st.is && st.is.durum === "calisiyor";
  const chk = (id, label, hint, on) => `<div class="secenek"><input type="checkbox" id="${id}" aria-describedby="${id}-ip" ${on ? "checked" : ""}><label for="${id}">${label}</label><p class="ipucu" id="${id}-ip">${hint}</p></div>`;
  const radio = (name, id, val, label, hint, on) => `<div class="secenek"><input type="radio" name="${name}" id="${id}" value="${val}" aria-describedby="${id}-ip" ${on ? "checked" : ""}><label for="${id}">${label}</label><p class="ipucu" id="${id}-ip">${hint}</p></div>`;
  render(`<div class="sayfa-bas"><div><h1>Taramalar</h1><p class="aciklama">Yeni tarama başlatın ya da geçmiş taramaları açın.</p></div></div>
    <div data-is-paneli="tarama">${st.is && st.is.tur === "tarama" ? jobPanel(st.is) : ""}</div>
    <div class="duzen">
      <section class="bolum" aria-labelledby="h-gecmis"><h2 id="h-gecmis">Geçmiş taramalar</h2>
        ${scans.length ? `<div class="tablo-kap" role="region" aria-label="Geçmiş taramalar tablosu" tabindex="0"><table class="tablo">
          <thead><tr><th scope="col">No</th><th scope="col" class="sol">Zaman</th><th scope="col" class="sol">Başlatan</th><th scope="col" class="sol">Kapsam</th><th scope="col">Hisse</th><th scope="col">ETF</th><th scope="col" class="sol">Durum</th><th scope="col"><span class="sr-only">İşlem</span></th></tr></thead>
          <tbody>${scans.map(s => `<tr><td>${s.id}</td>
            <th scope="row" class="sol">${s.status === "tamam" ? `<a href="#/tarama/${s.id}">${when(s.started_at)}</a>` : when(s.started_at)}</th>
            <td class="sol">${{ elle: "Siz", zamanlama: "Otomatik", komut: "Komut satırı" }[s.trigger] || esc(s.trigger)}</td>
            <td class="sol">${s.options.mod === "genis" ? "Geniş" : "Zirve"}</td><td>${s.n_stocks}</td><td>${s.n_etfs}</td>
            <td class="sol">${s.status === "tamam" ? '<span class="rozet rozet--olumlu">Tamam</span>' : s.status === "hata" ? `<span class="rozet rozet--olumsuz">Hata</span><span class="sr-only">: ${esc(s.error)}</span>` : '<span class="rozet">Sürüyor</span>'}</td>
            <td>${s.status !== "calisiyor" ? `<button type="button" class="dugme dugme--kucuk dugme--tehlike" data-sil="${s.id}">Sil<span class="sr-only"> tarama ${s.id}</span></button>` : ""}</td></tr>`).join("")}</tbody>
        </table></div>` : '<p class="ikincil">Henüz tarama yok.</p>'}
      </section>
      <section class="bolum" aria-labelledby="h-yeni"><h2 id="h-yeni">Yeni tarama</h2>
        <form id="tarama-formu" novalidate>
          <fieldset aria-describedby="kapsam-ip"><legend>Tarama kapsamı</legend>
            <p class="ipucu" id="kapsam-ip">Varsayılanı Ayarlar sayfasından değiştirebilirsiniz.</p>
            <div class="secenekler">
              ${radio("kapsam", "k-zirve", "zirve", "Zirvedekiler", "Tüm zamanların ve 52 haftanın zirvesindekiler. Yaklaşık 2 dakika.", t.mod !== "genis")}
              ${radio("kapsam", "k-genis", "genis", "Zirveye yakınlar dahil", "52 haftalık zirveye yüzde 5 yakın olanlar da. Yaklaşık 5 dakika.", t.mod === "genis")}
            </div>
          </fieldset>
          <details class="ust-bosluk"><summary>Ek seçenekler</summary>
            <fieldset><legend>Dahil edilecekler</legend><p class="ipucu">Uygun olanların hepsini seçin.</p>
              <div class="secenekler">
                ${chk("s-ath-only", "Sadece Gerçek ATH (52H zirvelerini ele)", "Tarihsel en yüksek seviyesinde olmayan hisseleri tarama dışı bırakır", false)}
                ${chk("s-kucuk", "Küçük şirketler", "Piyasa değeri 300 milyon doların altındakiler", t.kucuk)}
                ${chk("s-kal", "Kaldıraçlı ETF'ler", "Günlük 2 ya da 3 kat getiri hedefleyen fonlar", t.kaldiracli)}
                ${chk("s-tav", "Tampon, gelir ve tahvil ETF'leri", "Yükselişi yapısı gereği sınırlı fonlar", t.tavanli)}
              </div></fieldset>
          </details>
          <div class="dugmeler ust-bosluk"><button type="submit" class="dugme dugme--birincil" ${running ? 'aria-disabled="true" aria-describedby="tf-mesaj"' : ""}>Taramayı başlat</button></div>
          <p class="ipucu" id="tf-mesaj" role="status">${running ? "Bir iş sürüyor; bitince yeniden başlatabilirsiniz." : ""}</p>
        </form>
      </section>
    </div>`);
  $("#tarama-formu").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = $('#tarama-formu [type="submit"]');
    if (btn.getAttribute("aria-disabled") === "true") { $("#tf-mesaj").textContent = "Bir iş sürüyor; bitince yeniden başlatabilirsiniz."; return; }
    const ok = await startScan({
      mod: $('[name="kapsam"]:checked').value,
      sadece_gercek_ath: $("#s-ath-only").checked,
      kucuk: $("#s-kucuk").checked, kaldiracli: $("#s-kal").checked, tavanli: $("#s-tav").checked,
    });
    if (ok) { btn.setAttribute("aria-disabled", "true"); $("#tf-mesaj").textContent = "Tarama başladı. İlerleme sayfanın üstünde görünür."; }
  });
  $$("[data-sil]", main).forEach(b => b.addEventListener("click", async () => {
    const id = b.dataset.sil;
    const ok = await confirmAction({ baslik: `Tarama ${id} silinsin mi?`, metin: "Taramanın sonuçları ve uyarıları kalıcı olarak silinir. Bu işlem geri alınamaz.", tamam: "Taramayı sil" });
    if (!ok) return;
    await del("/taramalar/" + id);
    notify(`Tarama ${id} silindi.`);
    route({ focus: false });
  }));
  return "Taramalar";
}

async function pageScan(id) {
  const s = await api("/taramalar/" + id);
  render(`<div class="sayfa-bas"><div><h1>Tarama ${s.id}</h1>
      <p class="aciklama">${when(s.started_at)}, ${scopeName(s.options.mod)}. ${s.n_stocks} hisse ve ${s.n_etfs} ETF puanlandı.</p></div>
      <div class="dugmeler"><a class="dugme" href="/api/taramalar/${s.id}/csv?tur=Hisse" download>Hisseleri indir (CSV)</a>
        <a class="dugme" href="/api/taramalar/${s.id}/csv?tur=ETF" download>ETF'leri indir (CSV)</a>
        <a class="dugme" href="/api/taramalar/${s.id}/html" download>Raporu indir (HTML)</a></div></div>
    <div id="sekmeler">
      <div role="tablist" aria-label="Sonuç türü">
        <button type="button" role="tab" id="sk-h" aria-controls="sp-h">Hisseler (${s.hisseler.length})</button>
        <button type="button" role="tab" id="sk-e" aria-controls="sp-e">ETF'ler (${s.etfler.length})</button>
        <button type="button" role="tab" id="sk-g" aria-controls="sp-g">Endüstriler (${s.groups.length})</button>
      </div>
      <div role="tabpanel" id="sp-h" aria-labelledby="sk-h" tabindex="0"></div>
      <div role="tabpanel" id="sp-e" aria-labelledby="sk-e" tabindex="0" hidden></div>
      <div role="tabpanel" id="sp-g" aria-labelledby="sk-g" tabindex="0" hidden>
        <div class="tablo-kap"><table class="tablo"><caption>Zirvedeki hisselerin endüstrileri ve endüstrinin kendi getirisi</caption>
          <thead><tr><th scope="col" class="sol">Endüstri</th><th scope="col">Zirvedeki hisse</th><th scope="col">Endüstri 3 ay</th><th scope="col">6 ay</th><th scope="col">1 yıl</th><th scope="col" class="sol">Hisseler</th></tr></thead>
          <tbody>${s.groups.map(g => `<tr><th scope="row" class="sol">${esc(g.endustri)}</th><td>${g.adet}</td><td>${pct(g.q)}</td><td>${pct(g.h)}</td><td>${pct(g.y)}</td><td class="sol sar">${g.semboller.map(tick).join(", ")}</td></tr>`).join("")}</tbody></table></div>
      </div>
    </div>`);
  resultsTable($("#sp-h"), s.hisseler, "Hisse", `Tarama ${s.id} hisse sonuçları, puana göre sıralı`);
  resultsTable($("#sp-e"), s.etfler, "ETF", `Tarama ${s.id} ETF sonuçları, puana göre sıralı`);
  tabs($("#sekmeler"));
  return `Tarama ${s.id}`;
}

async function pageTicker(t) {
  t = t.toUpperCase();
  const d = await api("/hisse/" + encodeURIComponent(t));
  let it = d.son;
  const ath = d.ath || (it ? { is_true_ath: it.is_true_ath, ath_price: it.ath_fiyat, ath_date: it.ath_tarih, dist_from_ath_pct: it.ath_uzaklik_yuzde, mavi_gokyuzu: it.mavi_gokyuzu } : null);
  const enc = encodeURIComponent(t);
  const draw = () => {
    const sub = it ? `${esc(it.sektor)}${it.endustri ? ", " + esc(it.endustri) : ""}` : "";
    const meta = !it ? "Bu sembol henüz bir taramada yer almadı."
      : it.anlik ? "Anlık puan: şimdi hesaplandı, kaydedilmedi."
      : `${when(it.tarama_zamani)} taramasında ${it.sira}. sıra.`;
    const watchBtn = `<button type="button" class="dugme" id="tk-izle">${d.izleniyor ? "İzleme listesinden çıkar" : "İzleme listesine ekle"}</button>`;
    const scoreBtn = `<button type="button" class="dugme ${it ? "" : "dugme--birincil"}" id="tk-puanla">${it && !it.anlik ? "Güncel verilerle puanla" : it ? "Yeniden puanla" : "Şimdi puanla"}</button>`;

    const badges = [];
    if (it?.arketip) badges.push(`<span class="rozet rozet--arketip">${esc(it.arketip)}</span>`);
    if (ath) {
      if (ath.is_true_ath) badges.push('<span class="rozet rozet--ath">Gerçek ATH (Mavi Gökyüzü)</span>');
      else badges.push(`<span class="rozet rozet--uyari">52H Zirvesi (-%${nf(ath.dist_from_ath_pct, 1)} ATH)</span>`);
    }
    if (it) {
      const rest = (it.etiketler || []).filter(x => x !== 'Gerçek ATH' && x !== '52H Zirvesi' && x !== it.arketip);
      if (rest.length) badges.push(tagBadges(rest));
    }
    const badgesHtml = badges.length ? `<div class="rozetler ust-bosluk">${badges.join(" ")}</div>` : "";

    const athBox = ath ? `<div class="kutu ${ath.is_true_ath ? 'kutu--basari' : 'kutu--uyari'} alt-bosluk">
      <strong>${ath.is_true_ath ? 'Tüm Zamanların Zirvesi (Gerçek ATH)' : '52 Haftalık Zirve (Tarihsel Zirve Değil)'}</strong>:
      ${ath.is_true_ath
        ? `Tarihsel rekor seviyede (${nf(ath.ath_price, 2)} $). Hissenin üstünde zararda bekleyen hiçbir yatırımcı yok; satış baskısız açık gökyüzü kırılımı.`
        : `Tarihsel zirve <strong>${nf(ath.ath_price, 2)} $</strong> (${ath.ath_date || 'geçmiş döngü'}). Güncel fiyat tarihi zirvesinin <strong>-%${nf(ath.dist_from_ath_pct, 1)}</strong> altında. Eski tepelerden kalan maliyetli yatırımcıların satış direnci oluşturma riski bulunur.`}
    </div>` : "";

    const firsatHtml = it ? opportunityReportHtml(it) : "";
    const planHtml = it?.plan && it.plan.stop_loss ? `<section class="bolum alt-bosluk" aria-labelledby="h-plan"><h2 id="h-plan">1 Yıllık Multi-Bagger Eylem Planı</h2>${tradingPlanHtml(it.plan)}</section>` : "";
    const factsHtml = it ? `<section class="bolum alt-bosluk" aria-labelledby="h-metrik"><h2 id="h-metrik">Kapsamlı Finansal ve Teknik Metrikler</h2>${categorizedFactsHtml(it)}</section>` : "";

    const catalystsHtml = it?.katalizorler && it.katalizorler.length ? `
      <section class="bolum alt-bosluk" aria-labelledby="h-kataliz">
        <h2 id="h-kataliz">1 Yıllık Yükseliş Katalizörleri</h2>
        <ul class="liste">${it.katalizorler.map(c => `<li>${esc(c)}</li>`).join("")}</ul>
      </section>` : "";

    render(`<div class="sayfa-bas"><div>${sub ? `<p class="ikincil">${sub}</p>` : ""}
        <h1>${esc(t)}${it ? ` <span class="ikincil" style="font-weight:400">${esc(it.sirket)}</span>` : ""}</h1>
        <p class="aciklama">${meta}</p>${badgesHtml}</div>
        <div class="dugmeler">${watchBtn}${scoreBtn}</div></div>
      <p class="hata-mesaji" id="tk-hata" role="alert" hidden></p>
      ${athBox}
      ${it ? `<dl class="ozet ozet--buyuk alt-bosluk"><div><dt>Puan (100 üzerinden)</dt><dd>${nf(it.puan, 1)}</dd></div>
        <div><dt>12 ayda +%50 olasılığı</dt><dd>${prob(it.p_up)}</dd></div>
        <div><dt>Risk</dt><dd>${esc(it.risk)}<span class="kucuk ikincil" style="font-family:var(--yazi-aile-govde);font-weight:400"> (${prob(it.p_down)} düşüş olasılığı)</span></dd></div></dl>` : ""}
      ${firsatHtml}
      <section class="bolum alt-bosluk" aria-labelledby="h-fiyat"><h2 id="h-fiyat">Fiyat, son 3 yıl (haftalık)</h2><div id="tk-grafik"><p class="ikincil">Fiyat geçmişi yükleniyor</p></div></section>
      ${planHtml}
      ${catalystsHtml}
      ${factsHtml}
      <div class="duzen-esit alt-bosluk">
        <section class="bolum" aria-labelledby="h-neden">${it ? reasonsHtml(it, 2).replace("<h2>", '<h2 id="h-neden">') : '<h2 id="h-neden">Neden yükselebilir?</h2><p class="ikincil">Puan için "Şimdi puanla" düğmesini kullanın.</p>'}</section>
        <section class="bolum" aria-labelledby="h-bilesen"><h2 id="h-bilesen">Puan bileşenleri</h2>${it ? subBars(it) : '<p class="ikincil">Puan yok.</p>'}</section>
      </div>
      <div class="duzen-esit alt-bosluk">
        <section class="bolum" aria-labelledby="h-gecmis"><h2 id="h-gecmis">Puan geçmişi</h2>${d.gecmis.length ? `<div class="tablo-kap"><table class="tablo">
          <thead><tr><th scope="col" class="sol">Tarama</th><th scope="col">Sıra</th><th scope="col">Puan</th><th scope="col">+%50 olasılığı</th><th scope="col">Fiyat ($)</th></tr></thead>
          <tbody>${d.gecmis.slice().reverse().map(x => `<tr><th scope="row" class="sol"><a href="#/tarama/${x.scan_id}">${when(x.started_at)}</a></th><td>${x.rank}</td><td>${nf(x.score, 1)}</td><td>${prob(x.p_up)}</td><td>${nf(x.price, 2)}</td></tr>`).join("")}</tbody></table></div>` : '<p class="ikincil">Bu sembol kayıtlı taramalarda yok.</p>'}</section>
        <section class="bolum" aria-labelledby="h-haber"><h2 id="h-haber">Son haberler</h2><div id="tk-haber"><p class="ikincil">Haberler yükleniyor</p></div></section>
      </div>
      <p class="ikincil">Başka kaynaklarda açın:
        <a href="https://finviz.com/quote.ashx?t=${enc}" target="_blank" rel="noopener">Finviz<span class="sr-only"> (yeni sekmede)</span></a>,
        <a href="https://finance.yahoo.com/quote/${enc}" target="_blank" rel="noopener">Yahoo Finance<span class="sr-only"> (yeni sekmede)</span></a>,
        <a href="https://www.tradingview.com/symbols/${enc}/" target="_blank" rel="noopener">TradingView<span class="sr-only"> (yeni sekmede)</span></a>.</p>`);
    $("#tk-izle").addEventListener("click", async () => {
      const btn = $("#tk-izle");
      try {
        if (d.izleniyor) await del("/izleme/" + enc); else await post("/izleme", { sembol: t });
        d.izleniyor = !d.izleniyor;
        btn.textContent = d.izleniyor ? "İzleme listesinden çıkar" : "İzleme listesine ekle";
        announce(d.izleniyor ? `${t} izleme listesine eklendi.` : `${t} izleme listesinden çıkarıldı.`);
      } catch (e) { showError(e.message); }
    });
    $("#tk-puanla").addEventListener("click", async () => {
      const btn = $("#tk-puanla");
      btn.setAttribute("aria-disabled", "true");
      btn.textContent = "Puanlanıyor";
      announce(`${t} puanlanıyor.`);
      try {
        it = await api(`/hisse/${enc}/puanla`);
        draw();
        announce(`${t} puanlandı: ${Number(it.puan).toLocaleString("tr-TR")} puan.`);
        $("h1", main).focus();
      } catch (e) {
        btn.removeAttribute("aria-disabled");
        btn.textContent = "Şimdi puanla";
        showError(`${t} puanlanamadı: ${e.message}`);
      }
    });
    loadAsync();
  };
  const showError = msg => { const el = $("#tk-hata"); el.textContent = msg; el.hidden = false; };
  const loadAsync = () => {
    api(`/hisse/${enc}/fiyat`).then(rows => priceChart($("#tk-grafik"), rows, t))
      .catch(e => { $("#tk-grafik").innerHTML = `<p class="ikincil">Fiyat geçmişi alınamadı: ${esc(e.message)}</p>`; });
    api(`/hisse/${enc}/haber`).then(n => { $("#tk-haber").innerHTML = newsList(n); })
      .catch(e => { $("#tk-haber").innerHTML = `<p class="ikincil">Haberler alınamadı: ${esc(e.message)}</p>`; });
  };
  draw();
  return `${t}${it ? " " + it.sirket : ""}`;
}


async function pageWatch() {
  const items = await api("/izleme");
  render(`<div class="sayfa-bas"><div><h1>İzleme listesi</h1><p class="aciklama">Takip ettiğiniz semboller: eklendiği fiyattan bugüne getiri ve son taramadaki puan. Bir sembol taramada eşik puanı geçerse uyarı oluşur.</p></div></div>
    <div class="duzen">
      <section class="bolum" aria-labelledby="h-liste"><h2 id="h-liste">Liste (${items.length})</h2>
      ${items.length ? `<div class="tablo-kap" role="region" aria-label="İzleme listesi tablosu" tabindex="0"><table class="tablo">
        <thead><tr><th scope="col" class="sol">Sembol</th><th scope="col" class="sol">Şirket</th><th scope="col">Eklendi</th><th scope="col">O gün ($)</th><th scope="col">Şimdi ($)</th><th scope="col">Getiri</th><th scope="col">Son puan</th><th scope="col">Risk</th><th scope="col" class="sol">Not</th><th scope="col"><span class="sr-only">İşlem</span></th></tr></thead>
        <tbody>${items.map(w => `<tr><th scope="row" class="sol">${tick(w.ticker)}</th><td class="sol">${esc((w.sirket || "").slice(0, 28))}</td><td>${day(w.added_at)}</td>
          <td>${nf(w.added_price, 2)}</td><td>${nf(w.fiyat, 2)}</td><td>${ret(w.getiri)}</td>
          <td>${w.puan == null ? '<span class="ikincil">Taramada yok</span>' : nf(w.puan, 1)}</td><td>${riskBadge(w.risk)}</td>
          <td class="sol sar">${esc(w.note)}</td>
          <td><button type="button" class="dugme dugme--kucuk dugme--tehlike" data-cikar="${esc(w.ticker)}">Çıkar<span class="sr-only"> ${esc(w.ticker)}</span></button></td></tr>`).join("")}</tbody></table></div>`
        : '<p class="ikincil">Liste boş. Yandaki formdan ya da bir hisse sayfasındaki "İzleme listesine ekle" düğmesinden ekleyebilirsiniz.</p>'}
      </section>
      <section class="bolum" aria-labelledby="h-ekle"><h2 id="h-ekle">Sembol ekle</h2>
        <form id="izle-formu" novalidate>
          <div class="alan" id="w-alan">
            <label class="etiket" for="w-sembol">Sembol</label>
            <p class="ipucu" id="w-ipucu">Örneğin DHT ya da PLTR</p>
            <p class="hata-mesaji" id="w-hata" hidden></p>
            <input type="text" id="w-sembol" class="genislik-orta" maxlength="10" autocomplete="off" spellcheck="false" aria-describedby="w-ipucu" style="text-transform:uppercase">
          </div>
          <details class="ust-bosluk"><summary>Not ekle (isteğe bağlı)</summary>
            <div class="alan"><label class="etiket" for="w-not">Not</label><textarea id="w-not" rows="2" maxlength="300"></textarea></div></details>
          <div class="dugmeler ust-bosluk"><button type="submit" class="dugme dugme--birincil">Listeye ekle</button></div>
        </form>
      </section>
    </div>`);
  const input = $("#w-sembol");
  const setError = msg => {
    const err = $("#w-hata");
    err.hidden = !msg;
    err.innerHTML = msg ? `<span class="sr-only">Hata: </span>${esc(msg)}` : "";
    if (msg) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", "w-ipucu w-hata"); input.focus(); }
    else { input.removeAttribute("aria-invalid"); input.setAttribute("aria-describedby", "w-ipucu"); }
  };
  $("#izle-formu").addEventListener("submit", async e => {
    e.preventDefault();
    const t = input.value.trim().toUpperCase();
    if (!t) return setError("Bir sembol yazın, örneğin DHT.");
    if (!/^[A-Z0-9.\-]{1,10}$/.test(t)) return setError("Sembol yalnızca harf, rakam, nokta ve kısa çizgi içerebilir.");
    try {
      await post("/izleme", { sembol: t, not: $("#w-not").value });
      setError("");
      notify(`${t} izleme listesine eklendi.`);
      await route({ focus: false });
      $("#w-sembol").focus();
    } catch (err) {
      setError(/bulunamadı/i.test(err.message) ? `${t} sembolü Finviz'de bulunamadı. Yazımı kontrol edin.` : err.message);
    }
  });
  $$("[data-cikar]", main).forEach(b => b.addEventListener("click", async () => {
    const t = b.dataset.cikar;
    const w = items.find(x => x.ticker === t);
    await del("/izleme/" + encodeURIComponent(t));
    await route({ focus: false });
    $("#h-liste").focus?.();
    notify(`${t} izleme listesinden çıkarıldı.`, {
      sure: 12000,
      eylem: { etiket: "Geri al", fn: async () => {
        await post("/izleme", { sembol: t, not: w.note, fiyat: w.added_price, eklenme: w.added_at });
        announce(`${t} geri eklendi.`);
        route({ focus: false });
      } },
    });
  }));
  return "İzleme listesi";
}

async function pagePerf() {
  let n = +(sessionStorage.getItem("perfN") || 10);
  render('<h1>Performans</h1><p class="ikincil ust-bosluk">Güncel fiyatlar alınıyor</p>');
  const p = await api("/performans?ilk=" + n);
  const block = kind => {
    const s = p.ozet[kind];
    const title = kind === "Hisse" ? "Hisse adayları" : "ETF adayları";
    if (!s) return `<section class="bolum"><h2>${title}</h2><p class="ikincil">En az bir günlük tarama olunca burada görünür.</p></section>`;
    return `<section class="bolum"><h2>${title}</h2><p class="ikincil kucuk alt-bosluk">${s.n} farklı aday, ilk göründükleri taramadan bugüne.</p>
      <dl class="ozet"><div><dt>Ortalama getiri</dt><dd>${ret(s.ort)}</dd></div><div><dt>SPY'a göre fark</dt><dd>${ret(s.spy_ustu)}</dd></div>
        <div><dt>Kazandıranların oranı</dt><dd>%${Math.round(s.isabet * 100)}</dd></div><div><dt>Medyan</dt><dd>${ret(s.medyan)}</dd></div></dl>
      <p class="ust-bosluk">En iyi ${tick(s.en_iyi.sembol)} ${ret(s.en_iyi.getiri)}, en kötü ${tick(s.en_kotu.sembol)} ${ret(s.en_kotu.getiri)}.</p></section>`;
  };
  render(`<div class="sayfa-bas"><div><h1>Performans</h1><p class="aciklama">Her taramanın ilk adaylarının, tarama anındaki fiyattan bugüne getirisi. Modelin gerçekte işe yarayıp yaramadığını burada görürsünüz.</p></div>
      <fieldset><legend>Her taramadan kaç aday</legend><div class="bolumlu">${[5, 10, 20].map(x => `<input type="radio" name="pn" id="pn${x}" value="${x}" ${x === n ? "checked" : ""}><label for="pn${x}">İlk ${x}</label>`).join("")}</div></fieldset></div>
    <div class="duzen-esit alt-bosluk">${block("Hisse")}${block("ETF")}</div>
    <section class="bolum" aria-labelledby="h-tar"><h2 id="h-tar">Taramalara göre</h2>
      ${p.taramalar.length ? `<div class="tablo-kap" role="region" aria-label="Taramalara göre getiri tablosu" tabindex="0"><table class="tablo">
        <thead><tr><td></td><th scope="col" class="sol">Tarama</th><th scope="col" class="sol">Zaman</th><th scope="col">Geçen gün</th><th scope="col">Hisse ortalaması</th><th scope="col">ETF ortalaması</th><th scope="col">SPY</th></tr></thead>
        <tbody>${p.taramalar.map(s => `<tr data-id="${s.tarama_id}"><td><button type="button" class="ac-kapa" aria-expanded="false" aria-controls="pd-${s.tarama_id}">${ICON.ok}<span class="sr-only">Tarama ${s.tarama_id} adayları</span></button></td>
          <th scope="row" class="sol"><a href="#/tarama/${s.tarama_id}">Tarama ${s.tarama_id}</a></th><td class="sol">${when(s.zaman)}</td><td>${s.gun}</td><td>${ret(s.ort_hisse)}</td><td>${ret(s.ort_etf)}</td><td>${ret(s.spy)}</td></tr>`).join("")}</tbody></table></div>`
        : '<p class="ikincil">Henüz tarama yok.</p>'}
      <p class="not">Getiriler temettü hariçtir.</p></section>`);
  $$('[name="pn"]', main).forEach(r => r.addEventListener("change", e => { sessionStorage.setItem("perfN", e.target.value); route({ focus: false }); }));
  $("tbody", main)?.addEventListener("click", e => {
    const btn = e.target.closest(".ac-kapa");
    if (!btn) return;
    const tr = btn.closest("tr");
    if (btn.getAttribute("aria-expanded") === "true") { $("#" + btn.getAttribute("aria-controls"))?.remove(); btn.setAttribute("aria-expanded", "false"); return; }
    const s = p.taramalar.find(x => x.tarama_id === +tr.dataset.id);
    const d = document.createElement("tr");
    d.className = "ayrinti";
    d.id = btn.getAttribute("aria-controls");
    d.innerHTML = `<td colspan="7"><div class="tablo-kap"><table class="tablo"><caption>Tarama ${s.tarama_id} adaylarının getirisi</caption>
      <thead><tr><th scope="col" class="sol">Tür</th><th scope="col">Sıra</th><th scope="col" class="sol">Sembol</th><th scope="col">Puan</th><th scope="col">O gün ($)</th><th scope="col">Bugün ($)</th><th scope="col">Getiri</th></tr></thead>
      <tbody>${s.adaylar.map(a => `<tr><td class="sol">${a.tur}</td><td>${a.sira}</td><th scope="row" class="sol">${tick(a.sembol)}</th><td>${nf(a.puan, 1)}</td><td>${nf(a.fiyat0, 2)}</td><td>${nf(a.fiyat, 2)}</td><td>${ret(a.getiri)}</td></tr>`).join("")}</tbody></table></div></td>`;
    tr.after(d);
    btn.setAttribute("aria-expanded", "true");
    scrollRegions();
  });
  return "Performans";
}

async function pageAnalysis() {
  const [A, st] = await Promise.all([api("/analiz"), api("/durum")]);
  const has = A && A.model;
  const running = st.is && st.is.durum === "calisiyor";
  const head = `<thead><tr><th scope="col" class="sol">Grup</th><th scope="col">Olay sayısı</th><th scope="col">Medyan 12 ay getiri</th><th scope="col">+%50 ve üstü</th><th scope="col">+%100 ve üstü</th><th scope="col">−%30 ve altı</th></tr></thead>`;
  const row = (lab, s) => s && s.n ? `<tr><th scope="row" class="sol">${esc(lab)}</th><td>${nf(s.n)}</td><td>${pct(s.medyan * 100)}</td><td>%${Math.round(s.p50 * 100)}</td><td>%${Math.round(s.p100 * 100)}</td><td>%${Math.round(s.kayip30 * 100)}</td></tr>` : "";
  const table = (cap, rows) => `<div class="tablo-kap"><table class="tablo"><caption>${esc(cap)}</caption>${head}<tbody>${rows}</tbody></table></div>`;
  render(`<div class="sayfa-bas"><div><h1>Analiz ve model</h1>
      <p class="aciklama">${has ? `Son analiz ${day(A.tarih + " ")} tarihinde ${nf(A.hisse_sayisi)} hissenin 5 yıllık haftalık verisiyle yapıldı.` : "Model henüz oluşturulmadı."}</p></div></div>
    <div data-is-paneli="analiz">${st.is && st.is.tur === "analiz" ? jobPanel(st.is) : ""}</div>
    <div class="duzen alt-bosluk">
      <section class="bolum" aria-labelledby="h-ne"><h2 id="h-ne">Ne yapıyor?</h2>
        <p>Likit ABD hisselerinin 5 yıllık haftalık fiyatında, her 4 haftada bir 52 haftalık zirve yapan hisseleri bulur ve sonraki 12 ayın getirisine bakar. Bu olaylardan iki model eğitir: 12 ayda yüzde 50'den fazla yükselme ve yüzde 30'dan fazla düşme olasılığı. Taramalardaki <strong>teknik model</strong> puanı ve <strong>risk</strong> sütunu bu modellerden gelir.</p>
        <p class="not">Evren bugün işlem gören hisselerden oluştuğu için oranlar iyimserdir; gruplar arası farklar daha anlamlıdır.</p></section>
      <section class="bolum" aria-labelledby="h-calistir"><h2 id="h-calistir">${has ? "Yeniden çalıştır" : "Modeli oluştur"}</h2>
        <form id="analiz-formu" novalidate>
          <p>Ayda bir yeniden çalıştırmak yeterlidir. Önbellekle yaklaşık 1 dakika sürer.</p>
          <div class="secenekler ust-bosluk"><div class="secenek"><input type="checkbox" id="a-yenile" aria-describedby="a-yenile-ip"><label for="a-yenile">Verileri yeniden indir</label>
            <p class="ipucu" id="a-yenile-ip">Hisse listesini ve fiyatları baştan indirir; 5 ila 10 dakika sürer.</p></div></div>
          <div class="dugmeler ust-bosluk"><button type="submit" class="dugme dugme--birincil" ${running ? 'aria-disabled="true"' : ""}>${has ? "Analizi çalıştır" : "Modeli oluştur"}</button></div>
          <p class="ipucu" id="af-mesaj" role="status">${running ? "Bir iş sürüyor; bitince yeniden deneyin." : ""}</p>
        </form></section>
    </div>
    ${has ? `<section class="bolum alt-bosluk" aria-labelledby="h-dogrulama"><h2 id="h-dogrulama">Model doğrulaması</h2>
        <p class="alt-bosluk">${esc(A.model.egitim_bitis)} öncesindeki olaylarla eğitildi, sonraki ${nf(A.model.test_n)} olayda denendi. En yüksek tahmin dilimindeki hisseler, en düşük dilime göre belirgin biçimde daha sık yüzde 50'nin üstünde yükseldi.</p>
        ${table("Tahmin dilimine göre gerçekleşen sonuçlar (test dönemi)", A.model.test_dilimleri.map(r => row(r.grup, r)).join(""))}</section>
      <section class="bolum alt-bosluk" aria-labelledby="h-genel"><h2 id="h-genel">Genel tablo</h2>
        ${table("Zirvede olmanın sonraki 12 aya etkisi", row("Tüm hisse ve tarihler", A.taban_tum_olaylar) + row("52 haftalık yeni zirve", A.yeni_52h_zirve) + row("Zirveye yüzde 5 yakın", A.zirveye_yakin_5) + row("Zirveden uzak", A.zirvede_degil))}</section>
      <div class="duzen-esit">${Object.entries(A.kirilimlar).map(([name, rows], i) => `<section class="bolum" aria-labelledby="h-k${i}"><h2 id="h-k${i}">${esc(name)}</h2>${table(`${name}: yalnızca yeni zirve olayları`, rows.map(r => row(r.grup, r)).join(""))}</section>`).join("")}</div>` : ""}`);
  $("#analiz-formu").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = $('#analiz-formu [type="submit"]');
    if (btn.getAttribute("aria-disabled") === "true") { $("#af-mesaj").textContent = "Bir iş sürüyor; bitince yeniden deneyin."; return; }
    try {
      await post("/analiz", { yenile: $("#a-yenile").checked });
      btn.setAttribute("aria-disabled", "true");
      $("#af-mesaj").textContent = "Analiz başladı. İlerleme sayfanın üstünde görünür.";
      poll();
    } catch (err) { $("#af-mesaj").textContent = err.message; }
  });
  return "Analiz ve model";
}

async function pageAlerts() {
  const items = await api("/uyarilar");
  render(`<div class="sayfa-bas"><div><h1>Uyarılar</h1><p class="aciklama">Taramalardan sonra oluşan bildirimlerin kaydı. Ne zaman uyarı oluşacağını <a href="#/ayarlar">Ayarlar</a> sayfasından seçebilirsiniz.</p></div></div>
    <section class="bolum">${items.length ? `<ul class="uyarilar">${items.map(a => `<li class="${a.seen ? "" : "yeni"}">${when(a.created_at)}${a.seen ? "" : '<span class="sr-only">Yeni.</span>'}
      <span>${a.ticker ? tick(a.ticker) + ": " : ""}${esc(a.message)}${a.scan_id ? ` (<a href="#/tarama/${a.scan_id}">tarama ${a.scan_id}</a>)` : ""}</span></li>`).join("")}</ul>` : '<p class="ikincil">Henüz uyarı yok.</p>'}</section>`);
  if (items.some(a => !a.seen)) {
    await post("/uyarilar/okundu");
    $("#uyari-sayi").hidden = true;
  }
  return "Uyarılar";
}

function currentTheme() {
  try { return localStorage.getItem("tema") || "sistem"; } catch { return "sistem"; }
}
function applyTheme(v) {
  if (v === "acik" || v === "koyu") document.documentElement.dataset.tema = v; else delete document.documentElement.dataset.tema;
  try { if (v === "sistem") localStorage.removeItem("tema"); else localStorage.setItem("tema", v); } catch { /* depolama kapalı */ }
}

async function pageSettings() {
  const s = await api("/ayarlar");
  const radio = (name, id, val, label, on, hint = "") => `<div class="secenek"><input type="radio" name="${name}" id="${id}" value="${val}" ${hint ? `aria-describedby="${id}-ip"` : ""} ${on ? "checked" : ""}><label for="${id}">${label}</label>${hint ? `<p class="ipucu" id="${id}-ip">${hint}</p>` : ""}</div>`;
  const chk = (id, label, on, hint = "") => `<div class="secenek"><input type="checkbox" id="${id}" ${hint ? `aria-describedby="${id}-ip"` : ""} ${on ? "checked" : ""}><label for="${id}">${label}</label>${hint ? `<p class="ipucu" id="${id}-ip">${hint}</p>` : ""}</div>`;
  const weights = (defs, cur, pre) => `<div class="tablo-kap"><table class="tablo"><thead><tr><th scope="col" class="sol">Bileşen</th><th scope="col">Varsayılan</th><th scope="col">Ağırlık</th></tr></thead><tbody>
    ${Object.entries(defs).map(([k, v]) => `<tr><th scope="row" class="sol"><label for="${pre}-${k}">${esc(SUB_NAMES[k] || k)}</label></th><td>${v}</td>
      <td><input type="number" id="${pre}-${k}" data-w="${pre}" data-k="${k}" min="0" max="100" step="1" class="genislik-kisa" value="${cur && cur[k] != null ? cur[k] : v}"></td></tr>`).join("")}</tbody></table></div>`;
  const theme = currentTheme();
  render(`<div class="sayfa-bas"><div><h1>Ayarlar</h1><p class="aciklama">Görünüm hemen uygulanır. Diğer değişiklikler "Ayarları kaydet" ile kaydedilir.</p></div></div>
    <div class="duzen-esit alt-bosluk">
      <section class="bolum" aria-labelledby="h-gorunum"><h2 id="h-gorunum">Görünüm</h2>
        <fieldset><legend>Tema</legend><div class="secenekler">
          ${radio("tema", "t-sistem", "sistem", "Sistem ayarını izle", theme === "sistem")}
          ${radio("tema", "t-acik", "acik", "Açık", theme === "acik")}
          ${radio("tema", "t-koyu", "koyu", "Koyu", theme === "koyu")}</div></fieldset></section>
      <section class="bolum" aria-labelledby="h-tel"><h2 id="h-tel">Telefondan erişim</h2>
        ${s.ag_adresi ? `<p>Aynı Wi-Fi ağındaki cihazlardan bu adresi açın: <strong><a href="${esc(s.ag_adresi)}">${esc(s.ag_adresi)}</a></strong></p>`
          : "<p>Platform şu an yalnızca bu bilgisayardan açılabiliyor. Telefondan açmak için platformu <strong>Baslat-Ag.bat</strong> ile başlatın; adres burada görünür.</p>"}
        <p class="not">Ağ modunda şifre yoktur; yalnızca güvendiğiniz ev ağında kullanın.</p></section>
    </div>
    <form id="ayar-formu" novalidate>
      <div class="kutu kutu--hata alt-bosluk" id="ayar-hatalar" role="alert" tabindex="-1" hidden></div>
      <div class="duzen-esit">
        <section class="bolum" aria-labelledby="h-vt"><h2 id="h-vt">Varsayılan tarama</h2>
          <fieldset><legend>Tarama kapsamı</legend><div class="secenekler">
            ${radio("mod", "m-zirve", "zirve", "Zirvedekiler", s.tarama.mod !== "genis", "Yaklaşık 2 dakika")}
            ${radio("mod", "m-genis", "genis", "Zirveye yakınlar dahil", s.tarama.mod === "genis", "Yaklaşık 5 dakika")}</div></fieldset>
          <fieldset><legend>Dahil edilecekler</legend><p class="ipucu">Uygun olanların hepsini seçin.</p><div class="secenekler">
            ${chk("v-kucuk", "Küçük şirketler", s.tarama.kucuk, "Piyasa değeri 300 milyon doların altındakiler")}
            ${chk("v-kal", "Kaldıraçlı ETF'ler", s.tarama.kaldiracli)}
            ${chk("v-tav", "Tampon, gelir ve tahvil ETF'leri", s.tarama.tavanli)}</div></fieldset>
          <div class="alan"><label class="etiket" for="v-haber">Haberi çekilecek hisse sayısı</label><p class="ipucu" id="v-haber-ip">0 ile 60 arası. Her haber bir istek demektir; sayı arttıkça tarama uzar.</p>
            <input type="number" id="v-haber" class="genislik-kisa" min="0" max="60" value="${s.tarama.haber}" aria-describedby="v-haber-ip"></div>
        </section>
        <section class="bolum" aria-labelledby="h-ot"><h2 id="h-ot">Otomatik tarama</h2>
          <div class="secenekler">${chk("z-aktif", "Her gün otomatik tara", s.zamanlama.aktif, "Platform açıkken çalışır")}</div>
          <div class="alan"><label class="etiket" for="z-saat">Saat</label><p class="ipucu" id="z-saat-ip">Bu bilgisayarın saatiyle. ABD borsası Türkiye saatiyle yazın 23.00'te, kışın 00.00'da kapanır.</p>
            <input type="time" id="z-saat" value="${esc(s.zamanlama.saat)}" aria-describedby="z-saat-ip"></div>
          <div class="secenekler ust-bosluk">${chk("z-hi", "Yalnızca hafta içi", s.zamanlama.sadece_hafta_ici)}</div>
        </section>
        <section class="bolum" aria-labelledby="h-uy"><h2 id="h-uy">Uyarılar</h2>
          <div class="alan"><label class="etiket" for="u-esik">İzleme listesi için puan eşiği</label><p class="ipucu" id="u-esik-ip">0 ile 100 arası</p>
            <input type="number" id="u-esik" class="genislik-kisa" min="0" max="100" value="${s.uyari.esik}" aria-describedby="u-esik-ip"></div>
          <fieldset><legend>Bildirilecekler</legend><p class="ipucu">Uygun olanların hepsini seçin.</p><div class="secenekler">
            ${chk("u-iz", "İzleme listesindeki bir sembol eşiği geçince", s.uyari.izleme)}
            ${chk("u-y10", "Bir hisse ilk 10'a yeni girince", s.uyari.yeni_ilk10)}</div></fieldset>
        </section>
      </div>
      <section class="bolum ust-bosluk" aria-labelledby="h-ag"><h2 id="h-ag">Puan ağırlıkları</h2>
        <details><summary>Uzman ayarlarını göster</summary>
          <p class="alt-bosluk">Toplamın 100 olması gerekmez; puanlama sırasında 100'e ölçeklenir. Değişiklik bir sonraki taramadan itibaren geçerli olur.</p>
          <div class="duzen-esit"><div><h3>Hisse puanı</h3>${weights(s.varsayilan_agirlik, s.agirlik, "wh")}<p class="not" id="wh-toplam" role="status"></p></div>
            <div><h3>ETF puanı</h3>${weights(s.varsayilan_etf_agirlik, s.etf_agirlik, "we")}</div></div>
          <div class="dugmeler ust-bosluk"><button type="button" class="dugme" id="w-sifirla">Ağırlıkları varsayılana döndür</button></div>
        </details></section>
      <div class="dugmeler ust-bosluk"><button type="submit" class="dugme dugme--birincil">Ayarları kaydet</button><p id="ayar-durum" role="status" class="ikincil"></p></div>
    </form>`);
  $$('[name="tema"]', main).forEach(r => r.addEventListener("change", e => {
    applyTheme(e.target.value);
    announce(`Tema: ${e.target.nextElementSibling.textContent}.`);
  }));
  const sum = () => { $("#wh-toplam").textContent = "Hisse ağırlıkları toplamı: " + $$('[data-w="wh"]').reduce((a, i) => a + (+i.value || 0), 0); };
  $$('[data-w="wh"]').forEach(i => i.addEventListener("input", sum));
  sum();
  $("#w-sifirla").addEventListener("click", () => {
    $$('[data-w="wh"]').forEach(i => { i.value = s.varsayilan_agirlik[i.dataset.k]; });
    $$('[data-w="we"]').forEach(i => { i.value = s.varsayilan_etf_agirlik[i.dataset.k]; });
    sum();
    announce("Ağırlıklar varsayılan değerlere döndü. Kaydetmeyi unutmayın.");
  });
  $("#ayar-formu").addEventListener("submit", async e => {
    e.preventDefault();
    const errors = [];
    const num = (id, lo, hi, label) => {
      const el = $("#" + id), v = Number(el.value);
      const bad = el.value === "" || !Number.isFinite(v) || v < lo || v > hi;
      if (bad) { el.setAttribute("aria-invalid", "true"); errors.push(`<a href="#${id}">${label} ${lo} ile ${hi} arasında olmalı</a>`); } else el.removeAttribute("aria-invalid");
      return v;
    };
    const haber = num("v-haber", 0, 60, "Haberi çekilecek hisse sayısı");
    const esik = num("u-esik", 0, 100, "Puan eşiği");
    const saat = $("#z-saat").value;
    if (!/^\d{2}:\d{2}$/.test(saat)) errors.push('<a href="#z-saat">Saat SS:DD biçiminde olmalı</a>');
    const box = $("#ayar-hatalar");
    if (errors.length) {
      box.innerHTML = `<h2>Kaydedilemedi</h2><ul class="liste">${errors.map(x => `<li>${x}</li>`).join("")}</ul>`;
      box.hidden = false;
      box.focus();
      return;
    }
    box.hidden = true;
    const collect = (pre, defs) => {
      const o = {};
      $$(`[data-w="${pre}"]`).forEach(i => { o[i.dataset.k] = Math.max(0, +i.value || 0); });
      return Object.keys(o).every(k => o[k] === defs[k]) ? null : o;
    };
    try {
      await put("/ayarlar", {
        tarama: { mod: $('[name="mod"]:checked').value, haber, kucuk: $("#v-kucuk").checked, kaldiracli: $("#v-kal").checked, tavanli: $("#v-tav").checked },
        zamanlama: { aktif: $("#z-aktif").checked, saat, sadece_hafta_ici: $("#z-hi").checked },
        uyari: { esik, izleme: $("#u-iz").checked, yeni_ilk10: $("#u-y10").checked },
        agirlik: collect("wh", s.varsayilan_agirlik), etf_agirlik: collect("we", s.varsayilan_etf_agirlik),
      });
      $("#ayar-durum").textContent = "Ayarlar kaydedildi.";
    } catch (err) {
      box.innerHTML = `<h2>Kaydedilemedi</h2><p>${esc(err.message)}</p>`;
      box.hidden = false;
      box.focus();
    }
  });
  return "Ayarlar";
}

async function pageHelp() {
  render(`<div class="sayfa-bas"><div><h1>Yardım</h1><p class="aciklama">Platformun nasıl kullanılacağı, terimlerin anlamı ve sık karşılaşılan sorunlar.</p></div></div>
    <div class="duzen">
      <div class="yigin">
        <section class="bolum" aria-labelledby="h-nasil"><h2 id="h-nasil">Nasıl kullanılır</h2>
          <ol class="liste" style="list-style:decimal">
            <li>İlk kurulumda <a href="#/analiz">Analiz</a> sayfasından modeli oluşturun (5 ila 10 dakika, tek sefer).</li>
            <li><a href="#/">Panel</a> ya da <a href="#/taramalar">Taramalar</a> sayfasından tarama başlatın (yaklaşık 2 dakika).</li>
            <li>Sonuç tablosunda bir satırın okuna basarak nedenleri ve riskleri okuyun, ilginç sembolleri izleme listesine ekleyin.</li>
            <li>Birkaç hafta sonra <a href="#/performans">Performans</a> sayfasında adayların SPY'a göre ne yaptığına bakın.</li>
          </ol></section>
        <section class="bolum" aria-labelledby="h-terim"><h2 id="h-terim">Terimler</h2>
          <dl class="sozluk">
            <dt>Puan</dt><dd>100 üzerinden 1 yıllık yükseliş potansiyeli. Teknik model (40), büyüme (25), kurum ve analist (10), değerleme (8), endüstri gücü (7), kalite (5) ve trend (5) bileşenlerinden oluşur.</dd>
            <dt>+%50 olasılığı</dt><dd>Geçmişte benzer teknik profildeki yeni zirve hisselerinin 12 ay içinde yüzde 50'den fazla yükselme oranı. Hayatta kalma yanlılığı nedeniyle iyimserdir.</dd>
            <dt>Risk</dt><dd>Benzer profildeki hisselerin 12 ayda yüzde 30'dan fazla düşme oranı: Düşük (yüzde 8'in altı), Orta (yüzde 8 ile 15), Yüksek (yüzde 15'in üstü).</dd>
            <dt>Hacim artışı</dt><dd>Son 4 haftanın ortalama işlem hacminin 1 yıllık ortalamaya oranı. 2 katın üstü güçlü talep işaretidir.</dd>
            <dt>Satış büyümesi</dt><dd>Son çeyreğin satışlarının bir yıl önceki aynı çeyreğe göre değişimi.</dd>
            <dt>Gelecek yıl kâr</dt><dd>Analistlerin gelecek mali yıl için beklediği hisse başı kâr değişimi.</dd>
            <dt>İleri F/K</dt><dd>Fiyatın gelecek yılın beklenen hisse başı kârına oranı. Düşük olması ucuzluğa işaret eder.</dd>
            <dt>Zirvedekiler ve geniş kapsam</dt><dd>Zirvedekiler: bugün tüm zamanların ya da 52 haftanın en yüksek fiyatına ulaşanlar. Geniş kapsam: 52 haftalık zirveye yüzde 5 yakın olanlar da.</dd>
            <dt>Döngüsel zirve</dt><dd>Kârı şu an çok yüksek ama analistlerin gelecek yıl düşüş beklediği şirketler (ör. navlun fiyatı yüksek tankerler).</dd>
            <dt>Tavanlı getiri</dt><dd>Tampon, opsiyon geliri ya da tahvil ETF'leri; yapıları gereği büyük yükseliş yakalayamaz ve varsayılan olarak elenir.</dd>
            <dt>Kaldıraçlı ETF</dt><dd>Günlük 2 ya da 3 kat getiri hedefleyen fonlar; uzun vadede değer kaybettirebilir ve varsayılan olarak elenir.</dd>
          </dl></section>
      </div>
      <div class="yigin">
        <section class="bolum" aria-labelledby="h-kisa"><h2 id="h-kisa">Klavye</h2>
          <dl class="sozluk"><dt><kbd>/</kbd></dt><dd>Sembol arama kutusuna gider.</dd>
            <dt><kbd>Sekme</kbd></dt><dd>Sayfanın başındaki "İçeriğe geç" bağlantısı menüyü atlar.</dd>
            <dt>Ok tuşları</dt><dd>Sonuç sekmeleri arasında geçiş yapar.</dd></dl></section>
        <section class="bolum" aria-labelledby="h-kaynak"><h2 id="h-kaynak">Veri ve sınırlar</h2>
          <ul class="liste"><li>Zirve listeleri ve temel veriler Finviz'den gelir; yaklaşık 15 dakika gecikmelidir.</li>
            <li>Fiyat geçmişi Yahoo Finance'ten haftalık olarak alınır.</li>
            <li>Model geçmiş fiyatlarla eğitilir; jeopolitik ya da emtia şoklarını önceden bilemez.</li>
            <li>Bu bir tarama aracıdır, yatırım tavsiyesi değildir.</li></ul></section>
        <section class="bolum" aria-labelledby="h-sorun"><h2 id="h-sorun">Sorun giderme</h2>
          <dl class="sozluk"><dt>Tarama hata verdi</dt><dd>Finviz çok sık istekte geçici olarak engelleyebilir. Birkaç dakika bekleyip yeniden deneyin.</dd>
            <dt>Teknik model yok uyarısı</dt><dd>Analiz sayfasından modeli bir kez oluşturun.</dd>
            <dt>Sayfa açılmıyor</dt><dd>Baslat.bat penceresinin açık olduğundan emin olun ve tarayıcıda http://127.0.0.1:8790 adresini açın.</dd></dl></section>
      </div>
    </div>`);
  return "Yardım";
}

route();
poll();
