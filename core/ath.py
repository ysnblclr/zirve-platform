"""All-Time High (Tarihin En Yüksek Seviyesi - ATH) Doğrulama Modülü.

Yahoo Finance maksimum aylık grafik geçmişinden hissenin halka arzdan / başlangıçtan
itibaren gördüğü en yüksek fiyatı (Gerçek ATH) ve tarihini çeker; yerel diskte önbelleğe alır.
Finviz 52 haftalık zirveleri ('ta_highlow52w_nh') ile Gerçek ATH arasındaki farkı
kesin olarak tespit eder.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
import requests

from .paths import ATH_CACHE

YAHOO_MAX = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=max&interval=1mo"
ATH_THRESHOLD_PCT = 3.5  # ATH'ye %3.5 veya daha yakınsa 'Gerçek ATH' kabul edilir

RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
    "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def _safe_filename(ticker: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_\-]", "_", ticker).upper()
    if clean in RESERVED_NAMES:
        clean = f"_{clean}_"
    return f"{clean}.json"


def fetch_ath_data(ticker: str, max_age_hours: float = 24.0, session: requests.Session | None = None) -> dict | None:
    """Hissenin tüm zamanlar grafiğini çeker ya da önbellekten okur."""
    path = ATH_CACHE / _safe_filename(ticker)
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    sess = session or requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0"

    for attempt in range(3):
        try:
            r = sess.get(YAHOO_MAX.format(t=ticker), timeout=15)
        except requests.RequestException:
            time.sleep(1.0 * (attempt + 1))
            continue

        if r.status_code == 429:
            time.sleep(3.0 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None

        try:
            data = r.json()
            res = data["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            timestamps = res.get("timestamp") or []
            highs = q.get("high") or []
            closes = q.get("close") or []

            valid_high_indices = [i for i, h in enumerate(highs) if h is not None and h > 0]
            if not valid_high_indices:
                return None

            max_h = -1.0
            max_idx = 0
            for i in valid_high_indices:
                if highs[i] > max_h:
                    max_h = float(highs[i])
                    max_idx = i

            ath_date_str = ""
            if max_idx < len(timestamps) and timestamps[max_idx]:
                ath_dt = dt.datetime.fromtimestamp(timestamps[max_idx], dt.timezone.utc)
                ath_date_str = ath_dt.strftime("%Y-%m")

            last_close = None
            valid_closes = [c for c in closes if c is not None and c > 0]
            if valid_closes:
                last_close = float(valid_closes[-1])

            record = {
                "ticker": ticker.upper(),
                "ath_price": round(max_h, 4),
                "ath_date": ath_date_str,
                "last_close": round(last_close, 4) if last_close else None,
                "cached_at": time.time(),
            }
            try:
                path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                pass
            return record
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    return None


def verify_ath(ticker: str, current_price: float | None = None, session: requests.Session | None = None) -> dict:
    """Verilen sembol için Gerçek ATH durumunu doğrular."""
    raw = fetch_ath_data(ticker, max_age_hours=24.0, session=session)
    cur = current_price
    if cur is None and raw:
        cur = raw.get("last_close")

    if not raw or not raw.get("ath_price") or not cur or cur <= 0:
        return {
            "is_true_ath": True,  # Bilinmiyorsa Finviz sinyaline güven
            "ath_price": cur,
            "ath_date": "",
            "dist_from_ath_pct": 0.0,
            "is_52w_only": False,
            "ath_durum": "ATH",
            "mavi_gokyuzu": True,
        }

    ath_p = raw["ath_price"]
    # Eğer güncel fiyat ATH'den büyükse yeni rekor kırılmıştır
    if cur >= ath_p:
        dist_pct = 0.0
        ath_p = cur
    else:
        dist_pct = ((ath_p - cur) / ath_p) * 100.0

    is_true = dist_pct <= ATH_THRESHOLD_PCT
    is_52w_only = not is_true

    durum = "Gerçek ATH" if is_true else f"52H Zirvesi (-%{dist_pct:.1f} ATH)"

    return {
        "is_true_ath": is_true,
        "ath_price": round(ath_p, 2),
        "ath_date": raw.get("ath_date", ""),
        "dist_from_ath_pct": round(dist_pct, 1),
        "is_52w_only": is_52w_only,
        "ath_durum": durum,
        "mavi_gokyuzu": is_true,  # Üstünde hiçbir tarihsel direnç veya maliyetlenen satıcı yok
    }


def batch_verify_ath(tickers: list[str], current_prices: dict[str, float] | None = None, max_workers: int = 8) -> dict[str, dict]:
    """Birden fazla sembol için paralel olarak ATH durumunu doğrular."""
    cur_map = current_prices or {}
    out: dict[str, dict] = {}
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(verify_ath, t, cur_map.get(t), sess): t for t in tickers}
        for fut in futs:
            t = futs[fut]
            try:
                out[t] = fut.result()
            except Exception:
                out[t] = {
                    "is_true_ath": True,
                    "ath_price": cur_map.get(t),
                    "ath_date": "",
                    "dist_from_ath_pct": 0.0,
                    "is_52w_only": False,
                    "ath_durum": "ATH",
                    "mavi_gokyuzu": True,
                }
    return out
