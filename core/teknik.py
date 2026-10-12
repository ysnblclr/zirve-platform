"""Haftalık fiyat verisi (Yahoo Finance), teknik özellikler ve lojistik model.

analiz.py geçmiş olaylarda, tara.py bugünkü adaylarda AYNI özellik fonksiyonunu
kullanır; böylece canlı puan, geriye dönük testte doğrulanan ölçümle hesaplanır.
"""

from __future__ import annotations

import json
import math
import statistics
import time

import requests

from .paths import PRICE_CACHE

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=5y&interval=1wk"
MIN_WEEKS = 64

# Modelin girdileri (sıra önemli; analiz_sonuc.json'daki katsayılarla eşleşir).
# Endüstri genişliği (breadth) analizde raporlanır ama modele girmez: canlı taramada
# tüm endüstrinin haftalık verisi olmadığından aynı tanımla hesaplanamıyor.
FEATURES = ["mom26", "vol_surge", "volatility", "from_low", "ext10", "multi_year"]
FEATURE_TR = {
    "mom26": "6 aylık momentum",
    "vol_surge": "hacim artışı (4 hf / 1 yıl)",
    "volatility": "yıllık oynaklık",
    "from_low": "52 haftalık dipten uzaklık",
    "ext10": "50 günlük ortalamaya uzaklık",
    "multi_year": "çok yıllık zirve",
    "breadth": "endüstri genişliği",
}


# ----------------------------------------------------------------------------- veri
def fetch_prices(ticker: str, max_age_days: float, session: requests.Session) -> dict | None:
    path = PRICE_CACHE / f"{ticker}.json"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return json.loads(path.read_text())
    for attempt in range(4):
        try:
            r = session.get(YAHOO.format(t=ticker), timeout=20)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        try:
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
            data = {"ts": res["timestamp"], "h": q["high"], "l": q["low"], "c": q["close"],
                    "a": adj, "v": q["volume"]}
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        PRICE_CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data
    return None


def clean(d: dict | None, min_weeks: int = MIN_WEEKS) -> dict | None:
    """Boş/sıfır haftaları atar."""
    if not d:
        return None
    rows = [(t, h, l, c, a, v) for t, h, l, c, a, v in zip(d["ts"], d["h"], d["l"], d["c"], d["a"], d["v"])
            if None not in (h, l, c, a) and min(h, l, c, a) > 0]
    if len(rows) < min_weeks:
        return None
    t, h, l, c, a, v = map(list, zip(*rows))
    return {"ts": t, "h": h, "l": l, "c": c, "a": a, "v": [x or 0 for x in v]}


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


# ----------------------------------------------------------------------------- özellikler
def is_new_high(p: dict, i: int) -> bool:
    return i >= 52 and p["h"][i] >= max(p["h"][i - 52:i])


def features_at(p: dict, i: int, breadth: float | None) -> dict:
    """i. haftadaki teknik profil (i >= 52 olmalı)."""
    h, l, c, a, v = p["h"], p["l"], p["c"], p["a"], p["v"]
    rets = [a[j] / a[j - 1] - 1 for j in range(max(1, i - 25), i + 1)]
    sma10 = sum(c[i - 9:i + 1]) / 10
    vol_recent = sum(v[i - 3:i + 1]) / 4
    vol_base = (sum(v[i - 52:i - 4]) / 48) or 1
    return {
        "mom26": a[i] / a[i - 26] - 1,
        "mom52": a[i] / a[i - 52] - 1,
        "vol_surge": vol_recent / vol_base if vol_recent else 1.0,
        "volatility": statistics.pstdev(rets) * math.sqrt(52),
        "from_low": c[i] / min(l[i - 52:i + 1]) - 1,
        "ext10": c[i] / sma10 - 1,
        "multi_year": 1.0 if h[i] >= max(h[:i + 1]) else 0.0,
        "breadth": breadth,
    }


def transform(f: dict) -> list[float]:
    """Model girdisine dönüştürme: uç değerler kırpılır, oranlar log ölçeğe alınır."""
    def clip(x, lo, hi):
        return max(lo, min(hi, x))
    return [
        math.log1p(clip(f["mom26"], -0.8, 5)),
        math.log(clip(f["vol_surge"], 0.2, 10)),
        clip(f["volatility"], 0, 2),
        math.log1p(clip(f["from_low"], 0, 10)),
        clip(f["ext10"], -0.3, 1),
        f["multi_year"],
    ]


# ----------------------------------------------------------------------------- model
def fit_logistic(X: list[list[float]], y: list[int], l2: float = 1e-3, iters: int = 400, lr: float = 0.5) -> dict:
    """Saf Python lojistik regresyon (standartlaştırılmış girdiler, gradyan inişi)."""
    k = len(X[0])
    mean = [statistics.fmean(r[j] for r in X) for j in range(k)]
    std = [statistics.pstdev([r[j] for r in X]) or 1.0 for j in range(k)]
    Z = [[(r[j] - mean[j]) / std[j] for j in range(k)] for r in X]
    w, b, n = [0.0] * k, 0.0, len(Z)
    for _ in range(iters):
        gw, gb = [0.0] * k, 0.0
        for z, t in zip(Z, y):
            s = b + sum(wj * zj for wj, zj in zip(w, z))
            pr = 1 / (1 + math.exp(-max(-30, min(30, s))))
            e = pr - t
            gb += e
            for j in range(k):
                gw[j] += e * z[j]
        b -= lr * gb / n
        w = [wj - lr * (gj / n + l2 * wj) for wj, gj in zip(w, gw)]
    return {"mean": mean, "std": std, "coef": w, "bias": b}


def predict(model: dict, x: list[float]) -> float:
    s = model["bias"] + sum(c * (xi - m) / sd for c, xi, m, sd in zip(model["coef"], x, model["mean"], model["std"]))
    return 1 / (1 + math.exp(-max(-30, min(30, s))))


def contributions(model: dict, x: list[float]) -> list[tuple[str, float]]:
    """Her özelliğin olasılığa katkısı (standart sapma × katsayı), büyükten küçüğe."""
    parts = [(name, c * (xi - m) / sd) for name, c, xi, m, sd
             in zip(FEATURES, model["coef"], x, model["mean"], model["std"])]
    return sorted(parts, key=lambda t: abs(t[1]), reverse=True)
