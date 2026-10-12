"""Zirve Platformu'nu başlatır ve tarayıcıda açar.

  python sunucu.py          # sadece bu bilgisayardan: http://127.0.0.1:8790
  python sunucu.py --ag     # aynı Wi-Fi'deki telefon/tablet de açabilir
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser

import uvicorn

from app.api import app


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    default_port = int(os.environ.get("PORT", 8795))
    is_cloud = bool(os.environ.get("PORT"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=default_port)
    ap.add_argument("--ag", action="store_true", default=is_cloud, help="ağdaki/buluttaki cihazların erişimine aç")
    ap.add_argument("--acma", action="store_true", default=is_cloud, help="tarayıcıyı otomatik açma")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    host = "0.0.0.0" if (args.ag or is_cloud) else "127.0.0.1"
    local = f"http://127.0.0.1:{args.port}"
    print(f"Zirve Platformu çalışıyor: {local}")
    if args.ag:
        ip = lan_ip()
        if ip:
            app.state.ag_adresi = f"http://{ip}:{args.port}"
            print(f"Telefondan (aynı Wi-Fi): {app.state.ag_adresi}")
        print("Uyarı: ağ modunda şifre yoktur; yalnızca güvendiğiniz ev ağında kullanın.")
    print("Kapatmak için bu pencereyi kapatın ya da Ctrl+C'ye basın.")
    if not args.acma:
        threading.Timer(1.5, lambda: webbrowser.open(local)).start()
    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
