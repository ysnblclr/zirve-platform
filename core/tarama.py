"""Tarama hattı: Finviz'den zirve listesi → Yahoo teknik profil → puan → veritabanı → uyarılar."""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from . import db
from .ath import batch_verify_ath
from .finviz import ETF_COLUMNS, STOCK_COLUMNS, FinvizClient, num
from .paths import ANALYSIS_FILE, UNIVERSE_FILE
from .puanlama import score_etfs, score_stocks
from .teknik import clean, contributions, features_at, fetch_prices, predict, session, transform

Log = Callable[..., None]   # log(mesaj, oran=None)

SECTORS = ["basicmaterials", "communicationservices", "consumercyclical", "consumerdefensive", "energy",
           "financial", "healthcare", "industrials", "realestate", "technology", "utilities"]
MARKET_TICKERS = ["SPY", "QQQ", "IWM", "DIA"]


def _noop(msg: str, frac: float | None = None) -> None:
    print(msg, flush=True)


# ----------------------------------------------------------------------------- sorgular
def stock_queries(mode: str, small: bool) -> list[tuple[str, str]]:
    liq = "sh_avgvol_o100,sh_price_o2,cap_microover" if small else "sh_avgvol_o200,sh_price_o5,cap_smallover"
    q = [("Tüm zamanların zirvesi", "ind_stocksonly,ta_alltime_nh"),
         ("52 haftalık yeni zirve", f"ind_stocksonly,ta_highlow52w_nh,{liq}")]
    if mode == "genis":
        q.append(("52 haftalık zirveye %5 yakın", f"ind_stocksonly,ta_highlow52w_b0to5h,{liq}"))
    return q


def etf_queries(mode: str) -> list[tuple[str, str]]:
    q = [("ETF tüm zamanların zirvesi", "ind_exchangetradedfund,ta_alltime_nh,sh_avgvol_o50"),
         ("ETF 52 haftalık zirve", "ind_exchangetradedfund,ta_highlow52w_nh,sh_avgvol_o50")]
    if mode == "genis":
        q.append(("ETF zirveye %5 yakın", "ind_exchangetradedfund,ta_highlow52w_b0to5h,sh_avgvol_o100"))
    return q


def fetch(client: FinvizClient, queries, columns) -> list[dict]:
    """Sorguları çalıştırır; 1000 satırı aşan sorguyu sektörlere böler; sembole göre tekilleştirir."""
    seen: dict[str, dict] = {}
    for label, f in queries:
        rows = client.screener(f, columns, order="-marketcap", label=label, max_rows=1000)
        if len(rows) >= 1000:
            rows = []
            for sec in SECTORS:
                rows += client.screener(f"{f},sec_{sec}", columns, order="-marketcap", label=f"{label} / {sec}")
        for r in rows:
            seen.setdefault(r["Ticker"], r)
    return list(seen.values())


# ----------------------------------------------------------------------------- teknik profil
def last_complete_week(p: dict, today: dt.date) -> int:
    """Pazartesi–Perşembe içinde bulunulan hafta eksiktir; bir önceki hafta kullanılır."""
    n = len(p["ts"])
    last = dt.datetime.fromtimestamp(p["ts"][-1], dt.timezone.utc).date()
    same_week = last - dt.timedelta(days=last.weekday()) == today - dt.timedelta(days=today.weekday())
    return n - 2 if (same_week and today.weekday() < 4 and n >= 54) else n - 1


def compute_tech(tickers: list[str], model: dict | None, today: dt.date, log: Log = _noop) -> dict[str, dict]:
    sess = session()
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fetch_prices, t, 0.5, sess): t for t in tickers}
        for k, fut in enumerate(as_completed(futs), 1):
            t = futs[fut]
            p = clean(fut.result(), 60)
            if k % 50 == 0 or k == len(tickers):
                log(f"Fiyat geçmişi: {k}/{len(tickers)}", 0.45 + 0.35 * k / max(1, len(tickers)))
            if not p:
                continue
            f = features_at(p, last_complete_week(p, today), None)
            rec = {"ozellik": f, "p_up": None, "p_down": None, "katki": []}
            if model:
                x = transform(f)
                rec.update(p_up=predict(model["yukselis"], x), p_down=predict(model["dusus"], x),
                           katki=contributions(model["yukselis"], x))
            out[t] = rec
    return out


