"""Zirve Platformu web API'si. Arayüz (web/) aynı sunucudan servis edilir."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from core import db, performans, tarama
from core import tokens as design_tokens
from core.ath import verify_ath
from core.finviz import STOCK_COLUMNS, ETF_COLUMNS, FinvizClient, num
from core.isler import Scheduler, jobs
from core.paths import ANALYSIS_FILE, WEB
from core.puanlama import AGIRLIK, ETF_AGIRLIK, score_etfs, score_stocks
from core.rapor import write_csv, write_html
from core.teknik import clean, fetch_prices, session

TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    Scheduler().start()
    yield


app = FastAPI(title="Zirve Platformu", lifespan=lifespan)


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    sifre = os.environ.get("ZIRVE_SIFRE")
    if not sifre:
        return await call_next(request)
    kullanici = os.environ.get("ZIRVE_KULLANICI", "admin")
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return Response("Giris yapilmadi", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Zirve Platformu"'})
    try:
        encoded = auth_header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        u, p = decoded.split(":", 1)
        if u != kullanici or p != sifre:
            return Response("Hatali kullanici adi veya sifre", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Zirve Platformu"'})
    except Exception:
        return Response("Gecersiz kimlik bilgisi", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Zirve Platformu"'})
    return await call_next(request)


def _ticker(t: str) -> str:
    t = t.strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(400, "Geçersiz sembol")
    return t


def _analysis() -> dict | None:
    return json.loads(ANALYSIS_FILE.read_text(encoding="utf-8")) if ANALYSIS_FILE.exists() else None


# ============================================================================ durum
@app.get("/api/durum")
def durum():
    a = _analysis()
    last = db.latest_scan_id()
    scan = db.get_scan(last) if last else None
    return {
        "is": jobs.status(),
        "son_tarama": scan and {k: scan[k] for k in ("id", "started_at", "finished_at", "n_stocks", "n_etfs", "trigger")},
        "model": {"tarih": a["tarih"], "hisse_sayisi": a["hisse_sayisi"]} if a and a.get("model") else None,
        "okunmamis_uyari": db.unseen_alerts(),
        "zamanlama": db.get_settings()["zamanlama"],
    }


@app.get("/api/is")
def is_durumu():
    return jobs.status() or {}


@app.get("/api/piyasa")
def piyasa():
    try:
        return tarama.market_snapshot()
    except Exception as exc:
        raise HTTPException(502, f"Piyasa verisi alınamadı: {exc}")


# ============================================================================ taramalar
@app.post("/api/tarama")
def tarama_baslat(secenek: dict = Body(default={})):
    allowed = {"mod", "kucuk", "kaldiracli", "tavanli", "haber", "sadece_hisse", "sadece_etf", "sadece_gercek_ath"}
    params = {k: v for k, v in secenek.items() if k in allowed}
    if params.get("mod") not in (None, "zirve", "genis"):
        raise HTTPException(400, "mod 'zirve' ya da 'genis' olmalı")
    try:
        return jobs.start("tarama", params)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/taramalar")
def taramalar():
    return db.list_scans(200)


def _scan_or_404(scan_id: int | str) -> dict:
    sid = db.latest_scan_id() if scan_id == "son" else int(scan_id)
    scan = db.get_scan(sid) if sid else None
    if not scan:
        raise HTTPException(404, "Tarama bulunamadı")
    return scan


@app.get("/api/taramalar/{scan_id}")
def tarama_detay(scan_id: str, true_ath_only: bool = False, arketip: str | None = None):
    scan = _scan_or_404(scan_id)
    results = db.get_results(scan["id"])
    watched = db.watched()
    for r in results:
        r["izleniyor"] = r["sembol"] in watched
    if true_ath_only:
        results = [r for r in results if r.get("is_true_ath")]
    if arketip:
        results = [r for r in results if r.get("arketip") == arketip]
    return {**scan, "hisseler": [r for r in results if r["tur"] == "Hisse"],
            "etfler": [r for r in results if r["tur"] == "ETF"]}


@app.delete("/api/taramalar/{scan_id}")
def tarama_sil(scan_id: int):
    _scan_or_404(scan_id)
    db.delete_scan(scan_id)
    return {"ok": True}


@app.get("/api/taramalar/{scan_id}/csv")
def tarama_csv(scan_id: str, tur: str = "Hisse"):
    scan = _scan_or_404(scan_id)
    items = db.get_results(scan["id"], "ETF" if tur.upper() == "ETF" else "Hisse")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.csv"
        write_csv(items, p)
        data = p.read_bytes() if p.exists() else b""
    name = f"zirve_{scan['id']}_{'etf' if tur.upper() == 'ETF' else 'hisse'}.csv"
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/taramalar/{scan_id}/html", response_class=HTMLResponse)
def tarama_html(scan_id: str):
    scan = _scan_or_404(scan_id)
    meta = {"baslik": "Zirve Tarayıcı: 1 yıllık yükseliş potansiyeli", "zaman": scan["started_at"][:16],
            "mod": scan["options"].get("mod", "zirve"), "hisse_sayisi": scan["n_stocks"], "etf_sayisi": scan["n_etfs"]}
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "r.html"
        write_html(p, meta, db.get_results(scan["id"], "Hisse"), db.get_results(scan["id"], "ETF"),
                   scan["groups"], _analysis())
        html = p.read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="zirve_rapor_{scan["id"]}.html"'})


# ============================================================================ hisse
@app.get("/api/hisse/{ticker}")
def hisse(ticker: str):
    t = _ticker(ticker)
    ath_info = verify_ath(t)
    return {"sembol": t, "son": db.latest_result(t), "gecmis": db.ticker_history(t),
            "izleniyor": t in db.watched(), "ath": ath_info}


@app.get("/api/hisse/{ticker}/fiyat")
def hisse_fiyat(ticker: str):
    t = _ticker(ticker)
    p = clean(fetch_prices(t, 0.5, session()), 10)
    if not p:
        raise HTTPException(404, "Fiyat geçmişi bulunamadı")
    ath_info = verify_ath(t)
    ath_p = ath_info.get("ath_price")
    n = len(p["c"])
    start = max(0, n - 156)
    out = []
    for i in range(start, n):
        hi52 = max(p["h"][max(0, i - 52):i]) if i > 0 else p["h"][i]
        out.append({"t": dt.datetime.fromtimestamp(p["ts"][i], dt.timezone.utc).date().isoformat(),
                    "c": round(p["c"][i], 4), "h52": round(hi52, 4),
                    "ath": round(ath_p, 4) if ath_p else None, "v": p["v"][i]})
    return out


_news_cache: dict[str, tuple[float, list]] = {}


@app.get("/api/hisse/{ticker}/haber")
def hisse_haber(ticker: str):
    t = _ticker(ticker)
    hit = _news_cache.get(t)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        news = FinvizClient(verbose=False).news(t, 12)
    except Exception as exc:
        raise HTTPException(502, f"Haberler alınamadı: {exc}")
    _news_cache[t] = (time.time(), news)
    return news


_industries_cache: tuple[float, dict] | None = None
_adhoc_lock = threading.Lock()


@app.get("/api/hisse/{ticker}/puanla")
def hisse_puanla(ticker: str):
    """Zirve listesinde olmayan bir sembolü de anlık puanlar (kaydedilmez)."""
    global _industries_cache
    t = _ticker(ticker)
    with _adhoc_lock:
        client = FinvizClient(verbose=False)
        rows = client.screener("", STOCK_COLUMNS, tickers=t, label=t)
        if not rows:
            raise HTTPException(404, "Finviz'de bulunamadı")
        r = rows[0]
        if not _industries_cache or time.time() - _industries_cache[0] > 3600:
            _industries_cache = (time.time(), client.industries())
        industries = _industries_cache[1]
        tech = tarama.compute_tech([t], tarama.load_model(), dt.date.today(), lambda *a: None)
        settings = db.get_settings()
        price = num(r.get("Price"))
        ath_info = verify_ath(t, price)
        ath_map = {t: ath_info}
        if r.get("Industry") == "Exchange Traded Fund":
            erows = client.screener("", ETF_COLUMNS, tickers=t, label=t)
            items = score_etfs(erows, tech, True, True, settings.get("etf_agirlik"), ath_map=ath_map)
        else:
            items = score_stocks([r], industries, tech, dt.date.today(), tarama.industry_sizes(),
                                 settings.get("agirlik"), ath_map=ath_map)
    if not items:
        raise HTTPException(422, "Bu menkul puanlanamadı (veri yetersiz ya da SPAC)")
    return {**items[0], "anlik": True}



# ============================================================================ izleme listesi
@app.get("/api/izleme")
def izleme():
    return performans.watchlist_view()


@app.post("/api/izleme")
def izleme_ekle(veri: dict = Body(...)):
    t = _ticker(str(veri.get("sembol", "")))
    note = str(veri.get("not") or "")[:300]
    # "Geri al": silinen kaydı eski eklenme tarihi ve fiyatıyla geri yükle
    old_price, old_at = veri.get("fiyat"), veri.get("eklenme")
    if isinstance(old_price, (int, float)) and isinstance(old_at, str) \
            and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", old_at):
        db.watch_add(t, float(old_price), note, old_at)
        return {"ok": True, "fiyat": old_price}
    price = tarama.current_prices(None, [t]).get(t)
    if price is None:
        raise HTTPException(404, "Sembol Finviz'de bulunamadı")
    db.watch_add(t, price, note)
    return {"ok": True, "fiyat": price}


@app.delete("/api/izleme/{ticker}")
def izleme_sil(ticker: str):
    db.watch_remove(_ticker(ticker))
    return {"ok": True}


# ============================================================================ performans / analiz
@app.get("/api/performans")
def performans_(ilk: int = 10):
    return performans.followup(max(1, min(ilk, 40)))


@app.get("/api/analiz")
def analiz_():
    return _analysis() or {}


@app.post("/api/analiz")
def analiz_baslat(secenek: dict = Body(default={})):
    try:
        return jobs.start("analiz", {"yenile": bool(secenek.get("yenile"))})
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


# ============================================================================ uyarılar / ayarlar
@app.get("/api/uyarilar")
def uyarilar():
    return db.alerts(100)


@app.post("/api/uyarilar/okundu")
def uyarilar_okundu():
    db.mark_alerts_seen()
    return {"ok": True}


@app.get("/api/ayarlar")
def ayarlar():
    s = db.get_settings()
    return {**s, "varsayilan_agirlik": AGIRLIK, "varsayilan_etf_agirlik": ETF_AGIRLIK,
            "ag_adresi": getattr(app.state, "ag_adresi", None)}


@app.put("/api/ayarlar")
def ayarlar_kaydet(veri: dict = Body(...)):
    z = veri.get("zamanlama")
    if z and not re.match(r"^\d{1,2}:\d{2}$", str(z.get("saat", "23:15"))):
        raise HTTPException(400, "Saat SS:DD biçiminde olmalı")
    for key in ("agirlik", "etf_agirlik"):
        w = veri.get(key)
        if w is not None and (not isinstance(w, dict) or any(not isinstance(v, (int, float)) or v < 0
                                                             for v in w.values())):
            raise HTTPException(400, "Ağırlıklar sıfır ya da pozitif sayı olmalı")
    return db.save_settings(veri)


# ============================================================================ arayüz
@app.get("/tokens.css")
def tokens_css():
    """Tasarım belirteçleri: web/tokens.json'dan üretilen CSS özel özellikleri."""
    if not design_tokens.TOKENS_FILE.exists():
        tokens, _ = design_tokens.build()
        design_tokens.TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=1), encoding="utf-8")
    return Response(design_tokens.css(), media_type="text/css; charset=utf-8",
                    headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
