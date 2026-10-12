"""Platform açık olmadan komut satırından tarama. Sonuçlar platformun veritabanına yazılır.

  python tara.py                 # varsayılan ayarlarla tara
  python tara.py --mod genis     # zirveye %5 yakın olanlar da

Windows Görev Zamanlayıcı ile her akşam çalıştırılabilir (README'ye bakın).
"""

from __future__ import annotations

import argparse
import sys

from core import db, tarama


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod", choices=["zirve", "genis"])
    ap.add_argument("--haber", type=int)
    ap.add_argument("--kucuk", action="store_true", default=None)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    db.init()
    opts = {k: v for k, v in vars(args).items() if v is not None}
    scan_id = tarama.run_scan(opts, "komut", lambda m, f=None: print(m, flush=True))
    print(f"\nTarama #{scan_id} kaydedildi. İlk 15 hisse:")
    for it in db.get_results(scan_id, "Hisse", 15):
        pu = f"%{it['p_up'] * 100:.0f}" if it.get("p_up") is not None else "-"
        print(f"  {it['sira']:>2}. {it['sembol']:<6} {it['puan']:>5.1f}  ≥+%50 {pu:>4}  {it['risk']:<7} {it['endustri'][:32]}")


if __name__ == "__main__":
    main()
