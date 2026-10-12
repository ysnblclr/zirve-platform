"""Platformun dosya yerleşimi. Tüm kalıcı veri 'veri/' klasöründedir."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "veri"
CACHE = DATA / "cache"
PRICE_CACHE = CACHE / "yahoo"
ATH_CACHE = CACHE / "ath"
UNIVERSE_FILE = CACHE / "evren.json"
ANALYSIS_FILE = DATA / "analiz_sonuc.json"
DB_FILE = DATA / "zirve.db"
WEB = ROOT / "web"

for _p in (DATA, CACHE, PRICE_CACHE, ATH_CACHE):
    _p.mkdir(parents=True, exist_ok=True)

