"""Zirve Platformu - Bağımsız Süreç ve Servis Kontrol Merkezi.

Antigravity veya başka bir araca ihtiyaç duymadan bilgisayarınızdaki tüm
program ve servisleri (Web Sunucusu, Cloudflare Tüneli, Tarayıcılar, Botlar)
görsel bir web paneli üzerinden başlatıp durdurmanızı ve loglarını izlemenizi sağlar.

Erişim: http://127.0.0.1:8999
"""

from __future__ import annotations

import collections
import http.server
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

PORT = 8999
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "servisler.json"
URL_FILE = BASE_DIR / ".tunnel_url"

# Log tamponu (servis başına son 250 satır)
LOG_BUFFERS: dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=250))

# Çalışan süreç referansları
PROCESSES: dict[str, subprocess.Popen | None] = collections.defaultdict(lambda: None)

TUNNEL_URL = ""
if URL_FILE.exists():
    try:
        TUNNEL_URL = URL_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass

URL_REGEX = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


def load_services() -> list[dict]:
    """servisler.json dosyasından servis listesini okur."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    # Varsayılan temel servisler
    default_services = [
        {
            "id": "sunucu",
            "ad": "Zirve Web Platformu",
            "aciklama": "Yeni nesil True-ATH ve Multi-Bagger araştırma platformu sunucusu (Port 8795)",
            "komut": "python sunucu.py --port 8795 --ag --acma",
            "dizin": "",
            "port": 8795,
            "url": "http://127.0.0.1:8795",
            "yerlesik": true,
        },
        {
            "id": "tunel",
            "ad": "Cloudflare İnternet Tüneli",
            "aciklama": "Platformu dış dünyadan (telefondan/tabletten) erişilebilir kılan canlı HTTPS tüneli",
            "komut": "cloudflared.exe tunnel --url http://127.0.0.1:8795",
            "dizin": "",
            "port": None,
            "url": "",
            "yerlesik": true,
        },
        {
            "id": "tarama",
            "ad": "Zirve Tarama Motoru",
            "aciklama": "Finviz ve Yahoo Finance üzerinden tüm zamanların zirvesindeki hisseleri tarar",
            "komut": "python tara.py",
            "dizin": "",
            "port": None,
            "url": "",
            "yerlesik": true,
        },
        {
            "id": "eski_sunucu",
            "ad": "Eski Platform (Port 8790)",
            "aciklama": "Önceki masaüstü sürümünün arka plan servisi",
            "komut": "python platform_backend.py",
            "dizin": "",
            "port": 8790,
            "url": "http://127.0.0.1:8790",
            "yerlesik": false,
        },
    ]
    save_services(default_services)
    return default_services


def save_services(services: list[dict]):
    """servisler.json dosyasına servis listesini kaydeder."""
    try:
        CONFIG_FILE.write_text(json.dumps(services, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Hata: servisler.json kaydedilemedi: {exc}")


def append_log(service: str, text: str):
    global TUNNEL_URL
    lines = text.replace("\r", "").split("\n")
    for line in lines:
        if line.strip():
            timestamp = time.strftime("%H:%M:%S")
            LOG_BUFFERS[service].append(f"[{timestamp}] {line.strip()}")
            if service == "tunel":
                m = URL_REGEX.search(line)
                if m:
                    TUNNEL_URL = m.group(0)
                    try:
                        URL_FILE.write_text(TUNNEL_URL, encoding="utf-8")
                    except Exception:
                        pass


def reader_thread(service: str, pipe):
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            append_log(service, line)
    except Exception:
        pass


def is_port_in_use(port: int) -> int | None:
    """Port kullanımda ise sahibinin PID numarasını (veya 1) döner."""
    if os.name == "nt":
        try:
            cmd = f'powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"'
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                pids = [int(p) for p in out.split() if p.isdigit()]
                return pids[0] if pids else None
        except Exception:
            pass
    else:
        # Linux / Docker ortamı
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return 1
        except Exception:
            pass
    return None


def get_process_pid(process_name: str) -> int | None:
    """Süreç adından PID bulur."""
    if os.name == "nt":
        try:
            cmd = f'powershell -NoProfile -Command "(Get-Process {process_name} -ErrorAction SilentlyContinue).Id"'
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                pids = [int(p) for p in out.split() if p.isdigit()]
                return pids[0] if pids else None
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["pgrep", "-f", process_name], text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                pids = [int(p) for p in out.split() if p.isdigit()]
                return pids[0] if pids else None
        except Exception:
            pass
    return None


def kill_pid(pid: int):
    """PID ve tüm alt süreçlerini zorla sonlandırır."""
    if os.name == "nt":
        try:
            subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def resolve_command_tokens(cmd_str: str) -> list[str]:
    """Komut dizgesini ayrıştırır ve python / cloudflared yollarını çözümler."""
    try:
        tokens = shlex.split(cmd_str, posix=False)
    except Exception:
        tokens = cmd_str.split()

    if not tokens:
        return []

    first = tokens[0].lower().strip('"')
    if first in ("python", "python3", "py"):
        tokens[0] = sys.executable
    elif first in ("cloudflared.exe", "cloudflared"):
        cand = BASE_DIR / "cloudflared.exe"
        if cand.exists():
            tokens[0] = str(cand)

    return tokens


def get_service_status(service_config: dict) -> dict:
    global TUNNEL_URL
    name = service_config["id"]
    p = PROCESSES.get(name)
    running = False
    pid = None

    if p and p.poll() is None:
        running = True
        pid = p.pid
    else:
        # Port ile kontrol
        port = service_config.get("port")
        if port:
            pid = is_port_in_use(int(port))
            running = pid is not None
        elif name == "tunel":
            pid = get_process_pid("cloudflared")
            running = pid is not None

    url = service_config.get("url") or ""
    if name == "tunel" and running:
        if not TUNNEL_URL and URL_FILE.exists():
            try:
                TUNNEL_URL = URL_FILE.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        if not TUNNEL_URL:
            for l in reversed(LOG_BUFFERS["tunel"]):
                m = URL_REGEX.search(l)
                if m:
                    TUNNEL_URL = m.group(0)
                    break
        url = TUNNEL_URL
    elif not url and service_config.get("port") and running:
        url = f"http://127.0.0.1:{service_config['port']}"

    return {
        "id": name,
        "ad": service_config.get("ad", name),
        "aciklama": service_config.get("aciklama", ""),
        "komut": service_config.get("komut", ""),
        "running": running,
        "pid": pid,
        "url": url,
        "port": service_config.get("port"),
        "yerlesik": service_config.get("yerlesik", False),
        "log_count": len(LOG_BUFFERS[name]),
    }


def start_service(name: str):
    global PROCESSES
    services = load_services()
    matched = next((s for s in services if s["id"] == name), None)
    if not matched:
        return {"ok": False, "mesaj": f"'{name}' servisi servisler.json dosyasında bulunamadı."}

    current_status = get_service_status(matched)
    if current_status["running"]:
        return {"ok": False, "mesaj": f"{matched.get('ad', name)} zaten çalışıyor."}

    cmd_tokens = resolve_command_tokens(matched.get("komut", ""))
    if not cmd_tokens:
        return {"ok": False, "mesaj": "Çalıştırılacak komut belirtilmemiş."}

    cwd = matched.get("dizin") or str(BASE_DIR)
    if not Path(cwd).exists():
        cwd = str(BASE_DIR)

    try:
        append_log(name, f"--- Servis başlatılıyor: {' '.join(cmd_tokens)} ---")
        p = subprocess.Popen(
            cmd_tokens,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        PROCESSES[name] = p
        t = threading.Thread(target=reader_thread, args=(name, p.stdout), daemon=True)
        t.start()
        return {"ok": True, "mesaj": f"{matched.get('ad', name)} başlatıldı."}
    except Exception as exc:
        append_log(name, f"Başlatma hatası: {exc}")
        return {"ok": False, "mesaj": str(exc)}


def stop_service(name: str):
    global PROCESSES
    services = load_services()
    matched = next((s for s in services if s["id"] == name), {"id": name})
    st = get_service_status(matched)
    pid = st.get("pid")
    if pid:
        kill_pid(pid)
    p = PROCESSES.get(name)
    if p:
        try:
            p.terminate()
        except Exception:
            pass
        PROCESSES[name] = None
    append_log(name, f"--- Servis durduruldu (PID: {pid}) ---")
    return {"ok": True, "mesaj": f"{matched.get('ad', name)} durduruldu."}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Zirve Kontrol Merkezi</title>
  <style>
    :root {
      --arkaplan: oklch(18% 0.015 250);
      --yuzey: oklch(22% 0.02 250);
      --bilesen: oklch(27% 0.025 250);
      --kenar: oklch(35% 0.03 250);
      --metin: oklch(98% 0.005 250);
      --metin-ikincil: oklch(75% 0.02 250);
      --vurgu: oklch(65% 0.18 250);
      --olumlu: oklch(70% 0.17 145);
      --olumlu-zemin: oklch(25% 0.06 145);
      --uyari: oklch(75% 0.16 75);
      --uyari-zemin: oklch(26% 0.06 75);
      --olumsuz: oklch(65% 0.20 25);
      --olumsuz-zemin: oklch(26% 0.07 25);
      --font: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--font); background: var(--arkaplan); color: var(--metin); min-height: 100vh; padding: 2rem 1rem; }
    .kapsayici { max-width: 1040px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--kenar); padding-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem; }
    h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
    .alt-baslik { font-size: 0.875rem; color: var(--metin-ikincil); margin-top: 0.25rem; }
    .ust-dugmeler { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    
    .servis-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 310px), 1fr)); gap: 1.25rem; margin-bottom: 2rem; }
    .servis-kart { background: var(--yuzey); border: 1px solid var(--kenar); border-radius: 12px; padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between; gap: 1rem; transition: border-color 0.15s; }
    .servis-kart:hover { border-color: var(--vurgu); }
    .kart-ust { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
    .servis-ad { font-size: 1.05rem; font-weight: 600; }
    .servis-aciklama { font-size: 0.85rem; color: var(--metin-ikincil); margin-top: 0.35rem; line-height: 1.4; }
    .servis-komut { font-family: monospace; font-size: 0.75rem; color: var(--metin-ikincil); background: var(--arkaplan); padding: 0.25rem 0.5rem; border-radius: 4px; margin-top: 0.5rem; word-break: break-all; }
    
    .rozet { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.25rem 0.65rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
    .rozet--aktif { background: var(--olumlu-zemin); color: var(--olumlu); border: 1px solid var(--olumlu); }
    .rozet--pasif { background: var(--bilesen); color: var(--metin-ikincil); border: 1px solid var(--kenar); }
    .rozet--nokta { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    
    .bilgi-satiri { font-size: 0.85rem; color: var(--metin-ikincil); display: flex; flex-direction: column; gap: 0.35rem; background: var(--bilesen); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--kenar); }
    .bilgi-satiri strong { color: var(--metin); }
    .bilgi-satiri a { color: var(--vurgu); text-decoration: none; word-break: break-all; font-weight: 500; }
    .bilgi-satiri a:hover { text-decoration: underline; }
    
    .eylemler { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
    button, .dugme { all: unset; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: 600; padding: 0.5rem 0.85rem; border-radius: 8px; border: 1px solid var(--kenar); background: var(--bilesen); color: var(--metin); transition: opacity 0.15s, background 0.15s; text-align: center; }
    button:hover, .dugme:hover { background: var(--kenar); }
    button:focus-visible, .dugme:focus-visible { outline: 2px solid var(--vurgu); outline-offset: 2px; }
    .dugme--birincil { background: var(--vurgu); color: #fff; border-color: var(--vurgu); }
    .dugme--birincil:hover { opacity: 0.9; background: var(--vurgu); }
    .dugme--tehlike { background: var(--olumsuz-zemin); color: var(--olumsuz); border-color: var(--olumsuz); }
    .dugme--tehlike:hover { opacity: 0.9; }
    .dugme--kucuk-sil { font-size: 0.75rem; padding: 0.35rem 0.5rem; color: var(--olumsuz); border-color: transparent; background: transparent; }
    .dugme--kucuk-sil:hover { background: var(--olumsuz-zemin); border-color: var(--olumsuz); }

    /* Modal Form ve Log */
    dialog { background: var(--yuzey); color: var(--metin); border: 1px solid var(--kenar); border-radius: 12px; padding: 1.5rem; max-width: min(640px, calc(100vw - 2rem)); width: 100%; margin: auto; }
    dialog::backdrop { background: rgba(0, 0, 0, 0.7); }
    .modal-bas { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; border-bottom: 1px solid var(--kenar); padding-bottom: 0.75rem; }
    .konsol { background: oklch(14% 0.01 250); border: 1px solid var(--kenar); border-radius: 8px; padding: 0.75rem; font-family: monospace; font-size: 0.8rem; height: 320px; overflow-y: auto; white-space: pre-wrap; color: oklch(85% 0.05 145); line-height: 1.5; }
    
    .form-alan { margin-bottom: 1rem; display: flex; flex-direction: column; gap: 0.35rem; }
    .form-alan label { font-size: 0.85rem; font-weight: 600; color: var(--metin); }
    .form-alan input, .form-alan textarea { background: var(--arkaplan); color: var(--metin); border: 1px solid var(--kenar); border-radius: 6px; padding: 0.5rem 0.75rem; font-family: inherit; font-size: 0.85rem; }
    .form-alan input:focus, .form-alan textarea:focus { outline: 2px solid var(--vurgu); outline-offset: 1px; }
    .form-ipucu { font-size: 0.75rem; color: var(--metin-ikincil); }
    .form-butonlar { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1.5rem; }

    footer { text-align: center; font-size: 0.8rem; color: var(--metin-ikincil); margin-top: 2rem; border-top: 1px solid var(--kenar); padding-top: 1.5rem; }
    footer code { background: var(--bilesen); padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  </style>
</head>
<body>
  <div class="kapsayici">
    <header>
      <div>
        <h1>Zirve Kontrol Merkezi</h1>
        <p class="alt-baslik">Antigravity'den bağımsız arka plan servis ve program yönetim paneli</p>
      </div>
      <div class="ust-dugmeler">
        <button type="button" class="dugme--birincil" onclick="openAddModal()">+ Program Ekle</button>
        <button type="button" onclick="actionAll('start')">Tümünü Başlat</button>
        <button type="button" class="dugme--tehlike" onclick="actionAll('stop')">Tümünü Durdur</button>
      </div>
    </header>

    <div class="servis-grid" id="grid">
      <!-- Servis kartları dinamik yüklenir -->
    </div>

    <footer>
      <p>Yeni programları web arayüzündeki <strong>+ Program Ekle</strong> butonu ile veya klasördeki <code>servisler.json</code> dosyasını düzenleyerek ekleyebilirsiniz.</p>
      <p style="margin-top:0.4rem">Erişim Adresi: <code>http://127.0.0.1:8999</code></p>
    </footer>
  </div>

  <!-- Yeni Program Ekle Modal -->
  <dialog id="addModal">
    <div class="modal-bas">
      <h3>Yeni Program / Servis Ekle</h3>
      <button type="button" onclick="closeAddModal()">Kapat</button>
    </div>
    <form id="addForm" onsubmit="submitAddForm(event)">
      <div class="form-alan">
        <label for="inpAd">Program Adı *</label>
        <input type="text" id="inpAd" required placeholder="Örn: Kripto Fiyat Botu">
      </div>
      <div class="form-alan">
        <label for="inpKomut">Çalıştırma Komutu *</label>
        <input type="text" id="inpKomut" required placeholder="Örn: python bot.py veya node server.js">
        <span class="form-ipucu">Python betikleri için doğrudan 'python script.py' yazabilirsiniz.</span>
      </div>
      <div class="form-alan">
        <label for="inpPort">Port (Opsiyonel)</label>
        <input type="number" id="inpPort" placeholder="Örn: 5000 (Varsa dinlediği yerel port)">
      </div>
      <div class="form-alan">
        <label for="inpUrl">Web Linki / URL (Opsiyonel)</label>
        <input type="text" id="inpUrl" placeholder="Örn: http://127.0.0.1:5000">
      </div>
      <div class="form-alan">
        <label for="inpDizin">Çalışma Klasörü (Opsiyonel)</label>
        <input type="text" id="inpDizin" placeholder="Boş bırakılırsa mevcut proje klasörü kullanılır">
      </div>
      <div class="form-alan">
        <label for="inpAciklama">Kısa Açıklama (Opsiyonel)</label>
        <input type="text" id="inpAciklama" placeholder="Örn: Saatlik veri çeken arka plan betiği">
      </div>
      <div class="form-butonlar">
        <button type="button" onclick="closeAddModal()">Vazgeç</button>
        <button type="submit" class="dugme--birincil">Kaydet ve Ekle</button>
      </div>
    </form>
  </dialog>

  <!-- Log Konsol Modalı -->
  <dialog id="logModal">
    <div class="modal-bas">
      <h3 id="modalBaslik">Servis Logları</h3>
      <button type="button" onclick="closeLog()">Kapat</button>
    </div>
    <div class="konsol" id="logKonsol">Yükleniyor...</div>
  </dialog>

  <script>
    let activeLogService = null;
    let logTimer = null;

    async function loadStatus() {
      try {
        const res = await fetch("/api/durum");
        const data = await res.json();
        render(data.servisler);
      } catch (e) {
        console.error("Durum alınamadı:", e);
      }
    }

    function render(servisler) {
      const grid = document.getElementById("grid");
      grid.innerHTML = servisler.map(s => {
        const durumRozeti = s.running
          ? `<span class="rozet rozet--aktif"><span class="rozet--nokta"></span>Çalışıyor (PID: ${s.pid || '-'})</span>`
          : `<span class="rozet rozet--pasif"><span class="rozet--nokta"></span>Durduruldu</span>`;

        let urlBlok = "";
        if (s.running && s.url) {
          urlBlok = `<div class="bilgi-satiri"><span>Adres: <a href="${s.url}" target="_blank" rel="noopener">${s.url}</a></span></div>`;
        }

        let eylemler = "";
        if (s.id === "tarama") {
          eylemler = s.running
            ? `<button type="button" class="dugme--tehlike" onclick="doAction('${s.id}', 'durdur')">Taramayı Durdur</button>`
            : `<button type="button" class="dugme--birincil" onclick="doAction('${s.id}', 'baslat')">Şimdi Tara</button>`;
        } else {
          eylemler = s.running
            ? `
              ${s.url ? `<a href="${s.url}" target="_blank" rel="noopener" class="dugme dugme--birincil">Aç</a>` : ""}
              <button type="button" onclick="doAction('${s.id}', 'yeniden-baslat')">Yeniden Başlat</button>
              <button type="button" class="dugme--tehlike" onclick="doAction('${s.id}', 'durdur')">Durdur</button>
            `
            : `<button type="button" class="dugme--birincil" onclick="doAction('${s.id}', 'baslat')">Başlat</button>`;
        }

        eylemler += `<button type="button" onclick="openLog('${s.id}', '${escapeHtml(s.ad)}')">Loglar</button>`;

        const silDugmesi = (!s.yerlesik)
          ? `<button type="button" class="dugme--kucuk-sil" onclick="deleteService('${s.id}', '${escapeHtml(s.ad)}')" title="Listeden Kaldır">Kaldır</button>`
          : "";

        return `
          <div class="servis-kart">
            <div>
              <div class="kart-ust">
                <span class="servis-ad">${escapeHtml(s.ad)}</span>
                ${durumRozeti}
              </div>
              <p class="servis-aciklama">${escapeHtml(s.aciklama || '')}</p>
              <div class="servis-komut">${escapeHtml(s.komut || '')}</div>
            </div>
            ${urlBlok}
            <div class="eylemler">
              ${eylemler}
              ${silDugmesi}
            </div>
          </div>
        `;
      }).join("");
    }

    function escapeHtml(text) {
      if (!text) return "";
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    async function doAction(id, action) {
      try {
        await fetch(`/api/servis/${id}/${action}`, { method: "POST" });
        setTimeout(loadStatus, 400);
      } catch (e) {
        alert("İşlem başarısız: " + e.message);
      }
    }

    async function actionAll(action) {
      const endpoint = action === "start" ? "baslat" : "durdur";
      try {
        const res = await fetch("/api/durum");
        const data = await res.json();
        for (const s of data.servisler) {
          if (s.id !== "tarama") {
            await doAction(s.id, endpoint);
          }
        }
      } catch (e) {}
    }

    async function deleteService(id, name) {
      if (!confirm(`'${name}' programını kontrol merkezinden kaldırmak istediğinize emin misiniz?`)) return;
      try {
        const res = await fetch(`/api/servis-sil`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: id })
        });
        const r = await res.json();
        if (r.ok) {
          loadStatus();
        } else {
          alert("Hata: " + r.mesaj);
        }
      } catch (e) {
        alert("Hata: " + e.message);
      }
    }

    function openAddModal() {
      document.getElementById("addForm").reset();
      document.getElementById("addModal").showModal();
    }

    function closeAddModal() {
      document.getElementById("addModal").close();
    }

    async function submitAddForm(e) {
      e.preventDefault();
      const ad = document.getElementById("inpAd").value.trim();
      const komut = document.getElementById("inpKomut").value.trim();
      const portVal = document.getElementById("inpPort").value.trim();
      const url = document.getElementById("inpUrl").value.trim();
      const dizin = document.getElementById("inpDizin").value.trim();
      const aciklama = document.getElementById("inpAciklama").value.trim();

      const payload = {
        ad: ad,
        komut: komut,
        port: portVal ? parseInt(portVal, 10) : null,
        url: url,
        dizin: dizin,
        aciklama: aciklama
      };

      try {
        const res = await fetch("/api/servis-ekle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const r = await res.json();
        if (r.ok) {
          closeAddModal();
          loadStatus();
        } else {
          alert("Hata: " + r.mesaj);
        }
      } catch (err) {
        alert("Bağlantı hatası: " + err.message);
      }
    }

    async function openLog(id, title) {
      activeLogService = id;
      document.getElementById("modalBaslik").textContent = title + " Logları";
      document.getElementById("logModal").showModal();
      fetchLogs();
      if (logTimer) clearInterval(logTimer);
      logTimer = setInterval(fetchLogs, 1500);
    }

    async function fetchLogs() {
      if (!activeLogService) return;
      try {
        const res = await fetch(`/api/servis/${activeLogService}/loglar`);
        const data = await res.json();
        const konsol = document.getElementById("logKonsol");
        konsol.textContent = data.loglar.join("\\n") || "Henüz log kaydı yok.";
        konsol.scrollTop = konsol.scrollHeight;
      } catch (e) {}
    }

    function closeLog() {
      document.getElementById("logModal").close();
      activeLogService = null;
      if (logTimer) clearInterval(logTimer);
    }

    loadStatus();
    setInterval(loadStatus, 3000);
  </script>
</body>
</html>
"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        if path in ("/", "/index.html"):
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/durum":
            configs = load_services()
            servisler = [get_service_status(c) for c in configs]
            self.send_json({"servisler": servisler, "tunel_url": TUNNEL_URL})
            return

        if path.startswith("/api/servis/") and path.endswith("/loglar"):
            parts = path.split("/")
            if len(parts) >= 4:
                name = parts[3]
                logs = list(LOG_BUFFERS.get(name, []))
                self.send_json({"id": name, "loglar": logs})
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"

        # /api/servis-ekle
        if path == "/api/servis-ekle":
            try:
                data = json.loads(raw_body.decode("utf-8"))
                ad = data.get("ad", "").strip()
                komut = data.get("komut", "").strip()
                if not ad or not komut:
                    self.send_json({"ok": False, "mesaj": "Program adı ve komut zorunludur."}, 400)
                    return

                services = load_services()
                # ID oluştur
                base_id = re.sub(r"[^a-zA-Z0-9_]", "_", ad.lower()).strip("_") or "program"
                cand_id = base_id
                idx = 1
                while any(s["id"] == cand_id for s in services):
                    cand_id = f"{base_id}_{idx}"
                    idx += 1

                new_service = {
                    "id": cand_id,
                    "ad": ad,
                    "aciklama": data.get("aciklama", "").strip(),
                    "komut": komut,
                    "dizin": data.get("dizin", "").strip(),
                    "port": data.get("port"),
                    "url": data.get("url", "").strip(),
                    "yerlesik": False,
                }
                services.append(new_service)
                save_services(services)
                self.send_json({"ok": True, "servis": new_service})
            except Exception as exc:
                self.send_json({"ok": False, "mesaj": str(exc)}, 500)
            return

        # /api/servis-sil
        if path == "/api/servis-sil":
            try:
                data = json.loads(raw_body.decode("utf-8"))
                target_id = data.get("id")
                services = load_services()
                target = next((s for s in services if s["id"] == target_id), None)
                if not target:
                    self.send_json({"ok": False, "mesaj": "Servis bulunamadı."}, 404)
                    return
                if target.get("yerlesik", False):
                    self.send_json({"ok": False, "mesaj": "Yerleşik servisler silinemez."}, 400)
                    return

                # Önce durdur
                stop_service(target_id)
                # Listeden çıkar
                services = [s for s in services if s["id"] != target_id]
                save_services(services)
                self.send_json({"ok": True})
            except Exception as exc:
                self.send_json({"ok": False, "mesaj": str(exc)}, 500)
            return

        # /api/servis/{id}/{baslat|durdur|yeniden-baslat}
        m = re.match(r"^/api/servis/([a-zA-Z0-9_\-]+)/(baslat|durdur|yeniden-baslat)$", path)
        if m:
            service_name = m.group(1)
            action = m.group(2)

            if action == "baslat":
                res = start_service(service_name)
            elif action == "durdur":
                res = stop_service(service_name)
            elif action == "yeniden-baslat":
                stop_service(service_name)
                time.sleep(0.5)
                res = start_service(service_name)
            else:
                res = {"ok": False, "mesaj": "Geçersiz eylem"}

            self.send_json(res)
            return

        self.send_response(404)
        self.end_headers()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), DashboardHandler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"=====================================================")
    print(f" Zirve Kontrol Merkezi Calisiyor: {url}")
    print(f" Antigravity'den bagimsiz surec yonetim paneli.")
    print(f" Kapatmak icin bu pencereyi kapatin veya Ctrl+C.")
    print(f"=====================================================")

    # Tarayıcıda aç
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKontrol merkezi kapatildi.")


if __name__ == "__main__":
    main()
