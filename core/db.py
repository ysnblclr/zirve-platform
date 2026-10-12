"""SQLite depolama: taramalar, sonuçlar, izleme listesi, uyarılar ve ayarlar."""

from __future__ import annotations

import copy
import datetime as dt
import json
import sqlite3
from contextlib import contextmanager

from .paths import DB_FILE

DEFAULT_SETTINGS = {
    "tarama": {"mod": "zirve", "kucuk": False, "kaldiracli": False, "tavanli": False, "haber": 15},
    # Türkiye saati. ABD seansı yaz saatinde 23:00'te kapanır; kapanış sonrası tarama günün kesin listesini verir.
    "zamanlama": {"aktif": False, "saat": "23:15", "sadece_hafta_ici": True},
    "uyari": {"esik": 70, "yeni_ilk10": True, "izleme": True},
    "agirlik": None,       # None = puanlama.AGIRLIK varsayılanları
    "etf_agirlik": None,   # None = puanlama.ETF_AGIRLIK varsayılanları
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,              -- calisiyor | tamam | hata
    trigger TEXT NOT NULL,             -- elle | zamanlama | komut
    options_json TEXT NOT NULL,
    n_stocks INTEGER DEFAULT 0,
    n_etfs INTEGER DEFAULT 0,
    spy_price REAL,
    groups_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS results (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                -- Hisse | ETF
    rank INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    score REAL NOT NULL,
    p_up REAL,
    p_down REAL,
    risk TEXT,
    price REAL,
    item_json TEXT NOT NULL,
    PRIMARY KEY (scan_id, kind, ticker)
);
CREATE INDEX IF NOT EXISTS ix_results_ticker ON results(ticker);
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    added_price REAL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    scan_id INTEGER,
    ticker TEXT,
    message TEXT NOT NULL,
    seen INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
"""


def now_str() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    c = sqlite3.connect(DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)
        # yarıda kalmış taramalar (uygulama kapatıldıysa) hata olarak işaretlenir
        c.execute("UPDATE scans SET status='hata', error='Uygulama tarama sırasında kapandı' "
                  "WHERE status='calisiyor'")


# ----------------------------------------------------------------------------- ayarlar
def get_settings() -> dict:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    with conn() as c:
        for r in c.execute("SELECT key, value_json FROM settings"):
            val = json.loads(r["value_json"])
            if isinstance(out.get(r["key"]), dict) and isinstance(val, dict):
                out[r["key"]].update(val)
            else:
                out[r["key"]] = val
    return out


def save_settings(partial: dict) -> dict:
    with conn() as c:
        for k, v in partial.items():
            if k not in DEFAULT_SETTINGS:
                continue
            c.execute("INSERT INTO settings(key, value_json) VALUES(?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json", (k, json.dumps(v)))
    return get_settings()


# ----------------------------------------------------------------------------- taramalar
def create_scan(options: dict, trigger: str) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO scans(started_at, status, trigger, options_json) VALUES(?, 'calisiyor', ?, ?)",
                        (now_str(), trigger, json.dumps(options)))
        return cur.lastrowid


def finish_scan(scan_id: int, status: str, n_stocks: int = 0, n_etfs: int = 0, spy: float | None = None,
                groups: list | None = None, error: str | None = None) -> None:
    with conn() as c:
        c.execute("UPDATE scans SET finished_at=?, status=?, n_stocks=?, n_etfs=?, spy_price=?, groups_json=?, error=? "
                  "WHERE id=?", (now_str(), status, n_stocks, n_etfs, spy, json.dumps(groups or []), error, scan_id))


def insert_results(scan_id: int, items: list[dict]) -> None:
    rank: dict[str, int] = {}
    rows = []
    for it in items:
        rank[it["tur"]] = rank.get(it["tur"], 0) + 1
        rows.append((scan_id, it["tur"], rank[it["tur"]], it["sembol"], it["puan"], it.get("p_up"), it.get("p_down"),
                     it.get("risk"), it["veri"].get("Fiyat"), json.dumps(it, ensure_ascii=False, default=str)))
    with conn() as c:
        c.executemany("INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?,?,?)", rows)


def _scan_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["options"] = json.loads(d.pop("options_json") or "{}")
    d["groups"] = json.loads(d.pop("groups_json") or "[]")
    return d


def list_scans(limit: int = 100) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = _scan_row(r)
        d.pop("groups")
        out.append(d)
    return out


def get_scan(scan_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
    return _scan_row(r) if r else None


def latest_scan_id(status: str = "tamam") -> int | None:
    with conn() as c:
        r = c.execute("SELECT id FROM scans WHERE status=? ORDER BY id DESC LIMIT 1", (status,)).fetchone()
    return r["id"] if r else None


def previous_scan_id(scan_id: int) -> int | None:
    with conn() as c:
        r = c.execute("SELECT id FROM scans WHERE status='tamam' AND id<? ORDER BY id DESC LIMIT 1",
                      (scan_id,)).fetchone()
    return r["id"] if r else None


def get_results(scan_id: int, kind: str | None = None, limit: int | None = None) -> list[dict]:
    q = "SELECT item_json, rank FROM results WHERE scan_id=?"
    args: list = [scan_id]
    if kind:
        q += " AND kind=?"
        args.append(kind)
    q += " ORDER BY kind DESC, rank"
    if limit:
        q += " LIMIT ?"
        args.append(limit)
    with conn() as c:
        rows = c.execute(q, args).fetchall()
    out = []
    for r in rows:
        it = json.loads(r["item_json"])
        it["sira"] = r["rank"]
        out.append(it)
    return out


def delete_scan(scan_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM results WHERE scan_id=?", (scan_id,))
        c.execute("DELETE FROM alerts WHERE scan_id=?", (scan_id,))
        c.execute("DELETE FROM scans WHERE id=?", (scan_id,))


def ticker_history(ticker: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT s.id AS scan_id, s.started_at, r.kind, r.rank, r.score, r.p_up, r.p_down, r.risk, r.price "
            "FROM results r JOIN scans s ON s.id = r.scan_id WHERE r.ticker=? AND s.status='tamam' "
            "ORDER BY s.id", (ticker,)).fetchall()
    return [dict(r) for r in rows]


def latest_result(ticker: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT r.item_json, r.rank, r.scan_id, s.started_at FROM results r "
                      "JOIN scans s ON s.id=r.scan_id WHERE r.ticker=? AND s.status='tamam' "
                      "ORDER BY s.id DESC LIMIT 1", (ticker,)).fetchone()
    if not r:
        return None
    it = json.loads(r["item_json"])
    it.update(sira=r["rank"], scan_id=r["scan_id"], tarama_zamani=r["started_at"])
    return it


def picks_for_followup(top_n: int) -> list[dict]:
    """Tamamlanmış her taramanın ilk N hisse ve ETF adayı (performans takibi için)."""
    with conn() as c:
        rows = c.execute(
            "SELECT s.id AS scan_id, s.started_at, s.spy_price, r.kind, r.rank, r.ticker, r.score, r.price, r.risk "
            "FROM results r JOIN scans s ON s.id=r.scan_id WHERE s.status='tamam' AND r.rank<=? "
            "ORDER BY s.id DESC, r.kind DESC, r.rank", (top_n,)).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------- izleme listesi
def watchlist() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM watchlist ORDER BY added_at DESC")]


def watch_add(ticker: str, price: float | None, note: str = "", added_at: str | None = None) -> None:
    """added_at verilirse (geri alma) eklenme tarihi ve fiyatı aynen geri yüklenir."""
    with conn() as c:
        c.execute("INSERT INTO watchlist(ticker, added_at, added_price, note) VALUES(?,?,?,?) "
                  "ON CONFLICT(ticker) DO UPDATE SET note=excluded.note", (ticker, added_at or now_str(), price, note))


def watch_remove(ticker: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))


def watched() -> set[str]:
    with conn() as c:
        return {r["ticker"] for r in c.execute("SELECT ticker FROM watchlist")}


# ----------------------------------------------------------------------------- uyarılar
def add_alert(scan_id: int | None, ticker: str | None, message: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO alerts(created_at, scan_id, ticker, message) VALUES(?,?,?,?)",
                  (now_str(), scan_id, ticker, message))


def alerts(limit: int = 50) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


def unseen_alerts() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM alerts WHERE seen=0").fetchone()[0]


def mark_alerts_seen() -> None:
    with conn() as c:
        c.execute("UPDATE alerts SET seen=1 WHERE seen=0")
