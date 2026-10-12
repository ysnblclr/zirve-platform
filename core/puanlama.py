"""1 yıllık yükseliş potansiyeli puanı (0–100) ve risk seviyesi.

En büyük bileşen "teknik": analiz.py'nin 5 yıllık geriye dönük testinde eğitilen
lojistik modelin, benzer teknik profildeki yeni zirve hisselerinin 12 ayda +%50
yükselme oranı tahmini. Temel veriler (büyüme, analist, değerleme) geçmişe dönük
test edilemediği için CAN SLIM / momentum literatürüne göre eklenir.
Her bileşen 0–1 arası alt puan üretir, ağırlıkla çarpılıp toplanır; sonra cezalar düşülür.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter

from .ath import verify_ath
from .finviz import earnings_date, num
from .multi_bagger import (
    build_catalysts_and_risks,
    build_deep_opportunity_report,
    build_trading_plan,
    classify_archetype,
)

# Hisse puanı bileşenleri (toplam 100)
AGIRLIK = {
    "teknik": 40,        # modelin ≥+%50 olasılığı: hacim artışı, oynaklık, dipten uzaklık, genişlik...
    "buyume": 25,        # satış ve kâr büyümesi, ivmelenme, sürpriz
    "sahiplik": 10,      # kurum alımı, analist önerisi ve hedefi, içeriden sahiplik
    "degerleme": 8,      # PEG, ileri F/K, fiyat/satış
    "grup": 7,           # endüstri grubunun 3/6/12 aylık performans sırası
    "kalite": 5,         # özsermaye kârlılığı, faaliyet marjı
    "trend": 5,          # fiyat > 50 > 200 günlük ortalama
}

# ETF puanı bileşenleri (toplam 100)
ETF_AGIRLIK = {
    "teknik": 20,
    "momentum": 20,
    "fon_akisi": 25,
    "trend": 10,
    "likidite": 15,
    "maliyet": 5,
    "tema": 5,
}

# Modelin olasılığını 0–1 alt puana çevirme aralığı (test dilimleri yaklaşık %8–%79)
P_UP_LOW, P_UP_HIGH = 0.10, 0.40

HARIC_ENDUSTRI = {"Shell Companies"}
TAVANLI_ETF = re.compile(r"buffer|defined|protection|structured|floor|hedged equity|box spread|"
                         r"income|covered call|yieldmax|buy-?write|t-bill|treasury|bond", re.I)
KALDIRACLI_ETF = re.compile(r"\b(2x|3x|-1x|-2x|-3x|ultra|ultrapro|daily|leveraged|inverse|bear|short)\b", re.I)


def risk_level(p_down: float | None) -> str:
    if p_down is None:
        return "Bilinmiyor"
    return "Düşük" if p_down < 0.08 else "Orta" if p_down < 0.15 else "Yüksek"


def _v(r: dict, k: str) -> float | None:
    return num(r.get(k))


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _pct_ranks(values: list[float | None]) -> list[float]:
    """Listedeki sıralama yüzdesi (0 = en zayıf, 1 = en güçlü). Eksik değer 0,3 alır."""
    present = sorted(v for v in values if v is not None)
    n = len(present)
    out = []
    for v in values:
        if v is None or n < 2:
            out.append(0.3)
            continue
        out.append(sum(1 for x in present if x < v) / (n - 1))
    return out


def _rs_raw(r: dict) -> float | None:
    """IBD göreceli güç benzeri: son çeyreğe daha fazla ağırlık."""
    parts = [(0.4, _v(r, "Perf Quart")), (0.3, _v(r, "Perf Half")), (0.3, _v(r, "Perf Year"))]
    got = [(w, x) for w, x in parts if x is not None]
    return sum(w * x for w, x in got) / sum(w for w, _ in got) if got else None


def _fmt(x: float | None, suffix: str = "%", digits: int = 0) -> str:
    if x is None:
        return "-"
    s = f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("%" + s) if suffix == "%" else (s + suffix)


def _tech_text(name: str, f: dict) -> str:
    v = f.get(name)
    if name == "vol_surge":
        return f"Son 4 haftada hacim 1 yıllık ortalamanın {_fmt(v, '', 1)} katı (yoğun talep)"
    if name == "volatility":
        return f"Yıllık oynaklık {_fmt(v * 100)}: büyük hareket kapasitesi (iki yönlü)"
    if name == "from_low":
        return f"Fiyat 52 haftalık dibinin {_fmt(v * 100)} üstünde: güçlü trend"
    if name == "mom26":
        return f"6 ayda {_fmt(v * 100)} getiri"
    if name == "ext10":
        return f"Fiyat 50 günlük ortalamanın {_fmt(v * 100)} üstünde"
    if name == "multi_year":
        return "Çok yıllık zirvede" if v else "Sadece 52 haftanın zirvesinde"
    return FEATURE_TR.get(name, name)


def _tech_notes(tech: dict | None, reasons: list, risks: list) -> None:
    """Modelde olasılığı en çok artıran iki özelliği ve en çok düşüreni metne çevirir."""
    if not tech:
        return
    f = tech["ozellik"]
    for n in [n for n, c in tech["katki"] if c > 0.08 and n != "multi_year"][:2]:
        if n == "ext10":
            reasons.append(f"Fiyat 50 günlük ortalamaya yakın ({_fmt(f['ext10'] * 100)} üstünde): aşırı uzamamış")
        else:
            reasons.append(_tech_text(n, f))
    for n in [n for n, c in tech["katki"] if c < -0.08][:1]:
        if n == "ext10":
            risks.append(_tech_text(n, f) + " (geçmişte bu kadar uzamış zirvelerde sonraki yıl daha zayıf)")


# ============================================================================ HİSSE
def merged_weights(defaults: dict[str, float], override: dict | None) -> dict[str, float]:
    """Ayarlardaki ağırlıkları varsayılanların üstüne yazar; bilinmeyen anahtarları yok sayar."""
    w = dict(defaults)
    for k, v in (override or {}).items():
        if k in w and isinstance(v, (int, float)) and v >= 0:
            w[k] = float(v)
    return w


def score_stocks(rows: list[dict], industries: dict[str, dict], tech: dict[str, dict],
                 today: dt.date | None = None, industry_sizes: dict[str, int] | None = None,
                 weights: dict | None = None, ath_map: dict[str, dict] | None = None) -> list[dict]:
    """industry_sizes: endüstri başına likit hisse sayısı (analizin evreninden; yoksa boş).
    weights: AGIRLIK'ın üstüne yazılacak ağırlıklar (toplam 100'e ölçeklenir)."""
    today = today or dt.date.today()
    industry_sizes = industry_sizes or {}
    w = merged_weights(AGIRLIK, weights)
    scale = 100 / (sum(w.values()) or 1)
    w = {k: v * scale for k, v in w.items()}
    rows = [r for r in rows if r.get("Ticker") and r.get("Industry") not in HARIC_ENDUSTRI
            and r.get("Industry") != "Exchange Traded Fund"]
    # yetersiz verili menkuller (ör. tercihli hisseler) elenir
    rows = [r for r in rows if _v(r, "Market Cap") and (_v(r, "Sales Q/Q") is not None or _v(r, "EPS") is not None)]
    if not rows:
        return []
    rs = _pct_ranks([_rs_raw(r) for r in rows])
    ind_count = Counter(r.get("Industry") for r in rows)
    grp_vals = {name: _rs_raw_group(p) for name, p in industries.items()}
    grp_rank = dict(zip(grp_vals, _pct_ranks(list(grp_vals.values()))))
    out = [_score_stock(r, rs_pct, ind_count, grp_rank, industries, tech.get(r["Ticker"]), today, industry_sizes, w, ath_map)
           for r, rs_pct in zip(rows, rs)]
    out.sort(key=lambda x: x["puan"], reverse=True)
    return out


def _rs_raw_group(p: dict) -> float | None:
    vals = [(0.4, p.get("Perf Quart")), (0.3, p.get("Perf Half")), (0.3, p.get("Perf Year"))]
    got = [(w, x) for w, x in vals if x is not None]
    return sum(w * x for w, x in got) / sum(w for w, _ in got) if got else None


def _score_stock(r, rs_pct, ind_count, grp_rank, industries, tech, today, industry_sizes, weights, ath_map=None) -> dict:
    g = lambda k: _v(r, k)  # noqa: E731
    price, cap = g("Price"), g("Market Cap")
    q, h, y, m = g("Perf Quart"), g("Perf Half"), g("Perf Year"), g("Perf Month")
    s50, s200, rsi = g("SMA50"), g("SMA200"), g("RSI")
    sales_qq, eps_qq, eps_ny, eps_ty = g("Sales Q/Q"), g("EPS Q/Q"), g("EPS Next Y"), g("EPS This Y")
    sales_3y = g("Sales Past 3Y") if g("Sales Past 3Y") is not None else g("Sales Past 5Y")
    eps_sur, rev_sur = g("EPS Surprise"), g("Revenue Surprise")
    fpe, peg, ps = g("Forward P/E"), g("PEG"), g("P/S")
    roe, oper = g("ROE"), g("Oper M")
    inst_tr, ins_own = g("Inst Trans"), g("Insider Own")
    inst_own, short = g("Inst Own"), g("Short Float")
    recom, target = g("Recom"), g("Target Price")
    avgvol = g("Avg Volume")
    atr, short_ratio = g("ATR"), g("Short Ratio")
    industry = r.get("Industry") or ""
    reasons, risks, tags = [], [], []
    sub = {}

    # --- ATH Doğrulaması
    ticker = r["Ticker"]
    ath_info = (ath_map or {}).get(ticker) or verify_ath(ticker, price)
    is_true_ath = ath_info.get("is_true_ath", False)
    ath_p = ath_info.get("ath_price", price)
    dist_ath = ath_info.get("dist_from_ath_pct", 0.0)

    # --- Arketip, Katalizörler ve Eylem Planı
    r_parsed = {
        "Ticker": ticker,
        "Company": r.get("Company", ticker),
        "Industry": industry,
        "Sector": r.get("Sector", ""),
        "Price": price,
        "Sales Q/Q": sales_qq,
        "EPS Q/Q": eps_qq,
        "EPS Next Y": eps_ny,
        "Short Float": short,
        "Short Ratio": short_ratio,
        "Forward P/E": fpe,
        "P/E": g("P/E"),
        "PEG": peg,
        "P/S": ps,
        "Inst Trans": inst_tr,
        "Inst Own": inst_own,
    }
    arketip = classify_archetype(r_parsed, tech, ath_info)
    katalizler = build_catalysts_and_risks(r_parsed, tech, ath_info)
    plan = build_trading_plan(price, atr, tech, ath_info)
    firsat_raporu = build_deep_opportunity_report(r_parsed, tech, ath_info, plan, arketip)
    for c in katalizler:
        if c not in reasons:
            reasons.append(c)

    # --- teknik (geriye dönük test edilmiş model)
    p_up = tech["p_up"] if tech else None
    p_down = tech["p_down"] if tech else None
    if p_up is not None:
        sub["teknik"] = _clip((p_up - P_UP_LOW) / (P_UP_HIGH - P_UP_LOW))
    else:
        sub["teknik"] = 0.8 * rs_pct  # fiyat geçmişi yoksa listedeki göreceli güç
    if rs_pct >= 0.75:
        reasons.append(f"Göreceli güçte üst dilimde (listede ilk %{max(1, round((1 - rs_pct) * 100))}; "
                       f"3 ay {_fmt(q)}, 6 ay {_fmt(h)}, 1 yıl {_fmt(y)})")
    _tech_notes(tech, reasons, risks)

    # --- trend
    t = 0.0
    if s50 is not None and s200 is not None:
        t = (0.6 if (s50 > 0 and s200 > 0) else 0) + (0.4 if s200 > s50 else 0)
    sub["trend"] = t

    # --- büyüme
    b = 0.0
    if sales_qq is not None:
        b += 0.35 * _clip(sales_qq / 50)
        if sales_qq >= 25:
            reasons.append(f"Satışlar çeyreklik {_fmt(sales_qq)} büyüyor")
    if eps_qq is not None:
        b += 0.20 * _clip(eps_qq / 100)
    if eps_ny is not None:
        b += 0.25 * _clip((eps_ny + 10) / 50)
        if eps_ny >= 20:
            reasons.append(f"Gelecek yıl hisse başı kâr beklentisi {_fmt(eps_ny)} artış")
        elif eps_ny <= -10:
            risks.append(f"Analistler gelecek yıl kârın {_fmt(abs(eps_ny))} düşmesini bekliyor (döngü zirvesi riski)")
    if sales_qq is not None and sales_3y is not None and sales_qq > sales_3y + 5:
        b += 0.10
        reasons.append(f"Büyüme ivmeleniyor (son çeyrek {_fmt(sales_qq)}, 3 yıllık ort. {_fmt(sales_3y)})")
    if eps_sur is not None and rev_sur is not None:
        b += 0.10 * ((eps_sur > 0) + (rev_sur > 0)) / 2
    sub["buyume"] = b

    # --- kalite
    sub["kalite"] = (0.5 * _clip(roe / 25) if roe is not None else 0) + (0.5 * _clip(oper / 25) if oper is not None else 0)

    # --- değerleme
    d = 0.4
    if peg is not None and peg > 0:
        d = 1.0 if peg < 1 else 0.75 if peg < 1.5 else 0.5 if peg < 2.5 else 0.2
    elif fpe is not None and fpe > 0:
        d = 0.8 if fpe < 15 else 0.6 if fpe < 25 else 0.35 if fpe < 50 else 0.1
    if ps is not None and ps > 30:
        d *= 0.5
    sub["degerleme"] = d
    if fpe is not None and 0 < fpe < 15 and rs_pct >= 0.5:
        reasons.append(f"İleri F/K {_fmt(fpe, '', 1)}: güçlü fiyat hareketine rağmen ucuz")

    # --- sahiplik ve analistler
    s = 0.0
    if inst_tr is not None:
        s += 0.3 * _clip((inst_tr + 2) / 7)
        if inst_tr >= 3:
            reasons.append(f"Kurumsal yatırımcılar payını son çeyrekte {_fmt(inst_tr, digits=1)} artırdı")
    if recom is not None:
        s += 0.25 * _clip((3.2 - recom) / 1.7)
    upside = (target / price - 1) * 100 if target and price else None
    if upside is not None:
        s += 0.3 * _clip((upside + 5) / 30)
        if upside >= 15:
            reasons.append(f"Ortalama analist hedefi {_fmt(upside)} yukarıda")
        elif upside < -5:
            risks.append(f"Analist hedefi fiyatın {_fmt(abs(upside))} altında")
    if ins_own is not None:
        s += 0.15 * _clip(ins_own / 20)
    sub["sahiplik"] = s

    # --- endüstri grubu
    gp = grp_rank.get(industry, 0.3)
    sub["grup"] = gp
    if gp >= 0.85:
        perf = industries.get(industry, {})
        reasons.append(f"Endüstrisi ({industry}) en güçlü grupların arasında: 6 ayda {_fmt(perf.get('Perf Half'))}")
    same = ind_count.get(industry, 1)
    if same >= 3 and gp >= 0.75:
        tags.append("Grup hareketi")
    size = industry_sizes.get(industry, 0)
    if size >= 5 and same / size >= 0.35:
        risks.append(f"Endüstrisindeki likit hisselerin {_fmt(min(1, same / size) * 100)} kadarı zirvede: "
                     "kalabalık tema. Geçmiş testte bu oran %50'yi aşınca sonraki 12 ayın medyan getirisi %8'e düştü")

    score = sum(weights[k] * sub[k] for k in weights)

    # --- bonus ve cezalar
    if short is not None and 10 <= short <= 35 and rs_pct >= 0.5:
        score += 2
        reasons.append(f"Açığa satış oranı {_fmt(short, digits=1)}: yükselişte sıkışma potansiyeli")

    # True ATH Bonusu ve Geçmiş Tepe Direnç Cezası
    if is_true_ath:
        score += 4.0
        tags.insert(0, "Gerçek ATH")
    else:
        tags.insert(0, "52H Zirvesi")
        if dist_ath >= 20.0:
            score -= 3.0
            risks.append(f"Tarihsel zirvenin ({ath_p} $) -%{dist_ath:.1f} altında. Üstte geçmiş direnç oluşturan maliyetli satıcılar var.")

    if arketip and arketip not in tags:
        tags.append(arketip)

    ceza = 0
    if rsi is not None and rsi >= 85:
        ceza += 3
        risks.append(f"RSI {rsi:.0f}: aşırı alım, kısa vadeli geri çekilme olası")
    if s50 is not None and s50 >= 30:
        risks.append(f"50 günlük ortalamanın {_fmt(s50)} üstünde: girişte geri çekilme beklemek daha az riskli")
    if m is not None and m >= 100:
        ceza += 12
        risks.append(f"Bir ayda {_fmt(m)}: parabolik hareket")
        tags.append("Spekülatif")
    if ps is not None and ps >= 50:
        ceza += 5
        risks.append(f"Fiyat/satış {ps:.0f}: çok pahalı")
    if inst_own is not None and inst_own < 5:
        ceza += 5
        risks.append("Kurumsal sahiplik %5'in altında")
        if "Spekülatif" not in tags:
            tags.append("Spekülatif")
    if avgvol is not None and avgvol < 200_000:
        ceza += 4
        risks.append("Düşük işlem hacmi")
    score = _clip(score - ceza, 0, 100)

    # --- profil etiketleri
    if sales_qq is not None and sales_qq >= 25 and (eps_ny is None or eps_ny >= 15):
        tags.insert(0, "Büyüme lideri")
    if eps_ny is not None and eps_ny <= -10 and (eps_qq or 0) >= 50:
        tags.append("Döngüsel zirve")
    if fpe is not None and 0 < fpe < 15 and rs_pct >= 0.6:
        tags.append("Değer + momentum")
    if tech and tech["ozellik"].get("vol_surge", 0) >= 2:
        tags.append("Hacim patlaması")
    edate, upcoming = earnings_date(r.get("Earnings"), today)
    if upcoming and edate and (edate - today).days <= 30:
        tags.append("Bilanço yakın")
        reasons.append(f"Bilanço {edate.strftime('%d.%m.%Y')} tarihinde (kataliz)")

    return {
        "tur": "Hisse",
        "sembol": ticker,
        "sirket": r.get("Company", ""),
        "sektor": r.get("Sector", ""),
        "endustri": industry,
        "puan": round(score, 1),
        "p_up": p_up, "p_down": p_down, "risk": risk_level(p_down),
        "alt_puan": {k: round(v, 2) for k, v in sub.items()},
        "agirlik": {k: round(v, 1) for k, v in weights.items()},
        "etiketler": list(dict.fromkeys(tags)),
        "nedenler": reasons,
        "riskler": risks,
        "bilanco": edate.isoformat() if (edate and upcoming) else "",
        "is_true_ath": is_true_ath,
        "ath_fiyat": ath_p,
        "ath_tarih": ath_info.get("ath_date", ""),
        "ath_uzaklik_yuzde": dist_ath,
        "ath_durum": ath_info.get("ath_durum", "ATH"),
        "mavi_gokyuzu": ath_info.get("mavi_gokyuzu", is_true_ath),
        "arketip": arketip,
        "katalizorler": katalizler,
        "plan": plan,
        "firsat_raporu": firsat_raporu,
        "veri": {
            "Fiyat": price, "Piyasa Değeri": cap, "1 Ay": m, "3 Ay": q, "6 Ay": h, "1 Yıl": y,
            "Satış Ç/Ç": sales_qq, "EPS Ç/Ç": eps_qq, "EPS Gelecek Yıl": eps_ny, "EPS Bu Yıl": eps_ty,
            "İleri F/K": fpe, "F/K": g("P/E"), "PEG": peg, "F/S": ps, "P/B": g("P/B"), "P/FCF": g("P/FCF"),
            "Brüt Marj %": g("Gross M") or g("Gross Margin"),
            "Faaliyet Marj %": oper,
            "Kâr Marj %": g("Profit M") or g("Profit Margin"),
            "ROE %": roe, "ROA %": g("ROA"), "ROI %": g("ROI"),
            "Borç/Özsermaye": g("Debt/Eq"), "Cari Oran": g("Current R") or g("Current Ratio"),
            "Beta": g("Beta"), "RSI": rsi, "SMA20": g("SMA20"), "SMA50": s50, "SMA200": s200,
            "Açığa Satış": short, "Short Ratio": short_ratio, "ATR": atr,
            "ATH Fiyat": ath_p, "ATH Uzaklık %": dist_ath,
            "Kurumsal Pay %": inst_own, "Kurum Alımı": inst_tr,
            "İçeriden Pay %": ins_own, "İçeriden Alım %": g("Insider Trans"),
            "Analist Öneri": recom, "Hedef Potansiyel": upside, "Hedef Fiyat": target,
            "Hacim Artışı (x)": tech["ozellik"]["vol_surge"] if tech else None,
            "Oynaklık %": tech["ozellik"]["volatility"] * 100 if tech else None,
            "Göreceli Hacim": g("Rel Volume"), "Ort. Hacim": avgvol,
            "52H Yüksek": g("52W High"), "52H Düşük": g("52W Low"),
            "Temettü %": g("Dividend %"),
        },
    }



# ============================================================================ ETF
def score_etfs(rows: list[dict], tech: dict[str, dict], include_capped: bool = False,
               include_leveraged: bool = False, weights: dict | None = None,
               ath_map: dict[str, dict] | None = None) -> list[dict]:
    w = merged_weights(ETF_AGIRLIK, weights)
    scale = 100 / (sum(w.values()) or 1)
    w = {k: v * scale for k, v in w.items()}
    kept = []
    for r in rows:
        if not r.get("Ticker"):
            continue
        name = r.get("Company", "")
        cat = (r.get("Single Category") or "") + " " + (r.get("Asset Type") or "")
        lev = bool(KALDIRACLI_ETF.search(name)) or "Leveraged" in cat
        capped = bool(TAVANLI_ETF.search(name)) or cat.strip().startswith(("Bonds", "Currency"))
        if (capped and not include_capped) or (lev and not include_leveraged):
            continue
        kept.append((r, lev, capped))
    if not kept:
        return []
    rs = _pct_ranks([_rs_raw(r) for r, _, _ in kept])
    cat_count = Counter(r.get("Single Category") for r, _, _ in kept)
    out = [_score_etf(r, rs_pct, lev, capped, cat_count, tech.get(r["Ticker"]), w, ath_map)
           for (r, lev, capped), rs_pct in zip(kept, rs)]
    out.sort(key=lambda x: x["puan"], reverse=True)
    return out


def _score_etf(r, rs_pct, lev, capped, cat_count, tech, weights, ath_map=None) -> dict:
    g = lambda k: _v(r, k)  # noqa: E731
    price = g("Price")
    q, h, y, m = g("Perf Quart"), g("Perf Half"), g("Perf Year"), g("Perf Month")
    s50, s200, rsi = g("SMA50"), g("SMA200"), g("RSI")
    f1, f3, fy = g("Flows% 1M"), g("Flows% 3M"), g("Flows% YTD")
    aum, avgvol, exp = g("AUM"), g("Avg Volume"), g("Expense")
    cat = r.get("Single Category") or ""
    tags_raw = (r.get("Tags") or "").lower()
    ticker = r["Ticker"]
    reasons, risks, tags = [], [], []

    # ATH Doğrulaması
    ath_info = (ath_map or {}).get(ticker) or verify_ath(ticker, price)
    is_true_ath = ath_info.get("is_true_ath", False)
    ath_p = ath_info.get("ath_price", price)
    dist_ath = ath_info.get("dist_from_ath_pct", 0.0)

    p_up = tech["p_up"] if tech else None
    p_down = tech["p_down"] if tech else None
    sub = {
        "momentum": rs_pct,
        "teknik": _clip((p_up - P_UP_LOW) / (P_UP_HIGH - P_UP_LOW)) if p_up is not None else 0.5 * rs_pct,
    }
    if rs_pct >= 0.7:
        reasons.append(f"Getiride listenin üst diliminde (3 ay {_fmt(q)}, 6 ay {_fmt(h)}, 1 yıl {_fmt(y)})")
    if tech and tech["ozellik"]["vol_surge"] >= 1.5:
        reasons.append(_tech_text("vol_surge", tech["ozellik"]))

    sub["trend"] = ((0.5 if (s50 or 0) > 0 and (s200 or 0) > 0 else 0) + (0.5 if (s200 or 0) > (s50 or 0) else 0)
                    if s50 is not None and s200 is not None else 0)
    fl = 0.0
    if f1 is not None:
        fl += 0.4 * _clip((f1 + 2) / 15)
    if f3 is not None:
        fl += 0.35 * _clip((f3 + 2) / 30)
    if fy is not None:
        fl += 0.25 * _clip((fy + 5) / 50)
    sub["fon_akisi"] = fl
    if f1 is not None and f1 >= 5:
        reasons.append(f"Son bir ayda varlığının {_fmt(f1, digits=1)}'i kadar para girişi")
    elif f3 is not None and f3 <= -10:
        risks.append(f"Son 3 ayda {_fmt(abs(f3))} fon çıkışı")
    sub["tema"] = _clip((cat_count.get(cat, 1) - 1) / 3)
    if cat_count.get(cat, 1) >= 3:
        reasons.append(f"Aynı kategoriden ({cat}) {cat_count[cat]} ETF zirvede")
    li = 0.0
    if aum is not None:
        li += 0.6 * _clip((aum - 50e6) / 450e6)
    if avgvol is not None:
        li += 0.4 * _clip(avgvol / 500_000)
    sub["likidite"] = li
    sub["maliyet"] = _clip((1.0 - exp) / 0.8) if exp is not None else 0.5

    score = sum(weights[k] * sub[k] for k in weights)

    # True ATH Bonusu
    if is_true_ath:
        score += 3.0
        tags.insert(0, "Gerçek ATH")
        reasons.insert(0, "Tarihsel Zirve (Gerçek ATH): ETF tarihin en yüksek seviyesinde")
    else:
        tags.insert(0, "52H Zirvesi")

    ceza = 0
    if rsi is not None and rsi >= 85:
        ceza += 3
        risks.append(f"RSI {rsi:.0f}: aşırı alım")
    if lev:
        ceza += 15
        tags.append("Kaldıraçlı")
        risks.append("Kaldıraçlı/ters ETF: günlük yeniden dengeleme uzun vadede değer aşındırır")
    if capped:
        ceza += 20
        tags.append("Tavanlı getiri")
        risks.append("Tampon/gelir/tahvil ETF'i: yükseliş potansiyeli yapısal olarak sınırlı")
    if aum is not None and aum < 50e6:
        risks.append("Varlık büyüklüğü 50 M $'ın altında")
    if avgvol is not None and avgvol < 100_000:
        risks.append("Düşük işlem hacmi: alım-satım makası geniş olabilir")
    if "futures" in tags_raw or cat.startswith(("Commodities", "Other Asset Types")):
        tags.append("Emtia/vadeli")
        risks.append("Getiri vadeli kontratlara bağlı: şok tersine dönerse sert düşebilir (ör. BWET, BNO)")
    if m is not None and m >= 50:
        ceza += 6
        tags.append("Spekülatif")
        risks.append(f"Bir ayda {_fmt(m)}: parabolik")
    score = _clip(score - ceza, 0, 100)

    plan = build_trading_plan(price, None, tech, ath_info)

    return {
        "tur": "ETF",
        "sembol": ticker,
        "sirket": r.get("Company", ""),
        "sektor": cat,
        "endustri": r.get("Tags", ""),
        "puan": round(score, 1),
        "p_up": p_up, "p_down": p_down, "risk": risk_level(p_down),
        "alt_puan": {k: round(v, 2) for k, v in sub.items()},
        "agirlik": {k: round(v, 1) for k, v in weights.items()},
        "etiketler": list(dict.fromkeys(tags)),
        "nedenler": reasons,
        "riskler": risks,
        "bilanco": "",
        "is_true_ath": is_true_ath,
        "ath_fiyat": ath_p,
        "ath_tarih": ath_info.get("ath_date", ""),
        "ath_uzaklik_yuzde": dist_ath,
        "ath_durum": ath_info.get("ath_durum", "ATH"),
        "mavi_gokyuzu": is_true_ath,
        "arketip": "ETF Zirvesi",
        "katalizorler": reasons[:3],
        "plan": plan,
        "veri": {
            "Fiyat": price, "Varlık (AUM)": aum, "1 Ay": m, "3 Ay": q, "6 Ay": h, "1 Yıl": y,
            "Akış 1A %": f1, "Akış 3A %": f3, "Akış YB %": fy, "Gider %": exp, "RSI": rsi, "SMA50": s50,
            "ATH Fiyat": ath_p, "ATH Uzaklık %": dist_ath,
            "Hacim Artışı (x)": tech["ozellik"]["vol_surge"] if tech else None,
            "Göreceli Hacim": g("Rel Volume"), "Ort. Hacim": avgvol,
        },
    }

