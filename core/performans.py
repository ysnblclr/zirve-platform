"""Geçmiş taramaların adaylarının bugüne kadarki getirisi ve izleme listesi görünümü."""

from __future__ import annotations

import datetime as dt
import statistics

from . import db
from .tarama import current_prices


def followup(top_n: int = 10) -> dict:
    """Her taramanın ilk N hisse/ETF adayının tarama fiyatından bugüne getirisi, SPY ile kıyaslı."""
    picks = db.picks_for_followup(top_n)
    tickers = sorted({p["ticker"] for p in picks} | {"SPY"})
    prices = current_prices(None, tickers) if picks else {}
    spy_now = prices.get("SPY")
    by_scan: dict[int, dict] = {}
    for p in picks:
        s = by_scan.setdefault(p["scan_id"], {"tarama_id": p["scan_id"], "zaman": p["started_at"],
                                              "spy0": p["spy_price"], "adaylar": []})
        now = prices.get(p["ticker"])
        ret = (now / p["price"] - 1) if (now and p["price"]) else None
        s["adaylar"].append({"tur": p["kind"], "sira": p["rank"], "sembol": p["ticker"], "puan": p["score"],
                             "risk": p["risk"], "fiyat0": p["price"], "fiyat": now, "getiri": ret})
    scans = []
    for s in sorted(by_scan.values(), key=lambda x: x["tarama_id"], reverse=True):
        for kind in ("Hisse", "ETF"):
            rets = [a["getiri"] for a in s["adaylar"] if a["tur"] == kind and a["getiri"] is not None]
            s[f"ort_{kind.lower()}"] = statistics.fmean(rets) if rets else None
        s["spy"] = (spy_now / s["spy0"] - 1) if (spy_now and s["spy0"]) else None
        s["gun"] = (dt.datetime.now() - dt.datetime.fromisoformat(s["zaman"])).days
        scans.append(s)

    # Özet: en az 1 günlük taramalar, aynı sembol tekrar sayılmasın diye ilk görünüşü esas alınır
    first_seen: dict[tuple, dict] = {}
    for s in sorted(scans, key=lambda x: x["tarama_id"]):
        if s["gun"] < 1:
            continue
        for a in s["adaylar"]:
            if a["getiri"] is not None:
                first_seen.setdefault((a["tur"], a["sembol"]), {**a, "spy": s["spy"]})
    summary = {}
    for kind in ("Hisse", "ETF"):
        rows = [a for (k, _), a in first_seen.items() if k == kind]
        if rows:
            rets = [a["getiri"] for a in rows]
            excess = [a["getiri"] - a["spy"] for a in rows if a["spy"] is not None]
            summary[kind] = {
                "n": len(rows), "ort": statistics.fmean(rets), "medyan": statistics.median(rets),
                "isabet": sum(r > 0 for r in rets) / len(rets),
                "spy_ustu": statistics.fmean(excess) if excess else None,
                "en_iyi": max(rows, key=lambda a: a["getiri"]), "en_kotu": min(rows, key=lambda a: a["getiri"]),
            }
    return {"taramalar": scans, "ozet": summary, "spy": spy_now}


def watchlist_view() -> list[dict]:
    """İzleme listesi: eklendiği fiyattan bugüne getiri ve son taramadaki puanı."""
    items = db.watchlist()
    prices = current_prices(None, [w["ticker"] for w in items]) if items else {}
    out = []
    for w in items:
        last = db.latest_result(w["ticker"])
        now = prices.get(w["ticker"])
        out.append({
            **w,
            "fiyat": now,
            "getiri": (now / w["added_price"] - 1) if (now and w["added_price"]) else None,
            "puan": last["puan"] if last else None,
            "risk": last["risk"] if last else None,
            "p_up": last["p_up"] if last else None,
            "sirket": last["sirket"] if last else "",
            "son_tarama": last["tarama_zamani"] if last else None,
            "etiketler": last["etiketler"] if last else [],
        })
    return out
