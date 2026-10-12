"""1 Yıllık Multi-Bagger Katalizörleri, Fırsat Arketipi ve Eylem Planı Modülü.

BWET, PLTR, NVDA, APP, SMCI gibi hisselerin 1 yılda %100 - %500+ yükselmesini sağlayan
katalizör kombinasyonlarını tespit eder, hisseleri 5 ana fırsat arketipine ayırır,
derinlemesine yatırım tezi (fırsat raporu) ve somut işlem planı üretir.
"""

from __future__ import annotations


def classify_archetype(r: dict, tech: dict | None, ath_info: dict) -> str:
    """Hissenin 1 yıllık potansiyel arketipini belirler."""
    industry = (r.get("Industry") or "").lower()
    sector = (r.get("Sector") or "").lower()
    sales_qq = r.get("Sales Q/Q")
    short = r.get("Short Float")
    short_ratio = r.get("Short Ratio")
    fpe = r.get("Forward P/E")
    peg = r.get("PEG")
    is_true_ath = ath_info.get("is_true_ath", False)

    # 1. Açığa Satış Sıkışması (Short Squeeze)
    if short is not None and short >= 10.0 and (is_true_ath or ath_info.get("dist_from_ath_pct", 100) <= 5.0):
        return "Short Squeeze"
    if short_ratio is not None and short_ratio >= 3.5 and (short or 0) >= 7.0:
        return "Short Squeeze"

    # 2. Döngüsel Süper Döngü (Supercycle / Value-Momentum - örn. BWET tanker/emtia)
    if any(k in industry or k in sector for k in [
        "shipping", "tanker", "marine", "energy", "oil", "gas", "coal",
        "steel", "chemical", "uranium", "basic materials", "mining", "transport"
    ]):
        return "Döngüsel ve Emtia"
    if (fpe is not None and 0 < fpe <= 18) and (peg is not None and 0 < peg <= 1.5):
        return "Döngüsel ve Emtia"

    # 3. Biyoteknoloji ve Sağlık (FDA / Klinik Katalizör)
    if any(k in sector or k in industry for k in ["health", "biotech", "drug", "medical", "pharma"]):
        return "Biyoteknoloji"

    # 4. Yapay Zeka ve Yazılım (Hypergrowth Tech/AI)
    if any(k in sector or k in industry for k in [
        "tech", "software", "semiconductor", "communication", "internet",
        "electronics", "information", "cloud"
    ]):
        return "Yapay Zeka ve Yazılım"
    if sales_qq is not None and sales_qq >= 35.0:
        return "Yapay Zeka ve Yazılım"

    # 5. Mavi Gökyüzü Kırılımı (Pure Blue Sky Breakout)
    if is_true_ath:
        return "Mavi Gökyüzü Kırılımı"

    return "Döngüsel ve Emtia" if any(k in sector for k in ["industrial", "financial", "consumer"]) else "Mavi Gökyüzü Kırılımı"


