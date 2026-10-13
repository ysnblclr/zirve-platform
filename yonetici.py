"""Zirve Platformu - Bağımsız Süreç ve Servis Kontrol Merkezi.

Antigravity veya başka bir araca ihtiyaç duymadan bilgisayarınızdaki tüm
Zirve Platformu servislerini (Web Sunucusu, Cloudflare Tüneli, Tarama Motoru)
görsel bir web paneli üzerinden başlatıp durdurmanızı ve loglarını izlemenizi sağlar.

Erişim: http://127.0.0.1:8999
"""

from __future__ import annotations

import collections
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

PORT = 8999
BASE_DIR = Path(__file__).resolve().parent

# Log tamponu (servis başına son 200 satır)
LOG_BUFFERS: dict[str, collections.deque] = {
    "sunucu": collections.deque(maxlen=200),
    "tunel": collections.deque(maxlen=200),
    "tarama": collections.deque(maxlen=200),
    "eski_sunucu": collections.deque(maxlen=200),
}

# Çalışan süreç referansları
PROCESSES: dict[str, subprocess.Popen | None] = {
    "sunucu": None,
    "tunel": None,
    "tarama": None,
    "eski_sunucu": None,
}

TUNNEL_URL = ""
URL_REGEX = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


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


def reader_thread(service: str, pipe):
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            append_log(service, line)
    except Exception:
        pass


def is_port_in_use(port: int) -> int | None:
    """Port kullanımda ise sahibinin PID numarasını döner."""
    try:
        cmd = f'powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"'
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            pids = [int(p) for p in out.split() if p.isdigit()]
            return pids[0] if pids else None
    except Exception:
        pass
    return None


def get_process_pid(service_name: str) -> int | None:
    """Süreç adından PID bulur (Windows)."""
    try:
        cmd = f'powershell -NoProfile -Command "(Get-Process {service_name} -ErrorAction SilentlyContinue).Id"'
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            pids = [int(p) for p in out.split() if p.isdigit()]
            return pids[0] if pids else None
    except Exception:
        pass
    return None


