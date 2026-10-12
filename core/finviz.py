"""Finviz ücretsiz screener istemcisi.

Ücretsiz sürüm sayfa başına 20 satır gösterir; bu modül sayfaları tek tek gezer,
istekler arasında bekler ve 429/5xx hatalarında yeniden dener.
Sütunlar Finviz'in başlık adlarıyla (ör. "Perf Year", "Sales Q/Q") sözlüğe yazılır.
"""

from __future__ import annotations

import datetime as dt
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://finviz.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Özel görünüm (v=152) sütun kimlikleri. Kimlik eşlemesi değişse bile kayıtlar
# Finviz'in döndürdüğü başlık adlarıyla tutulduğu için kod doğru sütunu okur.
STOCK_COLUMNS = list(range(0, 73)) + [125, 126, 127, 128, 132, 133, 142, 143]
ETF_COLUMNS = [
    0, 1, 2, 3, 4, 6, 42, 43, 44, 45, 46, 47, 48, 52, 53, 54, 57, 58, 59, 63, 64, 65, 66,
    100, 103, 105, 107, 109, 112, 113, 114, 115, 116, 117, 120, 125,
]

FREE_ROW_LIMIT = 1000  # ücretsiz sürüm r=1001 ve sonrasına 403 döndürür
_TOTAL_RE = re.compile(r"#1 / (\d+) Total")
_TICKER_RE = re.compile(r"[?&]t=([A-Za-z0-9.\-]+)")
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def num(value) -> float | None:
    """'12.5%' -> 12.5, '1.2B' -> 1.2e9, '1,234' -> 1234.0, '-' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    v = str(value).strip().replace(",", "")
    if v in ("", "-"):
        return None
    mult = 1.0
    if v.endswith("%"):
        v = v[:-1]
    elif v[-1] in _SUFFIX:
        mult = _SUFFIX[v[-1]]
        v = v[:-1]
    try:
        return float(v) * mult
    except ValueError:
        return None


def earnings_date(value: str | None, today: dt.date | None = None) -> tuple[dt.date | None, bool]:
    """Finviz 'Oct 28/b' biçimini tarihe çevirir. (tarih, gelecekte_mi) döner.

    Finviz yeni tarih açıklanana kadar son bilanço tarihini gösterir; bu yüzden
    bugünden önceki tarih 'geçmiş bilanço' kabul edilir.
    """
    today = today or dt.date.today()
    if not value:
        return None, False
    m = re.match(r"([A-Z][a-z]{2}) (\d{1,2})", value.strip())
    if not m or m.group(1) not in _MONTHS:
        return None, False
    d = dt.date(today.year, _MONTHS[m.group(1)], int(m.group(2)))
    if (d - today).days < -180:
        d = d.replace(year=today.year + 1)
    elif (d - today).days > 180:
        d = d.replace(year=today.year - 1)
    return d, d >= today


try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as cffi_requests
    HAS_CURL_CFFI = False


class FinvizClient:
    def __init__(self, delay: float = 0.8, retries: int = 4, timeout: int = 25, verbose: bool = True,
                 log=None):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.verbose = verbose
        self.log_fn = log or (lambda m: print(m, flush=True))
        self._last = 0.0
        self._warmed = False
        if HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome124")
        else:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })

    def _get(self, path: str, params: dict | None = None) -> str:
        url = BASE + path
        if not self._warmed:
            try:
                self.session.get(BASE, timeout=10)
                self._warmed = True
            except Exception:
                pass
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
            except Exception as exc:
                if attempt == self.retries:
                    raise
                self._log(f"  bağlantı hatası ({exc.__class__.__name__}), yeniden deneniyor...")
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                self._log(f"  Finviz {r.status_code} döndü, {5 * (attempt + 1)} sn bekleniyor...")
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
        raise RuntimeError("Finviz isteği başarısız: " + url)

    def _log(self, msg: str) -> None:
        if self.verbose:
            self.log_fn(msg.strip())

    # ------------------------------------------------------------------ screener
    def screener(self, filters: str, columns: list[int], order: str | None = None,
                 tickers: str | None = None, max_rows: int = 3000, label: str = "") -> list[dict]:
        """Bir screener sorgusunun tüm sayfalarını okur ve satırları sözlük olarak döner."""
        params = {"v": "152", "c": ",".join(map(str, columns))}
        if filters:
            params["f"] = filters
        if order:
            params["o"] = order
        if tickers:
            params["t"] = tickers
        out: list[dict] = []
        seen: set[str] = set()
        total = None
        r = 1
        while r <= max_rows:
            html = self._get("/screener.ashx", {**params, "r": r})
            if total is None:
                m = _TOTAL_RE.search(html)
                total = int(m.group(1)) if m else None
                self._log(f"  {label or filters}: {total if total is not None else '?'} sonuç")
                if total and total > FREE_ROW_LIMIT:
                    self._log(f"  Uyarı: ücretsiz Finviz ilk {FREE_ROW_LIMIT} satırı verir; filtreyi daraltın.")
                    max_rows = min(max_rows, FREE_ROW_LIMIT)
            rows = _parse_screener(html)
            new = [x for x in rows if x.get("Ticker") not in seen]
            if not new:
                break
            for x in new:
                seen.add(x["Ticker"])
            out.extend(new)
            if len(rows) < 20 or (total is not None and len(out) >= total):
                break
            r += 20
        return out

    def tickers(self, filters: str, max_rows: int = 10000) -> list[str]:
        """Sadece sembol listesi (v=411 görünümü sayfa başına 1000 sembol verir)."""
        out: list[str] = []
        r = 1
        while r <= max_rows:
            html = self._get("/screener.ashx", {"v": "411", "f": filters, "r": r})
            found = re.findall(r"stock\?t=([A-Za-z0-9.\-]+)", html)
            new = [t for t in dict.fromkeys(found) if t not in out]
            if not new:
                break
            out.extend(new)
            if len(found) < 1000:
                break
            r += 1000
        return out

    # ------------------------------------------------------------------ gruplar
    def industries(self) -> dict[str, dict]:
        """Endüstri grup performansları: {'Marine Shipping': {'Perf Half': 31.2, ...}}"""
        html = self._get("/groups.ashx", {"g": "industry", "v": "140", "o": "name"})
        soup = BeautifulSoup(html, "lxml")
        tables = [t for t in soup.find_all("table") if "Perf Half" in t.get_text()]
        if not tables:
            return {}
        table = tables[-1]
        header = [th.get_text(strip=True) for th in table.find_all("th")]
        out = {}
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) != len(header):
                continue
            rec = dict(zip(header, cells))
            name = rec.get("Name")
            if name:
                out[name] = {k: num(v) for k, v in rec.items() if k not in ("No.", "Name")}
        return out

    # ------------------------------------------------------------------ haberler
    def news(self, ticker: str, n: int = 5) -> list[dict]:
        html = self._get("/quote.ashx", {"t": ticker, "p": "d"})
        soup = BeautifulSoup(html, "lxml")
        table = soup.find(id="news-table")
        if not table:
            return []
        out, last_date = [], ""
        for tr in table.find_all("tr"):
            a = tr.find("a")
            if not a or not a.get_text(strip=True):
                continue
            stamp = tr.find("td").get_text(" ", strip=True) if tr.find("td") else ""
            m = re.match(r"(Today|[A-Z][a-z]{2}-\d{2}-\d{2})", stamp)
            if m:
                last_date = m.group(1)
            src = tr.select_one(".news-link-right span")
            href = a.get("href", "")
            if href.startswith("/"):
                href = BASE + href
            out.append({
                "date": last_date,
                "title": a.get_text(strip=True),
                "url": href,
                "source": src.get_text(strip=True).strip("()") if src else "",
            })
            if len(out) >= n:
                break
        return out


def _parse_screener(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.screener_table")
    if table is None:
        return []
    trs = table.find_all("tr")
    if not trs:
        return []
    header = [c.get_text(strip=True) for c in trs[0].find_all(["th", "td"])]
    rows = []
    for tr in trs[1:]:
        cells = tr.find_all("td")
        if len(cells) != len(header):
            continue
        rec = {}
        for h, c in zip(header, cells):
            if h == "Ticker":
                a = c.find("a", href=_TICKER_RE)
                m = _TICKER_RE.search(a["href"]) if a else None
                rec[h] = m.group(1) if m else c.get_text(strip=True)
            else:
                rec[h] = c.get_text(strip=True)
        rows.append(rec)
    return rows