def build_catalysts_and_risks(r: dict, tech: dict | None, ath_info: dict) -> list[str]:
    """1 yıllık yükseliş katalizörlerini maddeler halinde listeler."""
    cats = []
    sales_qq = r.get("Sales Q/Q")
    eps_qq = r.get("EPS Q/Q")
    eps_ny = r.get("EPS Next Y")
    short = r.get("Short Float")
    short_ratio = r.get("Short Ratio")
    fpe = r.get("Forward P/E")
    inst_tr = r.get("Inst Trans")
    vol_surge = tech["ozellik"].get("vol_surge") if tech else None

    # ATH Katalizörü
    if ath_info.get("is_true_ath"):
        cats.append("Mavi Gökyüzü (Gerçek ATH): Tarihsel rekor seviyede; üzerindeki tüm dirençler temizlenmiş, sıfır satış baskısıyla açık fiyat keşfi.")
    else:
        ath_p = ath_info.get("ath_price")
        dist = ath_info.get("dist_from_ath_pct")
        if ath_p and dist:
            cats.append(f"52 Haftalık Zirve (Dip Taban Dönüşü): Tarihi zirvesine ({ath_p} $) -%{dist:.1f} mesafede; uzun vadeli konsolidasyonu yukarı kırdı.")

    # Sıkışma Katalizörü
    if short is not None and short >= 10.0:
        ratio_txt = f", {short_ratio:.1f} gün kapanma süresi" if short_ratio else ""
        cats.append(f"Açığa Satış Sıkışması Katalizörü: %{short:.1f} açığa satış payı{ratio_txt}. Zirvede açıkçıların panik kapatma alımları ralliyi ivmelendirir.")
    elif short_ratio is not None and short_ratio >= 3.5:
        cats.append(f"Yüksek Kapanma Süresi (Short Ratio {short_ratio:.1f} gün): Açık pozisyonların tasfiyesi günlerce sürerek sürekli alış desteği sağlar.")

    # Büyüme Katalizörü
    if sales_qq is not None and sales_qq >= 20.0:
        cats.append(f"Çeyreklik Satış Büyümesi %{sales_qq:.1f}: Güçlü ciro genişlemesi kurumsal çarpan genişlemesini besliyor.")

    if eps_qq is not None and eps_qq >= 30.0:
        cats.append(f"Çeyreklik Kâr Patlaması (EPS +%{eps_qq:.1f}): Faaliyet kârındaki patlama hisseyi kurumsal radara sokuyor.")

    if eps_ny is not None and eps_ny >= 15.0:
        cats.append(f"Gelecek Yıl Kâr Beklentisi +%{eps_ny:.1f}: Analistler büyüme ivmesinin önümüzdeki 12 ay da süreceğini öngörüyor.")

    # Hacim Katalizörü
    if vol_surge is not None and vol_surge >= 1.5:
        cats.append(f"Kurumsal Hacim Patlaması: Son haftalarda işlem hacmi 1 yıllık ortalamanın {vol_surge:.1f} katı (agresif kurumsal alım).")

    # Değerleme / Değer Katalizörü
    if fpe is not None and 0 < fpe <= 16:
        cats.append(f"Cazip Değerleme (İleri F/K {fpe:.1f}): Yüksek büyüme ve güçlü momentuma rağmen değerleme aşırı ısınmamış.")

    # Kurumsal Destek
    if inst_tr is not None and inst_tr >= 2.0:
        cats.append(f"Smart Money / Kurumsal Fon Girişi: Büyük fonlar hisse payını son çeyrekte +%{inst_tr:.1f} artırdı.")

    return cats


def build_trading_plan(price: float, atr: float | None, tech: dict | None, ath_info: dict) -> dict:
    """Hisse için somut eylem seviyeleri (Alım aralığı, Stop-loss, kademeli hedefler ve R:R) üretir."""
    if not price or price <= 0:
        return {}

    ext10 = tech["ozellik"].get("ext10", 0.0) if tech else 0.0

    # Alım Aralığı
    if ext10 > 0.16:
        alim_alt = round(price * 0.93, 2)
        alim_ust = round(price * 0.98, 2)
        alim_not = f"{alim_alt} $ - {alim_ust} $ (50 günlük ortalamaya doğru test / geri çekilme bekle)"
    else:
        alim_alt = round(price * 0.98, 2)
        alim_ust = round(price * 1.02, 2)
        alim_not = f"{alim_alt} $ - {alim_ust} $ (Aktif kırılım / giriş bölgesi)"

    # Stop-Loss: ATR tabanlı dinamik volatilite desteği
    if atr and atr > 0:
        stop_p = round(max(price * 0.88, price - 2.2 * atr), 2)
    else:
        stop_p = round(price * 0.92, 2)

    stop_pct = round(((price - stop_p) / price) * 100.0, 1)

    # Hedefler
    hedef_1 = round(price * 1.35, 2)   # Kısa/Orta Vade: +%35
    hedef_2 = round(price * 2.20, 2)   # 1 Yıllık Multi-Bagger: +%120
    hedef_3 = round(price * 3.50, 2)   # Süper Trend / Moonshot: +%250

    rr = round(120.0 / max(1.0, stop_pct), 1)

    return {
        "alim_araligi": alim_not,
        "stop_loss": stop_p,
        "stop_loss_pct": stop_pct,
        "hedef_1": hedef_1,
        "hedef_1_pct": 35.0,
        "hedef_2": hedef_2,
        "hedef_2_pct": 120.0,
        "hedef_3": hedef_3,
        "hedef_3_pct": 250.0,
        "risk_odul": f"1 : {rr}",
        "invalidation": f"Günlük kapanış {stop_p} $ altında kalırsa veya hacimli kırılım başarısız olursa tez iptal edilir.",
        "pozisyon_onerisi": "Portföyün maksimum %5-%8'i ile sınırlandırılmalı, stop-loss disiplinine katı uyulmalıdır.",
    }