def load_model() -> dict | None:
    if not ANALYSIS_FILE.exists():
        return None
    return json.loads(ANALYSIS_FILE.read_text(encoding="utf-8")).get("model")


def industry_sizes() -> dict[str, int]:
    sizes: dict[str, int] = defaultdict(int)
    if UNIVERSE_FILE.exists():
        for u in json.loads(UNIVERSE_FILE.read_text(encoding="utf-8")):
            sizes[u.get("industry")] += 1
    return sizes


def group_table(stocks: list[dict], industries: dict) -> list[dict]:
    by = defaultdict(list)
    for s in stocks:
        by[s["endustri"]].append(s["sembol"])
    out = []
    for ind, syms in by.items():
        p = industries.get(ind, {})
        out.append({"endustri": ind, "adet": len(syms), "semboller": syms,
                    "q": p.get("Perf Quart"), "h": p.get("Perf Half"), "y": p.get("Perf Year")})
    out.sort(key=lambda g: (g["adet"], g["h"] or -999), reverse=True)
    return out


# ----------------------------------------------------------------------------- ana akış
def run_scan(options: dict, trigger: str = "elle", log: Log = _noop) -> int:
    """Taramayı çalıştırır, sonuçları veritabanına yazar ve tarama kimliğini döner."""
    settings = db.get_settings()
    opts = {**settings["tarama"], **(options or {})}
    scan_id = db.create_scan(opts, trigger)
    try:
        client = FinvizClient(log=log)
        now = dt.datetime.now()
        log("Finviz'den zirve listeleri çekiliyor...", 0.02)
        stock_rows = [] if opts.get("sadece_etf") else fetch(client, stock_queries(opts["mod"], opts["kucuk"]),
                                                             STOCK_COLUMNS)
        log(f"{len(stock_rows)} hisse bulundu. ETF listeleri çekiliyor...", 0.25)
        etf_rows = [] if opts.get("sadece_hisse") else fetch(client, etf_queries(opts["mod"]), ETF_COLUMNS)
        log(f"{len(etf_rows)} ETF bulundu. Endüstri performansları çekiliyor...", 0.4)
        industries = client.industries()

        model = load_model()
        if not model:
            log("Uyarı: model yok; teknik bileşen için basit göreceli güç kullanılacak (Analiz sayfasından oluşturun).")
        tickers = [r["Ticker"] for r in stock_rows + etf_rows]
        log(f"{len(tickers)} aday için haftalık fiyat geçmişi okunuyor...", 0.45)
        tech = compute_tech(tickers, model, now.date(), log)

        log("Tüm adaylar için Gerçek All-Time High (ATH) geçmişi doğrulanıyor...", 0.72)
        cur_prices = {r["Ticker"]: num(r.get("Price")) for r in stock_rows + etf_rows if num(r.get("Price"))}
        ath_map = batch_verify_ath(tickers, cur_prices)

        stocks = score_stocks(stock_rows, industries, tech, now.date(), industry_sizes(), settings.get("agirlik"), ath_map=ath_map)
        etfs = score_etfs(etf_rows, tech, opts.get("tavanli", False), opts.get("kaldiracli", False),
                          settings.get("etf_agirlik"), ath_map=ath_map)

        if opts.get("sadece_gercek_ath"):
            stocks = [s for s in stocks if s.get("is_true_ath")]
            etfs = [e for e in etfs if e.get("is_true_ath")]

        n_news = int(opts.get("haber") or 0)
        if n_news:
            log(f"İlk {n_news} hisse ve ilk 5 ETF için haberler çekiliyor...", 0.82)
            for it in stocks[:n_news] + etfs[:min(5, n_news)]:
                try:
                    it["haberler"] = client.news(it["sembol"], 5)
                except Exception as exc:  # haber alınamasa da tarama sürer
                    log(f"{it['sembol']} haberleri alınamadı: {exc}")
        spy = current_prices(client, ["SPY"]).get("SPY")
        db.insert_results(scan_id, stocks + etfs)
        db.finish_scan(scan_id, "tamam", len(stocks), len(etfs), spy, group_table(stocks, industries))
        make_alerts(scan_id, stocks, settings)
        log(f"Tamamlandı: {len(stocks)} hisse, {len(etfs)} ETF puanlandı.", 1.0)
        return scan_id
    except Exception as exc:
        db.finish_scan(scan_id, "hata", error=f"{exc.__class__.__name__}: {exc}")
        raise


