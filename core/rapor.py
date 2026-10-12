"""Tarama sonuçlarından tek dosyalık (çevrimdışı açılan) HTML rapor ve CSV üretir."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .puanlama import AGIRLIK, ETF_AGIRLIK

ALT_PUAN_AD = {
    "teknik": "Teknik model", "momentum": "Momentum", "trend": "Trend", "buyume": "Büyüme",
    "kalite": "Kalite", "degerleme": "Değerleme", "sahiplik": "Kurum/analist",
    "grup": "Endüstri gücü", "fon_akisi": "Fon akışı", "tema": "Tema", "likidite": "Likidite",
    "maliyet": "Maliyet",
}


def _pct(x) -> str:
    return "" if x is None else f"{x * 100:.0f}".replace(".", ",")


def write_csv(items: list[dict], path: Path) -> None:
    if not items:
        return
    data_keys = list(items[0]["veri"].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Sıra", "Sembol", "Şirket", "Puan", "Model ≥+%50 olasılığı", "Model ≤-%30 olasılığı", "Risk",
                    "Etiketler", "Sektör", "Endüstri", "Bilanço", *data_keys, "Nedenler", "Riskler"])
        for i, it in enumerate(items, 1):
            w.writerow([i, it["sembol"], it["sirket"], str(it["puan"]).replace(".", ","), _pct(it["p_up"]),
                        _pct(it["p_down"]), it["risk"], ", ".join(it["etiketler"]), it["sektor"],
                        it["endustri"], it["bilanco"],
                        *[("" if it["veri"][k] is None else str(round(it["veri"][k], 2)).replace(".", ","))
                          for k in data_keys],
                        " | ".join(it["nedenler"]), " | ".join(it["riskler"])])


def write_html(path: Path, meta: dict, stocks: list[dict], etfs: list[dict],
               groups: list[dict], analysis: dict | None) -> None:
    payload = {
        "meta": meta, "stocks": stocks, "etfs": etfs, "groups": groups, "analysis": analysis,
        "weights": AGIRLIK, "etfWeights": ETF_AGIRLIK, "subNames": ALT_PUAN_AD,
    }
    data = json.dumps(payload, ensure_ascii=False, default=str).replace("</", "<\\/")
    page = TEMPLATE.replace("/*DATA*/", data).replace("{{TITLE}}", html.escape(meta.get("baslik", "Zirve Tarayıcı")))
    path.write_text(page, encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#2563eb;--good:#15803d;--bad:#b91c1c;--warn:#b45309;--chip:#eef2ff;--bar:#dbe4ff}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;--muted:#a3a29b;--line:#33332f;--accent:#7aa2ff;--good:#4ade80;--bad:#f87171;--warn:#fbbf24;--chip:#25304d;--bar:#2b3a63}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:20px 24px 8px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted)}
main{padding:0 24px 40px;max-width:1500px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:150px}
.card b{display:block;font-size:20px}
.tabs{display:flex;gap:6px;margin:8px 0 12px;flex-wrap:wrap}
.tabs button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 14px;border-radius:8px;cursor:pointer;font:inherit}
.tabs button.on{border-color:var(--accent);color:var(--accent);font-weight:600}
.tools{display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.tools input,.tools select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:var(--card);cursor:pointer;font-weight:600;color:var(--muted);font-size:12px;user-select:none}
th:hover{color:var(--ink)}
td.l,th.l{text-align:left}
tr.row{cursor:pointer}
tr.row:hover td{background:color-mix(in srgb,var(--accent) 6%,transparent)}
.pos{color:var(--good)}.neg{color:var(--bad)}
.score{display:flex;align-items:center;gap:6px;justify-content:flex-end}
.score i{display:inline-block;height:8px;border-radius:4px;background:var(--accent)}
.chip{display:inline-block;padding:1px 7px;border-radius:10px;background:var(--chip);font-size:11.5px;margin-right:3px}
.chip.warn{background:color-mix(in srgb,var(--warn) 18%,transparent)}
.detail td{background:color-mix(in srgb,var(--accent) 3%,transparent);white-space:normal;text-align:left}
.dgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;padding:6px 4px}
.dgrid h4{margin:0 0 6px;font-size:13px}
.dgrid ul{margin:0;padding-left:18px}
.sb{display:grid;grid-template-columns:110px 1fr 36px;gap:6px;align-items:center;font-size:12px;margin:3px 0}
.sb span.b{height:7px;background:var(--line);border-radius:4px;position:relative;overflow:hidden}
.sb span.b i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:4px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.note{color:var(--muted);font-size:12.5px;margin-top:10px}
section.hide{display:none}
.mt{margin-top:18px}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="sub" id="subtitle"></div>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="tabs" id="tabs"></div>
  <section id="sec-stocks"></section>
  <section id="sec-etfs" class="hide"></section>
  <section id="sec-groups" class="hide"></section>
  <section id="sec-method" class="hide"></section>
  <p class="note">Bu rapor Finviz verileriyle üretilmiş otomatik bir taramadır; yatırım tavsiyesi değildir.
  Puan, geçmişte büyük yükselişlerle ilişkili özelliklerin bir özetidir; gelecekteki getiriyi garanti etmez.</p>
</main>
<script>
const D = /*DATA*/;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtN = (v, d=0) => v==null ? "-" : v.toLocaleString("tr-TR",{maximumFractionDigits:d,minimumFractionDigits:d});
const fmtP = v => v==null ? "-" : `<span class="${v>=0?'pos':'neg'}">%${fmtN(v,0)}</span>`;
const fmtBig = v => v==null ? "-" : v>=1e12 ? fmtN(v/1e12,2)+" Tn $" : v>=1e9 ? fmtN(v/1e9,1)+" Mr $" : v>=1e6 ? fmtN(v/1e6,0)+" M $" : fmtN(v,0);
const fmtVol = v => v==null ? "-" : v>=1e6 ? fmtN(v/1e6,1)+" M" : fmtN(v/1e3,0)+" B";
const finviz = t => `https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}`;

$("#title").textContent = D.meta.baslik;
$("#subtitle").textContent = `${D.meta.zaman} · mod: ${D.meta.mod} · Finviz verisi ~15 dk gecikmeli`;
$("#cards").innerHTML = [
  ["Taranan hisse", D.meta.hisse_sayisi], ["Puanlanan ETF", D.meta.etf_sayisi],
  ["En kalabalık grup", D.groups.length ? `${esc(D.groups[0].endustri)} (${D.groups[0].adet})` : "-"],
  ["En yüksek puan", D.stocks.length ? `${esc(D.stocks[0].sembol)} · ${fmtN(D.stocks[0].puan,1)}` : "-"],
].map(([a,b]) => `<div class="card"><span class="sub">${a}</span><b>${b}</b></div>`).join("");

const TABS = [["stocks","Hisseler"],["etfs","ETF'ler"],["groups","Gruplar"],["method","Yöntem ve analiz"]];
$("#tabs").innerHTML = TABS.map(([k,l],i)=>`<button data-k="${k}" class="${i?'':'on'}">${l}</button>`).join("");
$("#tabs").onclick = e => { const k = e.target.dataset.k; if(!k) return;
  document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on", b.dataset.k===k));
  TABS.forEach(([t])=>$("#sec-"+t).classList.toggle("hide", t!==k)); };

function table(sec, items, cols, weights) {
  let sortKey = null, sortDir = -1, q = "", tag = "";
  const tags = [...new Set(items.flatMap(i=>i.etiketler))].sort();
  sec.innerHTML = `<div class="tools"><input placeholder="Sembol, şirket veya endüstri ara" size="34">
    <select><option value="">Tüm etiketler</option>${tags.map(t=>`<option>${esc(t)}</option>`).join("")}</select>
    <span class="sub">${items.length} sonuç · satıra tıklayınca nedenler, riskler ve haberler açılır</span></div>
    <div class="wrap"><table><thead></thead><tbody></tbody></table></div>`;
  const [inp, sel] = sec.querySelectorAll("input,select");
  inp.oninput = () => { q = inp.value.toLowerCase(); draw(); };
  sel.onchange = () => { tag = sel.value; draw(); };
  const head = sec.querySelector("thead"), body = sec.querySelector("tbody");
  head.innerHTML = "<tr>" + cols.map((c,i)=>`<th class="${c.l?'l':''}" data-i="${i}" title="${esc(c.tip||'')}">${c.h}</th>`).join("") + "</tr>";
  head.onclick = e => { const i = e.target.dataset.i; if(i==null) return;
    sortKey === i ? sortDir *= -1 : (sortKey = i, sortDir = -1); draw(); };
  function draw() {
    let rows = items.map((it, idx) => ({it, idx}))
      .filter(({it}) => (!q || (it.sembol+" "+it.sirket+" "+it.endustri+" "+it.sektor).toLowerCase().includes(q)) && (!tag || it.etiketler.includes(tag)));
    if (sortKey != null) { const c = cols[sortKey]; rows.sort((a,b)=>{ const x=c.v(a.it), y=c.v(b.it);
      if (x==null) return 1; if (y==null) return -1; return (x>y?1:x<y?-1:0)*sortDir; }); }
    body.innerHTML = rows.map(({it, idx}) => `<tr class="row" data-x="${idx}">${cols.map(c=>`<td class="${c.l?'l':''}">${c.f(it, idx)}</td>`).join("")}</tr>`).join("");
  }
  body.onclick = e => { const tr = e.target.closest("tr.row"); if(!tr || e.target.closest("a")) return;
    const nx = tr.nextElementSibling;
    if (nx && nx.classList.contains("detail")) { nx.remove(); return; }
    const it = items[+tr.dataset.x];
    const d = document.createElement("tr"); d.className = "detail";
    d.innerHTML = `<td colspan="${cols.length}">${detail(it, weights)}</td>`; tr.after(d); };
  draw();
}

function detail(it, weights) {
  const sb = Object.entries(weights).map(([k,w]) => { const v = it.alt_puan[k] ?? 0;
    return `<div class="sb"><span>${esc(D.subNames[k]||k)} (${w})</span><span class="b"><i style="width:${Math.round(v*100)}%"></i></span><span>${fmtN(v*w,1)}</span></div>`; }).join("");
  const news = (it.haberler||[]).map(n=>`<li><span class="sub">${esc(n.date)}</span> <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a> <span class="sub">${esc(n.source)}</span></li>`).join("");
  const facts = Object.entries(it.veri).map(([k,v]) => `<span class="chip">${esc(k)}: ${v==null?"-":/Değer|AUM/.test(k)?fmtBig(v):/Hacim$/.test(k)&&k.startsWith("Ort")?fmtVol(v):fmtN(v, Math.abs(v)<10?2:0)}</span>`).join(" ");
  const prob = it.p_up==null ? "" : `<p><b>Tarihsel benzer profil:</b> 12 ayda ≥ +%50 oranı ${probCell(it.p_up)}, ≤ −%30 oranı ${probCell(it.p_down)} <span class="sub">(hayatta kalma yanlılığı nedeniyle mutlak değerler iyimserdir; sıralama için kullanın)</span></p>`;
  return `${prob}<div class="dgrid">
    <div><h4>Neden yükselebilir?</h4><ul>${it.nedenler.map(x=>`<li>${esc(x)}</li>`).join("") || "<li class='sub'>Belirgin olumlu sinyal yok</li>"}</ul>
      <h4 class="mt">Riskler</h4><ul>${it.riskler.map(x=>`<li>${esc(x)}</li>`).join("") || "<li class='sub'>Belirgin risk işareti yok</li>"}</ul></div>
    <div><h4>Puan dağılımı</h4>${sb}</div>
    <div><h4>Son haberler</h4><ul>${news || "<li class='sub'>Haber çekilmedi (--haber ile artırılabilir)</li>"}</ul></div>
  </div><div style="padding:6px 4px">${facts}</div>`;
}

const scoreCell = it => `<div class="score"><i style="width:${Math.round(it.puan*0.6)}px"></i><b>${fmtN(it.puan,1)}</b></div>`;
const probCell = p => p==null ? "-" : "%"+fmtN(p*100,0);
const riskCell = it => `<span class="chip ${it.risk==='Yüksek'?'warn':''}" title="Benzer profilde 12 ayda −%30 ve altı oranı: ${probCell(it.p_down)}">${esc(it.risk)}</span>`;
const tagCell = it => it.etiketler.map(t=>`<span class="chip ${/Spekülatif|Döngüsel|Kaldıraçlı|Tavanlı/.test(t)?'warn':''}">${esc(t)}</span>`).join("");
const tick = it => `<a href="${finviz(it.sembol)}" target="_blank" rel="noopener"><b>${esc(it.sembol)}</b></a>`;

table($("#sec-stocks"), D.stocks, [
  {h:"#", v:it=>D.stocks.indexOf(it), f:(it)=>D.stocks.indexOf(it)+1},
  {h:"Puan", v:it=>it.puan, f:scoreCell},
  {h:"Sembol", l:1, v:it=>it.sembol, f:tick},
  {h:"≥+%50", v:it=>it.p_up, f:it=>probCell(it.p_up), tip:"Geçmişte benzer teknik profildeki yeni zirve hisselerinin 12 ayda %50+ yükselme oranı (model tahmini)"},
  {h:"Risk", v:it=>it.p_down, f:riskCell, tip:"Benzer profilde 12 ayda %30+ düşüş oranı: Düşük <%8, Orta %8 ile 15, Yüksek >%15"},
  {h:"Şirket", l:1, v:it=>it.sirket, f:it=>esc(it.sirket.slice(0,28))},
  {h:"Profil", l:1, v:it=>it.etiketler.join(), f:tagCell},
  {h:"Endüstri", l:1, v:it=>it.endustri, f:it=>esc(it.endustri)},
  {h:"Fiyat $", v:it=>it.veri["Fiyat"], f:it=>fmtN(it.veri["Fiyat"],2)},
  {h:"Piyasa değ.", v:it=>it.veri["Piyasa Değeri"], f:it=>fmtBig(it.veri["Piyasa Değeri"])},
  {h:"6 ay", v:it=>it.veri["6 Ay"], f:it=>fmtP(it.veri["6 Ay"])},
  {h:"1 yıl", v:it=>it.veri["1 Yıl"], f:it=>fmtP(it.veri["1 Yıl"])},
  {h:"Satış Ç/Ç", v:it=>it.veri["Satış Ç/Ç"], f:it=>fmtP(it.veri["Satış Ç/Ç"]), tip:"Son çeyrek satış büyümesi (yıllık bazda)"},
  {h:"EPS gel. yıl", v:it=>it.veri["EPS Gelecek Yıl"], f:it=>fmtP(it.veri["EPS Gelecek Yıl"]), tip:"Gelecek yıl hisse başı kâr büyüme beklentisi"},
  {h:"İleri F/K", v:it=>it.veri["İleri F/K"], f:it=>fmtN(it.veri["İleri F/K"],1)},
  {h:"RSI", v:it=>it.veri["RSI"], f:it=>fmtN(it.veri["RSI"],0)},
  {h:"Bilanço", v:it=>it.bilanco, f:it=>it.bilanco ? it.bilanco.split("-").reverse().join(".") : "-"},
], D.weights);

table($("#sec-etfs"), D.etfs, [
  {h:"#", v:it=>D.etfs.indexOf(it), f:it=>D.etfs.indexOf(it)+1},
  {h:"Puan", v:it=>it.puan, f:scoreCell},
  {h:"Sembol", l:1, v:it=>it.sembol, f:tick},
  {h:"Risk", v:it=>it.p_down, f:riskCell},
  {h:"Fon", l:1, v:it=>it.sirket, f:it=>esc(it.sirket.slice(0,34))},
  {h:"Profil", l:1, v:it=>it.etiketler.join(), f:tagCell},
  {h:"Kategori", l:1, v:it=>it.sektor, f:it=>esc(it.sektor)},
  {h:"Varlık", v:it=>it.veri["Varlık (AUM)"], f:it=>fmtBig(it.veri["Varlık (AUM)"])},
  {h:"3 ay", v:it=>it.veri["3 Ay"], f:it=>fmtP(it.veri["3 Ay"])},
  {h:"1 yıl", v:it=>it.veri["1 Yıl"], f:it=>fmtP(it.veri["1 Yıl"])},
  {h:"Akış 1 ay", v:it=>it.veri["Akış 1A %"], f:it=>fmtP(it.veri["Akış 1A %"]), tip:"Son 1 aydaki net fon girişinin varlığa oranı"},
  {h:"Akış 3 ay", v:it=>it.veri["Akış 3A %"], f:it=>fmtP(it.veri["Akış 3A %"])},
  {h:"Gider", v:it=>it.veri["Gider %"], f:it=>it.veri["Gider %"]==null?"-":"%"+fmtN(it.veri["Gider %"],2)},
  {h:"RSI", v:it=>it.veri["RSI"], f:it=>fmtN(it.veri["RSI"],0)},
], D.etfWeights);

$("#sec-groups").innerHTML = `<div class="wrap"><table><thead><tr><th class="l">Endüstri</th><th>Zirvedeki hisse</th><th>Grubun 3 ay</th><th>6 ay</th><th>1 yıl</th><th class="l">Hisseler</th></tr></thead><tbody>${
  D.groups.map(g=>`<tr><td class="l">${esc(g.endustri)}</td><td>${g.adet}</td><td>${fmtP(g.q)}</td><td>${fmtP(g.h)}</td><td>${fmtP(g.y)}</td><td class="l">${g.semboller.map(s=>`<a href="${finviz(s)}" target="_blank" rel="noopener">${esc(s)}</a>`).join(", ")}</td></tr>`).join("")
}</tbody></table></div><p class="note">Aynı endüstriden çok sayıda hissenin aynı anda zirve yapması grup/tema hareketine işaret eder (BWET ve tankerlerdeki gibi).</p>`;

function methodHtml() {
  const w = Object.entries(D.weights).map(([k,v])=>`<li>${esc(D.subNames[k])}: <b>${v}</b></li>`).join("");
  const we = Object.entries(D.etfWeights).map(([k,v])=>`<li>${esc(D.subNames[k])}: <b>${v}</b></li>`).join("");
  let a = "<p class='sub'>Geriye dönük analiz henüz çalıştırılmadı: <code>python analiz.py</code></p>";
  const A = D.analysis;
  if (A) {
    const row = (lab, s) => s && s.n ? `<tr><td class="l">${esc(lab)}</td><td>${fmtN(s.n)}</td><td>%${fmtN(s.medyan*100)}</td><td>%${fmtN(s.p50*100)}</td><td>%${fmtN(s.p100*100)}</td><td>%${fmtN(s.kayip30*100)}</td></tr>` : "";
    const head = `<thead><tr><th class="l">Grup</th><th>Olay</th><th>Medyan 12 ay getiri</th><th>≥ +%50 olasılığı</th><th>≥ +%100</th><th>≤ −%30</th></tr></thead>`;
    a = `<p>${A.tarih} tarihli analiz · ${fmtN(A.hisse_sayisi)} hisse · 5 yıllık haftalık veri · her 4 haftada bir örnekleme.</p>
      <div class="wrap"><table>${head}<tbody>${row("Tüm hisse-tarihler (taban)", A.taban_tum_olaylar)}${row("52 haftalık yeni zirve", A.yeni_52h_zirve)}${row("Zirveye %5 yakın", A.zirveye_yakin_5)}${row("Zirveden uzak", A.zirvede_degil)}</tbody></table></div>` +
      (A.model ? `<h4 class="mt">Model doğrulaması <span class="sub">(${esc(A.model.egitim_bitis)} öncesiyle eğitildi, sonrasında test edildi; test n=${fmtN(A.model.test_n)})</span></h4>
        <div class="wrap"><table>${head}<tbody>${A.model.test_dilimleri.map(r=>row(r.grup, r)).join("")}</tbody></table></div>
        <p class="note">Model girdileri: ${A.model.ozellikler.map((f,i)=>`${esc(f)} (yükseliş ${A.model.yukselis.coef[i]>=0?"+":""}${fmtN(A.model.yukselis.coef[i],2)}, düşüş ${A.model.dusus.coef[i]>=0?"+":""}${fmtN(A.model.dusus.coef[i],2)})`).join(" · ")}. Katsayılar standart sapma başınadır.</p>` : "") +
      Object.entries(A.kirilimlar).map(([name, rows]) => `<h4 class="mt">${esc(name)} <span class="sub">(yalnızca yeni zirve olayları)</span></h4><div class="wrap"><table>${head}<tbody>${rows.map(r=>row(r.grup, r)).join("")}</tbody></table></div>`).join("") +
      `<p class="note">Evren bugün işlem gören hisselerden oluştuğu için hayatta kalma yanlılığı vardır; mutlak oranlar olduğundan yüksek görünür. Gruplar arası farklar daha anlamlıdır.</p>`;
  }
  return `<div class="dgrid"><div><h4>Hisse puanı ağırlıkları (toplam 100)</h4><ul>${w}</ul>
    <p class="note">Teknik model bileşeni, aşağıdaki geriye dönük testte eğitilen lojistik modelin ≥ +%50 olasılığıdır (%10 → 0 puan, %40 → tam puan). Cezalar: RSI ≥ 85, bir ayda %100+ yükseliş, F/S ≥ 50, kurumsal sahiplik < %5, düşük hacim. Bonus: %10 ile %35 arası açığa satış.</p></div>
    <div><h4>ETF puanı ağırlıkları (toplam 100)</h4><ul>${we}</ul>
    <p class="note">Tampon/gelir/tahvil ETF'leri ve kaldıraçlı ETF'ler varsayılan olarak elenir (<code>--tavanli</code>, <code>--kaldiracli</code> ile dahil edilir).</p></div></div>
    <h3 class="mt">Geriye dönük analiz</h3>${a}`;
}
$("#sec-method").innerHTML = methodHtml();
</script>
</body>
</html>
"""