def build_deep_opportunity_report(r: dict, tech: dict | None, ath_info: dict, plan: dict, arketip: str) -> dict:
    """Hisse için derinlemesine, profesyonel 1 yıllık fırsat analiz raporu üretir."""
    price = r.get("Price") or 0.0
    ticker = r.get("Ticker", "")
    company = r.get("Company") or ticker
    sector = r.get("Sector", "")
    industry = r.get("Industry", "")
    sales_qq = r.get("Sales Q/Q")
    eps_qq = r.get("EPS Q/Q")
    eps_ny = r.get("EPS Next Y")
    short = r.get("Short Float")
    short_ratio = r.get("Short Ratio")
    pe = r.get("P/E")
    fpe = r.get("Forward P/E")
    peg = r.get("PEG")
    inst_tr = r.get("Inst Trans")
    inst_own = r.get("Inst Own")
    is_true_ath = ath_info.get("is_true_ath", False)
    ath_price = ath_info.get("ath_price", price)
    dist_ath = ath_info.get("dist_from_ath_pct", 0.0)

    # 1. Yönetici Özeti (Executive Summary)
    if is_true_ath:
        ath_cumlesi = (
            f"{ticker}, tüm zamanların en yüksek seviyesinde ({price:.2f} $) dirençsiz mavi gökyüzü "
            "kırılımı gerçekleştirmiştir. Hissede zararda bekleyen hiçbir maliyetli satıcı bulunmadığından "
            "kurumsal alımlar doğrudan fiyat genişlemesine dönüşmektedir."
        )
    else:
        ath_cumlesi = (
            f"{ticker}, son 52 haftanın en yükseğine çıkarak uzun vadeli bir taban dönüşü gerçekleştirmiştir. "
            f"Tarihsel ATH rekoruna ({ath_price:.2f} $) -%{dist_ath:.1f} mesafede olup, ara dirençleri "
            "test ederek toparlanma momentumunu sürdürmektedir."
        )

    arketip_aciklama = {
        "Döngüsel ve Emtia": (
            "BWET benzeri emtia ve taşımacılık süper döngüsünün tam merkezindedir. "
            "Düşük ileriye dönük F/K oranı ve patlayıcı nakit akışı ile sermaye geri dönüşü hızlanmaktadır."
        ),
        "Short Squeeze": (
            "Yüksek açığa satış payı ve günlerce süren kapanma süresi nedeniyle potansiyel "
            "bir 'Short Squeeze' (açığa satış sıkışması) adayıdır. Zirve kırıldığında açıkçıların panik "
            "alışları ralliyi asimetrik olarak katlayabilir."
        ),
        "Yapay Zeka ve Yazılım": (
            "Yapay zeka ve kurumsal yazılım altyapısındaki hiper büyüme trendinin lideridir. "
            "Yüksek brüt kâr marjı ve operasyonel kaldıraç sayesinde her ilave ciro doğrudan net kâra yansımaktadır."
        ),
        "Biyoteknoloji": (
            "Klinik aşamalar, ilaç onayları ve sektörel AR-GE katalizörleriyle asimetrik getiri potansiyeline "
            "sahiptir. Doğru risk/ödül yönetimiyle yüksek ivme yakalama potansiyeli taşır."
        ),
        "Mavi Gökyüzü Kırılımı": (
            "Tüm zamanların tarihsel zirvesinde dirençsiz serbest fiyat keşfi yaşamaktadır. "
            "Kurumsal hacim patlaması ve piyasa liderliği ile en güçlü momentum kategorisindedir."
        ),
    }.get(arketip, "Güçlü momentum ve zirve kırılımı ile yüksek getiri potansiyeli taşımaktadır.")

    ozet = f"{company} ({ticker}), {arketip} arketipinde konumlanmıştır. {ath_cumlesi} {arketip_aciklama}"

    # 2. Zirve & Mavi Gökyüzü Dinamiği (Supply/Demand Psychology)
    if is_true_ath:
        zirve_dinamigi = (
            f"Tüm Zamanların Zirvesi (Mavi Gökyüzü Kırılımı): Hisse şu anda {price:.2f} $ seviyesinde "
            "tarihin en yüksek fiyatında işlem görmektedir. Bu seviyenin üzerinde hiçbir yatırımcı zararda "
            "beklemediği için 'maliyetine gelsin de çıkayım' psikolojisindeki satış direnci tamamen sıfırlanmıştır. "
            "Hisse serbest fiyat keşfi (blue sky price discovery) evresindedir; kurumsal blok emirler doğrudan "
            "yukarı yönlü fiyat ivmesine dönüşmektedir."
        )
    else:
        zirve_dinamigi = (
            f"52 Haftalık Zirve (Taban Kırılımı ve Toparlanma): Hissenin tarihsel tepe rekoru {ath_price:.2f} $ "
            f"seviyesinde olup hisse bu tepeye -%{dist_ath:.1f} mesafededir. Son 52 haftanın en yükseğine çıkması, "
            "uzun süreli bir dip konsolidasyonunun başarıyla tamamlandığını ve kurumsal alıcıların kontrolü ele "
            "aldığını gösterir. Eski tepelerdeki maliyetli satıcıların realize olabileceği dirençler bulunmakla birlikte, "
            "mevcut momentum bu dirençleri kırma gücüne sahiptir."
        )

    # 3. Smart Money & Açığa Satış (Short Squeeze Engine)
    short_txt = f"%{short:.1f}" if short is not None else "bilinmiyor"
    ratio_txt = f"{short_ratio:.1f} gün" if short_ratio else "bilinmiyor"
    inst_txt = f"+%{inst_tr:.1f}" if inst_tr is not None else "sabit"
    inst_own_txt = f"%{inst_own:.1f}" if inst_own is not None else "bilinmiyor"

    if short is not None and short >= 8.0:
        short_yorumu = (
            f"Halka açık payların {short_txt}'i açığa satılmış olup kapatma süresi {ratio_txt}'dir. "
            "Hisse zirveyi test ettikçe açık pozisyon taşıyan spekülatörler ağır teminat tamamlama (margin call) "
            "baskısı altına girer. Zirvenin kırılması halinde açıkçıların stop alımları patlayıcı bir 'short squeeze' "
            "dalgası yaratabilir."
        )
    else:
        short_yorumu = (
            f"Açığa satış payı {short_txt} ile dengeli seviyededir; hissede yapay spekülatif baskı düşüktür. "
            "Yükseliş doğrudan gerçek kurumsal talep ve temel büyüme tarafından beslenmektedir."
        )

    smart_money = (
        f"Kurumsal ve Açığa Satış Dinamiği: Kurumsal yatırımcıların hissedeki payı {inst_own_txt} olup, "
        f"son çeyrekte net kurumsal pozisyon artışı {inst_txt} seviyesindedir. {short_yorumu}"
    )

    # 4. Temel Büyüme & Kâr Patlaması (Hypergrowth Engine)
    sales_txt = f"+%{sales_qq:.1f}" if sales_qq is not None else "N/A"
    eps_txt = f"+%{eps_qq:.1f}" if eps_qq is not None else "N/A"
    eps_ny_txt = f"+%{eps_ny:.1f}" if eps_ny is not None else "N/A"
    pe_txt = f"{pe:.1f}" if pe else "N/A"
    fpe_txt = f"{fpe:.1f}" if fpe else "N/A"
    peg_txt = f"{peg:.2f}" if peg else "N/A"

    temel_buyume = (
        f"Temel Büyüme ve Kâr Patlaması: Şirket son çeyrekte satışlarını {sales_txt}, hisse başı kârını (EPS) "
        f"{eps_txt} oranında artırmıştır. Gelecek yıl kâr beklentisi {eps_ny_txt} seviyesindedir. "
        f"F/K: {pe_txt}, İleri F/K: {fpe_txt}, PEG: {peg_txt}. Bu finansal ivme, kurumsal analistlerin hedef "
        "fiyatlarını yukarı revize etmesini ve değerleme çarpanlarının yeniden fiyatlanmasını (multiple expansion) "
        "sağlayan temel itici güçtür."
    )

    # 5. Sektörel Süper Döngü ve Makro Katalizör
    sektorel_ruzgar = (
        f"Sektörel ve Makro Katalizör: {company}, {sector} sektöründe ve {industry} endüstrisinde faaliyet göstermektedir. "
        f"{arketip_aciklama} Sektördeki talep genişlemesi ve pazar liderliği, hissenin döngü boyunca endeksten "
        "pozitif ayrışmasını desteklemektedir."
    )

    # 6. Taktik Eylem ve Risk Yönetimi (Playbook)
    alim_not = plan.get("alim_araligi", f"{price} $")
    stop_p = plan.get("stop_loss", round(price * 0.92, 2))
    stop_pct = plan.get("stop_loss_pct", 8.0)
    h1 = plan.get("hedef_1", round(price * 1.35, 2))
    h2 = plan.get("hedef_2", round(price * 2.20, 2))
    h3 = plan.get("hedef_3", round(price * 3.50, 2))
    rr = plan.get("risk_odul", "1 : 15")

    taktik_eylem = (
        f"Taktik Eylem ve Pozisyon Stratejisi: Önerilen alım aralığı {alim_not}. "
        "Kademeli giriş stratejisi olarak pozisyonun %50'si aktif kırılımda, kalan %50'si 20 günlük EMA veya kırılım "
        f"seviyesi testinde açılabilir. Sermaye koruması için dinamik stop-loss {stop_p} $ (-%{stop_pct}) seviyesindedir. "
        f"İlk kâr alma hedefi (TP1) {h1} $ (+%35) seviyesinde anapara emniyete alınmalı ve stop başabaşa çekilmelidir. "
        f"Ana multi-bagger hedefi (TP2) {h2} $ (+%120) ve süper trend koşu hedefi (TP3) {h3} $ (+%250) olarak izlenmelidir. "
        f"Matematiksel Risk/Ödül oranı {rr} seviyesindedir."
    )

    return {
        "baslik": f"{ticker} - %120+ 1 Yıllık Multi-Bagger Fırsat Tezi ({arketip})",
        "ozet": ozet,
        "zirve_dinamigi": zirve_dinamigi,
        "smart_money": smart_money,
        "temel_buyume": temel_buyume,
        "sektorel_ruzgar": sektorel_ruzgar,
        "taktik_eylem": taktik_eylem,
        "invalidation": plan.get("invalidation", f"Günlük kapanış {stop_p} $ altında kalırsa tez geçersiz olur."),
    }
