"""Arka plan işleri (tarama, analiz) ve günlük zamanlayıcı.

Aynı anda tek iş çalışır: Finviz'e paralel istek göndermemek için. İşin ilerlemesi ve
günlüğü bellekte tutulur; arayüz /api/is ile okur.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import traceback
import uuid

from . import analiz, db, tarama


class JobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.current: dict | None = None
        self.last: dict | None = None

    def busy(self) -> bool:
        with self._lock:
            return self.current is not None

    def status(self) -> dict | None:
        with self._lock:
            job = self.current or self.last
            return dict(job, log=list(job["log"][-200:])) if job else None

    def start(self, kind: str, params: dict, trigger: str = "elle") -> dict:
        with self._lock:
            if self.current is not None:
                raise RuntimeError("Şu anda başka bir iş çalışıyor: " + self.current["baslik"])
            job = {
                "id": uuid.uuid4().hex[:8], "tur": kind, "tetik": trigger,
                "baslik": {"tarama": "Tarama", "analiz": "Geriye dönük analiz"}[kind],
                "durum": "calisiyor", "oran": 0.0, "mesaj": "Başlıyor...", "log": [],
                "baslangic": db.now_str(), "bitis": None, "sonuc": None, "hata": None,
            }
            self.current = job
        threading.Thread(target=self._run, args=(job, params), daemon=True).start()
        return job

    def _log(self, job: dict, msg: str, frac: float | None = None) -> None:
        with self._lock:
            if frac is not None:
                job["oran"] = max(job["oran"], min(1.0, frac))
            job["mesaj"] = msg
            job["log"].append(f"{dt.datetime.now():%H:%M:%S}  {msg}")

    def _run(self, job: dict, params: dict) -> None:
        log = lambda m, f=None: self._log(job, m, f)  # noqa: E731
        try:
            if job["tur"] == "tarama":
                job["sonuc"] = {"tarama_id": tarama.run_scan(params, job["tetik"], log)}
            else:
                res = analiz.run(bool(params.get("yenile")), 6, log)
                job["sonuc"] = {"hisse_sayisi": res["hisse_sayisi"]}
            job["durum"] = "tamam"
        except Exception as exc:
            job["durum"] = "hata"
            job["hata"] = f"{exc.__class__.__name__}: {exc}"
            self._log(job, "Hata: " + job["hata"])
            traceback.print_exc()
        finally:
            with self._lock:
                job["bitis"] = db.now_str()
                self.last = job
                self.current = None


jobs = JobManager()


class Scheduler(threading.Thread):
    """Ayarlardaki saatte günde bir kez otomatik tarama başlatır (uygulama açıkken)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.last_run_date: str | None = None

    def run(self) -> None:
        while True:
            try:
                self.tick(dt.datetime.now())
            except Exception:
                traceback.print_exc()
            time.sleep(30)

    def tick(self, now: dt.datetime) -> None:
        cfg = db.get_settings()["zamanlama"]
        if not cfg.get("aktif"):
            return
        if cfg.get("sadece_hafta_ici", True) and now.weekday() >= 5:
            return
        hh, mm = (int(x) for x in str(cfg.get("saat", "23:15")).split(":"))
        today = now.date().isoformat()
        if self.last_run_date == today or (now.hour, now.minute) < (hh, mm):
            return
        # Bugün zaten (elle ya da otomatik) tamamlanmış bir zamanlama taraması varsa tekrar etme
        for s in db.list_scans(20):
            if s["trigger"] == "zamanlama" and s["started_at"].startswith(today):
                self.last_run_date = today
                return
        if not jobs.busy():
            jobs.start("tarama", {}, trigger="zamanlama")
            self.last_run_date = today