def kill_pid(pid: int):
    """Windows'ta PID ve tüm alt süreçlerini zorla sonlandırır."""
    try:
        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def start_service(name: str):
    global PROCESSES
    if get_service_status(name)["running"]:
        return {"ok": False, "mesaj": f"{name} zaten çalışıyor."}

    cmd = []
    cwd = str(BASE_DIR)

    if name == "sunucu":
        cmd = [sys.executable, "sunucu.py", "--port", "8795", "--ag", "--acma"]
    elif name == "tunel":
        exe = str(BASE_DIR / "cloudflared.exe")
        cmd = [exe, "tunnel", "--url", "http://127.0.0.1:8795"]
    elif name == "tarama":
        cmd = [sys.executable, "tara.py"]
    elif name == "eski_sunucu":
        cmd = [sys.executable, "platform_backend.py"]
    else:
        return {"ok": False, "mesaj": "Bilinmeyen servis"}

    try:
        append_log(name, f"--- Servis başlatılıyor: {' '.join(cmd)} ---")
        p = subprocess.Popen(
            cmd,
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
        return {"ok": True, "mesaj": f"{name} başlatıldı."}
    except Exception as exc:
        append_log(name, f"Başlatma hatası: {exc}")
        return {"ok": False, "mesaj": str(exc)}


def stop_service(name: str):
    global PROCESSES
    st = get_service_status(name)
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
    return {"ok": True, "mesaj": f"{name} durduruldu."}


def get_service_status(name: str) -> dict:
    global TUNNEL_URL
    p = PROCESSES.get(name)
    running = False
    pid = None

    if p and p.poll() is None:
        running = True
        pid = p.pid
    else:
        # Sistemde harici olarak (örneğin Antigravity veya terminal tarafından) başlatılmış mı kontrol et
        if name == "sunucu":
            pid = is_port_in_use(8795)
            running = pid is not None
        elif name == "tunel":
            pid = get_process_pid("cloudflared")
            running = pid is not None
        elif name == "eski_sunucu":
            pid = is_port_in_use(8790)
            running = pid is not None

    url = ""
    if name == "sunucu" and running:
        url = "http://127.0.0.1:8795"
    elif name == "tunel" and running:
        if not TUNNEL_URL:
            # Loglardan son trycloudflare linkini ara
            for l in reversed(LOG_BUFFERS["tunel"]):
                m = URL_REGEX.search(l)
                if m:
                    TUNNEL_URL = m.group(0)
                    break
        url = TUNNEL_URL
    elif name == "eski_sunucu" and running:
        url = "http://127.0.0.1:8790"

    return {
        "id": name,
        "running": running,
        "pid": pid,
        "url": url,
        "log_count": len(LOG_BUFFERS[name]),
    }


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
    .kapsayici { max-width: 960px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--kenar); padding-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem; }
    h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
    .alt-baslik { font-size: 0.875rem; color: var(--metin-ikincil); margin-top: 0.25rem; }
    .ust-dugmeler { display: flex; gap: 0.5rem; }
    
    .servis-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 1.25rem; margin-bottom: 2rem; }
    .servis-kart { background: var(--yuzey); border: 1px solid var(--kenar); border-radius: 12px; padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between; gap: 1rem; }
    .kart-ust { display: flex; justify-content: space-between; align-items: flex-start; }
    .servis-ad { font-size: 1.1rem; font-weight: 600; }
    .servis-aciklama { font-size: 0.85rem; color: var(--metin-ikincil); margin-top: 0.35rem; line-height: 1.4; }
    
    .rozet { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.25rem 0.65rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .rozet--aktif { background: var(--olumlu-zemin); color: var(--olumlu); border: 1px solid var(--olumlu); }
    .rozet--pasif { background: var(--bilesen); color: var(--metin-ikincil); border: 1px solid var(--kenar); }
    .rozet--nokta { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    
    .bilgi-satiri { font-size: 0.85rem; color: var(--metin-ikincil); display: flex; flex-direction: column; gap: 0.35rem; background: var(--bilesen); padding: 0.75rem; border-radius: 8px; border: 1px solid var(--kenar); }
    .bilgi-satiri strong { color: var(--metin); }
    .bilgi-satiri a { color: var(--vurgu); text-decoration: none; word-break: break-all; }
    .bilgi-satiri a:hover { text-decoration: underline; }
    
    .eylemler { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    button, .dugme { all: unset; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: 600; padding: 0.5rem 0.85rem; border-radius: 8px; border: 1px solid var(--kenar); background: var(--bilesen); color: var(--metin); transition: opacity 0.15s, background 0.15s; text-align: center; }
    button:hover, .dugme:hover { background: var(--kenar); }
    button:focus-visible, .dugme:focus-visible { outline: 2px solid var(--vurgu); outline-offset: 2px; }
    .dugme--birincil { background: var(--vurgu); color: #fff; border-color: var(--vurgu); }
    .dugme--birincil:hover { opacity: 0.9; background: var(--vurgu); }
    .dugme--tehlike { background: var(--olumsuz-zemin); color: var(--olumsuz); border-color: var(--olumsuz); }
    .dugme--tehlike:hover { opacity: 0.9; }
    .dugme--tam { width: 100%; }

    /* Modal (Log penceresi) */
    dialog { background: var(--yuzey); color: var(--metin); border: 1px solid var(--kenar); border-radius: 12px; padding: 1.5rem; max-width: min(720px, calc(100vw - 2rem)); width: 100%; margin: auto; }
    dialog::backdrop { background: rgba(0, 0, 0, 0.7); }
    .modal-bas { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--kenar); padding-bottom: 0.75rem; }
    .konsol { background: oklch(14% 0.01 250); border: 1px solid var(--kenar); border-radius: 8px; padding: 0.75rem; font-family: monospace; font-size: 0.8rem; height: 320px; overflow-y: auto; white-space: pre-wrap; color: oklch(85% 0.05 145); line-height: 1.5; }
    
    footer { text-align: center; font-size: 0.8rem; color: var(--metin-ikincil); margin-top: 2rem; }
  </style>
</head>
<body>
  <div class="kapsayici">
    <header>
      <div>
        <h1>Zirve Kontrol Merkezi</h1>
        <p class="alt-baslik">Antigravity'den bağımsız arka plan servis ve tünel yönetim paneli</p>
      </div>
      <div class="ust-dugmeler">
        <button type="button" onclick="actionAll('start')">Tümünü Başlat</button>
        <button type="button" class="dugme--tehlike" onclick="actionAll('stop')">Tümünü Durdur</button>
      </div>
    </header>

    <div class="servis-grid" id="grid">
      <!-- Servis kartları JavaScript ile dinamik basılır -->
    </div>

    <footer>
      <p>Zirve Platformu Yönetici Servisi — Yerel Port 8999 üzerinde çalışmaktadır.</p>
    </footer>
  </div>

  <dialog id="logModal">
    <div class="modal-bas">
      <h3 id="modalBaslik">Servis Logları</h3>
      <button type="button" onclick="closeLog()">Kapat</button>
    </div>
    <div class="konsol" id="logKonsol">Yükleniyor...</div>
  </dialog>

  <script>
    const SERVIS_TANIMLARI = {
      sunucu: { ad: "Zirve Web Platformu", aciklama: "Yeni nesil True-ATH ve Multi-Bagger araştırma platformu sunucusu (Port 8795)" },
      tunel: { ad: "Cloudflare İnternet Tüneli", aciklama: "Platformu dış dünyadan (telefondan/tabletten) erişilebilir kılan canlı HTTPS tüneli" },
      tarama: { ad: "Zirve Tarama Motoru", aciklama: "Finviz ve Yahoo Finance üzerinden tüm zamanların zirvesindeki hisseleri tarar" },
      eski_sunucu: { ad: "Eski Platform (Port 8790)", aciklama: "Önceki masaüstü sürümünün arka plan servisi" }
    };

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
        const t = SERVIS_TANIMLARI[s.id] || { ad: s.id, aciklama: "" };
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

        eylemler += `<button type="button" onclick="openLog('${s.id}', '${t.ad}')">Loglar</button>`;

        return `
          <div class="servis-kart">
            <div>
              <div class="kart-ust">
                <span class="servis-ad">${t.ad}</span>
                ${durumRozeti}
              </div>
              <p class="servis-aciklama">${t.aciklama}</p>
            </div>
            ${urlBlok}
            <div class="eylemler">${eylemler}</div>
          </div>
        `;
      }).join("");
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
      for (const id of ["sunucu", "tunel"]) {
        await doAction(id, endpoint);
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
        pass  # Konsolu temiz tut

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
            servisler = [get_service_status(k) for k in ["sunucu", "tunel", "tarama", "eski_sunucu"]]
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
