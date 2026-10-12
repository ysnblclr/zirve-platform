"""Geriye dönük analiz: 52 haftalık zirve yapan hisseler sonraki 12 ayda ne yaptı?

Evren : Finviz'de bugün listelenen likit ABD hisseleri (piyasa değeri > 300 M $,
        ort. hacim > 200 bin, fiyat > 5 $).
Veri  : Yahoo Finance 5 yıllık haftalık fiyatlar (cache/yahoo altında önbelleğe alınır).
Olay  : Her 4 haftada bir, o hafta 52 haftalık yeni zirve yapan hisse.
Sonuç : Sonraki 52 haftalık getiri; +%50 / +%100 üstü ve -%30 altı oranları.
Model : Yeni zirve olaylarında "12 ayda ≥ +%50" ve "≤ -%30" olasılıkları için lojistik
        regresyon. Eski tarihlerle eğitilir, son tarihlerde test edilir.

Not: Evren bugün hâlâ işlem gören hisselerden oluştuğu için hayatta kalma yanlılığı
vardır; mutlak oranlar olduğundan iyi görünür. Asıl bilgi grupların birbirine göre farkıdır.

Kullanım: platformdaki "Analiz" sayfası ya da komut satırından:
          python -m core.analiz            (önbellekteki veriyi kullanır)
          python -m core.analiz --yenile   (evreni ve fiyatları yeniden indirir)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .finviz import FinvizClient, num
from .paths import ANALYSIS_FILE as RESULT_FILE
from .paths import UNIVERSE_FILE
from .teknik import FEATURES, MIN_WEEKS, clean, features_at, fetch_prices, fit_logistic, is_new_high, predict, \
    session, transform

Log = Callable[..., None]   # log(mesaj, oran=None)


def _print_log(msg: str, frac: float | None = None) -> None:
    print(msg, flush=True)


UNIVERSE_FILTER = "ind_stocksonly,cap_smallover,sh_avgvol_o200,sh_price_o5"
SECTORS = ["basicmaterials", "communicationservices", "consumercyclical", "consumerdefensive", "energy",
           "financial", "healthcare", "industrials", "realestate", "technology", "utilities"]
STEP = 4          # olay örnekleme aralığı (hafta)
HORIZON = 52      # ileri getiri ufku (hafta)
UP, DOWN = 0.5, -0.3


# ----------------------------------------------------------------------------- veri
def load_universe(refresh: bool, log: Log = _print_log) -> list[dict]:
    if UNIVERSE_FILE.exists() and not refresh and time.time() - UNIVERSE_FILE.stat().st_mtime < 30 * 86400:
        return json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    log("Evren Finviz'den indiriliyor (yaklaşık 3 dakika)...", 0.02)
    # Ücretsiz sürüm bir sorguda en fazla 1000 satır verir; evren sektörlere bölünür.
    client = FinvizClient(log=log)
    rows = []
    for k, sec in enumerate(SECTORS):
        rows += client.screener(f"{UNIVERSE_FILTER},sec_{sec}", [1, 3, 4, 6], order="ticker", label=sec)
        log(f"Evren: {sec} tamam", 0.02 + 0.13 * (k + 1) / len(SECTORS))
    uni = [{"t": r["Ticker"], "sector": r.get("Sector"), "industry": r.get("Industry"),
            "cap": num(r.get("Market Cap"))} for r in rows]
    UNIVERSE_FILE.write_text(json.dumps(uni), encoding="utf-8")
    return uni


def load_prices(universe: list[dict], refresh: bool, workers: int, log: Log = _print_log) -> dict[str, dict]:
    sess = session()
    prices: dict[str, dict] = {}
    max_age = 0 if refresh else 7
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_prices, u["t"], max_age, sess): u["t"] for u in universe}
        for k, fut in enumerate(as_completed(futs), 1):
            p = clean(fut.result(), HORIZON + MIN_WEEKS + 10)
            if p:
                prices[futs[fut]] = p
            if k % 250 == 0 or k == len(universe):
                log(f"Fiyat geçmişi: {k}/{len(universe)}", 0.15 + 0.6 * k / len(universe))
    return prices


# ----------------------------------------------------------------------------- olaylar
def week_key(ts: int) -> str:
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def build_events(universe: list[dict], prices: dict[str, dict]) -> list[dict]:
    industry = {u["t"]: u.get("industry") for u in universe}
    # Endüstri genişliği: her hafta, endüstrideki hisselerin kaçta kaçı yeni zirvede
    num_, den_ = defaultdict(int), defaultdict(int)
    for t, p in prices.items():
        ind = industry.get(t)
        for i in range(52, len(p["h"])):
            key = (ind, week_key(p["ts"][i]))
            den_[key] += 1
            num_[key] += is_new_high(p, i)

    events = []
    for t, p in prices.items():
        ind = industry.get(t)
        a, h, c = p["a"], p["h"], p["c"]
        for i in range(MIN_WEEKS, len(c) - HORIZON, STEP):
            wk = week_key(p["ts"][i])
            ev = {
                "t": t, "wk": wk,
                "new_high": is_new_high(p, i),
                "near_high": c[i] >= 0.95 * max(h[i - 52:i + 1]),
                "fwd": a[i + HORIZON] / a[i] - 1,
            }
            if ev["new_high"]:
                den = den_.get((ind, wk), 0)
                breadth = num_[(ind, wk)] / den if den >= 5 else None
                ev.update(features_at(p, i, breadth))
                prev = sum(is_new_high(p, j) for j in range(i - 12, i))
                ev["fresh"] = prev == 0
            events.append(ev)
    return events


# ----------------------------------------------------------------------------- istatistik
def stats(evs: list[dict]) -> dict:
    if not evs:
        return {"n": 0}
    f = sorted(e["fwd"] for e in evs)
    n = len(f)
    return {
        "n": n,
        "medyan": statistics.median(f),
        "p50": sum(x >= UP for x in f) / n,
        "p100": sum(x >= 1.0 for x in f) / n,
        "kayip30": sum(x <= DOWN for x in f) / n,
    }


def buckets(evs, key, edges, labels):
    return [{"grup": lab, **stats([e for e in evs if e.get(key) is not None and lo <= e[key] < hi])}
            for lo, hi, lab in zip(edges[:-1], edges[1:], labels)]


def quintiles(evs, key, fmt):
    vals = sorted(e[key] for e in evs if e.get(key) is not None)
    if len(vals) < 50:
        return []
    cuts = [vals[int(len(vals) * q / 5)] for q in range(1, 5)]
    edges = [-math.inf] + cuts + [math.inf]
    labels = [f"{k + 1}. dilim (" + (f"{fmt(edges[1])} altı" if k == 0 else f"{fmt(edges[4])} üstü" if k == 4
                                      else f"{fmt(edges[k])} ile {fmt(edges[k + 1])} arası") + ")"
              for k in range(5)]
    return buckets(evs, key, edges, labels)


def pct(x: float) -> str:
    return f"%{x * 100:.0f}"


def breakdowns(nh: list[dict]) -> dict:
    return {
        "6 aylık momentum (beşte birlik dilimler)": quintiles(nh, "mom26", pct),
        "Hacim artışı (son 4 hafta / 1 yıl)": buckets(
            nh, "vol_surge", [0, 0.8, 1.2, 2.0, 999], ["< 0,8x", "0,8 ile 1,2x arası", "1,2 ile 2x arası", "> 2x"]),
        "Yıllık oynaklık (beşte birlik dilimler)": quintiles(nh, "volatility", pct),
        "52 haftalık dipten uzaklık": buckets(
            nh, "from_low", [0, 0.3, 0.6, 1.0, 2.0, 999], ["< %30", "%30 ile 60 arası", "%60 ile 100 arası", "%100 ile 200 arası", "> %200"]),
        "50 günlük ortalamaya uzaklık": buckets(
            nh, "ext10", [-1, 0.05, 0.10, 0.20, 0.30, 99], ["< %5", "%5 ile 10 arası", "%10 ile 20 arası", "%20 ile 30 arası", "> %30"]),
        "Endüstri genişliği (aynı hafta zirvedeki endüstri payı)": buckets(
            nh, "breadth", [0, 0.10, 0.25, 0.50, 1.01], ["< %10", "%10 ile 25 arası", "%25 ile 50 arası", "> %50"]),
        "Çok yıllık zirve (5 yıllık veride en yüksek)": [
            {"grup": "5 yılın zirvesi", **stats([e for e in nh if e["multi_year"]])},
            {"grup": "Sadece 52 haftanın zirvesi", **stats([e for e in nh if not e["multi_year"]])}],
        "Taze kırılım (önceki 12 haftada zirve yok)": [
            {"grup": "Taze kırılım", **stats([e for e in nh if e["fresh"]])},
            {"grup": "Zaten zirvelerde", **stats([e for e in nh if not e["fresh"]])}],
    }


def train_models(nh: list[dict]) -> dict:
    """Zaman bölmeli eğitim/test; sonra tüm veriyle son model."""
    weeks = sorted({e["wk"] for e in nh})
    cut = weeks[int(len(weeks) * 0.6)]
    train = [e for e in nh if e["wk"] < cut]
    test = [e for e in nh if e["wk"] >= cut]
    X = lambda evs: [transform(e) for e in evs]  # noqa: E731
    up = lambda evs: [int(e["fwd"] >= UP) for e in evs]  # noqa: E731
    down = lambda evs: [int(e["fwd"] <= DOWN) for e in evs]  # noqa: E731

    m_up = fit_logistic(X(train), up(train))
    m_down = fit_logistic(X(train), down(train))
    scored = sorted(((predict(m_up, transform(e)), e) for e in test), key=lambda t: t[0])
    k = len(scored)
    test_q = []
    for q in range(5):
        part = [e for _, e in scored[int(k * q / 5):int(k * (q + 1) / 5)]]
        probs = [p for p, _ in scored[int(k * q / 5):int(k * (q + 1) / 5)]]
        test_q.append({"grup": f"Model dilimi {q + 1} (tahmin %{min(probs) * 100:.0f} ile %{max(probs) * 100:.0f} arası)",
                       **stats(part)})
    final_up = fit_logistic(X(nh), up(nh))
    final_down = fit_logistic(X(nh), down(nh))
    return {
        "ozellikler": FEATURES,
        "yukselis": final_up, "dusus": final_down,
        "egitim_bitis": cut, "egitim_n": len(train), "test_n": len(test),
        "test_dilimleri": test_q,
        "taban_p50": sum(up(nh)) / len(nh), "taban_kayip30": sum(down(nh)) / len(nh),
    }


def print_summary(res: dict) -> None:
    def line(lab, s):
        if not s.get("n"):
            return f"  {lab:<46} (veri yok)"
        return (f"  {lab:<46} n={s['n']:>6}  medyan={pct(s['medyan']):>5}  "
                f"≥+%50={pct(s['p50']):>4}  ≥+%100={pct(s['p100']):>4}  ≤-%30={pct(s['kayip30']):>4}")
    print(f"\nEvren: {res['hisse_sayisi']} hisse · ufuk 52 hafta")
    for lab, key in [("Tüm olaylar (taban)", "taban_tum_olaylar"), ("Zirveye %5 yakın", "zirveye_yakin_5"),
                     ("Yeni 52 haftalık zirve", "yeni_52h_zirve"), ("Zirveden uzak", "zirvede_degil")]:
        print(line(lab, res[key]))
    for name, rows in res["kirilimlar"].items():
        print(f"\n{name}: yeni zirve olayları")
        for r in rows:
            print(line(r["grup"], r))
    m = res["model"]
    print(f"\nModel testi (eğitim < {m['egitim_bitis']}, test n={m['test_n']}). Tahmin dilimine göre GERÇEKLEŞEN:")
    for r in m["test_dilimleri"]:
        print(line(r["grup"], r))
    print("\nKatsayılar (standart sapma başına, + = olasılığı artırır):")
    for name, cu, cd in zip(m["ozellikler"], m["yukselis"]["coef"], m["dusus"]["coef"]):
        print(f"  {name:<12} ≥+%50: {cu:+.2f}   ≤-%30: {cd:+.2f}")


def run(refresh: bool = False, workers: int = 6, log: Log = _print_log) -> dict:
    """Analizin tamamı: evren → fiyatlar → olaylar → istatistik ve model. Sonucu dosyaya yazar."""
    universe = load_universe(refresh, log)
    log(f"Evren: {len(universe)} hisse. Fiyat geçmişleri okunuyor (ilk sefer ~5 dakika)...", 0.15)
    prices = load_prices(universe, refresh, workers, log)
    log(f"Kullanılabilir fiyat serisi: {len(prices)}. Olaylar çıkarılıyor...", 0.78)
    events = build_events(universe, prices)
    nh = [e for e in events if e["new_high"]]
    log(f"{len(events)} olay, {len(nh)} yeni zirve. Model eğitiliyor...", 0.85)
    res = {
        "tarih": dt.date.today().isoformat(),
        "hisse_sayisi": len(prices),
        "taban_tum_olaylar": stats(events),
        "zirveye_yakin_5": stats([e for e in events if e["near_high"]]),
        "yeni_52h_zirve": stats(nh),
        "zirvede_degil": stats([e for e in events if not e["near_high"]]),
        "kirilimlar": breakdowns(nh),
        "model": train_models(nh),
    }
    RESULT_FILE.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("Analiz tamamlandı ve model kaydedildi.", 1.0)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yenile", action="store_true", help="evreni ve fiyatları yeniden indir")
    ap.add_argument("--is-parcacigi", type=int, default=6, help="eşzamanlı indirme sayısı")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = run(args.yenile, args.is_parcacigi)
    print_summary(res)
    print(f"\nSonuç kaydedildi: {RESULT_FILE}")


if __name__ == "__main__":
    main()