def make_alerts(scan_id: int, stocks: list[dict], settings: dict) -> None:
    cfg = settings["uyari"]
    esik = float(cfg.get("esik", 70))
    watched = db.watched()
    prev = db.previous_scan_id(scan_id)
    prev_top = {r["sembol"] for r in db.get_results(prev, "Hisse", 10)} if prev else None
    for i, it in enumerate(stocks, 1):
        sym = it["sembol"]
        if cfg.get("izleme", True) and sym in watched and it["puan"] >= esik:
            db.add_alert(scan_id, sym, f"İzleme listendeki {sym} puanı {it['puan']:.1f} (eşik {esik:.0f})")
        if cfg.get("yeni_ilk10", True) and prev_top is not None and i <= 10 and sym not in prev_top:
            db.add_alert(scan_id, sym, f"{sym} ilk 10'a girdi: {i}. sıra, puan {it['puan']:.1f}")


# ----------------------------------------------------------------------------- fiyatlar (önbellekli)
_price_cache: dict[str, tuple[float, dict]] = {}
_price_lock = threading.Lock()


def current_prices(client: FinvizClient | None, tickers: list[str], max_age: float = 600) -> dict[str, float | None]:
    """Finviz'den güncel fiyatlar (10 dakikalık önbellek)."""
    now = time.time()
    out, missing = {}, []
    with _price_lock:
        for t in tickers:
            hit = _price_cache.get(t)
            if hit and now - hit[0] < max_age:
                out[t] = hit[1].get("Price")
            else:
                missing.append(t)
    if missing:
        rows = quotes(client, missing, [1, 2, 65])
        with _price_lock:
            for t, r in rows.items():
                _price_cache[t] = (now, {"Price": num(r.get("Price"))})
                out[t] = num(r.get("Price"))
    return out


def quotes(client: FinvizClient | None, tickers: list[str], columns: list[int]) -> dict[str, dict]:
    client = client or FinvizClient(verbose=False)
    out = {}
    for i in range(0, len(tickers), 100):
        for r in client.screener("", columns, tickers=",".join(tickers[i:i + 100]), label="fiyat"):
            out[r["Ticker"]] = r
    return out


_market_cache: tuple[float, list] | None = None


def market_snapshot() -> list[dict]:
    """Ana endeks ETF'lerinin günlük değişimi ve zirveye uzaklığı (10 dakikalık önbellek)."""
    global _market_cache
    if _market_cache and time.time() - _market_cache[0] < 600:
        return _market_cache[1]
    rows = quotes(FinvizClient(verbose=False), MARKET_TICKERS, [1, 2, 42, 43, 47, 57, 125, 65, 66])
    out = []
    for t in MARKET_TICKERS:
        r = rows.get(t)
        if r:
            out.append({"sembol": t, "ad": r.get("Company"), "fiyat": num(r.get("Price")),
                        "degisim": num(r.get("Change %")), "hafta": num(r.get("Perf Week")),
                        "yb": num(r.get("Perf YTD")), "zirveye": num(r.get("52W High")),
                        "tum_zaman": num(r.get("All-Time High"))})
    _market_cache = (time.time(), out)
    return out
