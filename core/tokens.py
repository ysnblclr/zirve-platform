"""Tasarım belirteçleri (design tokens).

Tek kaynak: web/tokens.json (W3C Design Tokens Community Group biçimi).
- `python -m core.tokens` renk ölçeklerini OKLCH'de yeniden üretir, WCAG kontrastını
  doğrular ve tokens.json'u yazar.
- Sunucu /tokens.css isteğinde tokens.json'dan CSS özel özellikleri üretir.

Renk ölçekleri Radix Colors'ın 12 adımlı yapısını izler:
1–2 uygulama arka planı, 3–5 bileşen arka planı (normal/üzerine gelme/basılı),
6–8 kenarlık (sakin/etkileşimli/güçlü ve odak), 9–10 dolgu (normal/üzerine gelme),
11 düşük kontrastlı metin, 12 yüksek kontrastlı metin.
"""

from __future__ import annotations

import json
import math
import sys

from .paths import WEB

TOKENS_FILE = WEB / "tokens.json"

# Ton aileleri: (ton açısı, 9. adım kroması). Vurgu rengi bilinçli olarak petrol mavisi:
# yapay zekâ sitelerinde sık görülen mavi-mor gradyandan uzak, finans verisine uygun sakin bir ton.
HUES = {
    "gri": (230, 0.012),
    "vurgu": (225, 0.115),
    "olumlu": (150, 0.13),
    "olumsuz": (27, 0.17),
    "uyari": (70, 0.14),
}

# Açık ve koyu temada adım başına açıklık (L) ve kroma çarpanı
LIGHT_L = [0.994, 0.982, 0.958, 0.936, 0.912, 0.884, 0.846, 0.782, 0.53, 0.47, 0.47, 0.25]
# 9. adım (dolgu) iki temada da beyaz metinle ≥ 4.5:1 sağlayacak koyulukta tutulur (Radix'teki gibi).
DARK_L = [0.165, 0.195, 0.235, 0.265, 0.295, 0.335, 0.385, 0.455, 0.53, 0.58, 0.80, 0.95]
CHROMA = [0.04, 0.08, 0.18, 0.26, 0.34, 0.42, 0.52, 0.66, 1.0, 1.0, 0.85, 0.45]


# ----------------------------------------------------------------------------- renk matematiği
def oklch_to_srgb(l: float, c: float, h: float) -> tuple[float, float, float]:
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return tuple(12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055 for x in lin)


def in_gamut(rgb) -> bool:
    return all(-1e-4 <= x <= 1 + 1e-4 for x in rgb)


def fit(l: float, c: float, h: float) -> tuple[float, float, float]:
    """sRGB dışına taşan rengi kromasını düşürerek içeri alır."""
    while c > 0 and not in_gamut(oklch_to_srgb(l, c, h)):
        c -= 0.002
    return l, max(c, 0.0), h


def luminance(rgb) -> float:
    def lin(x):
        x = min(1.0, max(0.0, x))
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1, c2) -> float:
    a, b = luminance(oklch_to_srgb(*c1)), luminance(oklch_to_srgb(*c2))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def hexcode(c) -> str:
    return "#" + "".join(f"{round(min(1, max(0, x)) * 255):02x}" for x in oklch_to_srgb(*c))


# ----------------------------------------------------------------------------- üretim
def scale(hue: float, chroma: float, ls: list[float]) -> list[tuple[float, float, float]]:
    return [fit(l, chroma * k, hue) for l, k in zip(ls, CHROMA)]


def color_token(c) -> dict:
    l, ch, h = c
    return {"$value": {"colorSpace": "oklch", "components": [round(l, 4), round(ch, 4), round(h, 1)],
                       "hex": hexcode(c)}}


WHITE = (1.0, 0.0, 0.0)


def build() -> tuple[dict, list[str]]:
    report = []
    themes = {}
    for theme, ls in (("acik", LIGHT_L), ("koyu", DARK_L)):
        group: dict = {"$type": "color"}
        for name, (hue, chroma) in HUES.items():
            steps = scale(hue, chroma, ls)
            group[name] = {str(i + 1): color_token(c) for i, c in enumerate(steps)}
            # metin kontrastı: 11. adım ≥ 4.5:1, 12. adım ≥ 7:1 (1. ve 2. adım zeminde)
            for bg in (0, 1):
                for step, need in ((10, 4.5), (11, 7.0)):
                    r = contrast(steps[step], steps[bg])
                    report.append(f"{theme:<5} {name:<8} {step + 1:>2}/{bg + 1}: {r:5.2f} (≥{need})"
                                  + ("" if r >= need else "  YETERSİZ"))
            # dolgu (9. adım) üstündeki metin: beyaz yeterliyse beyaz, değilse koyu
            on9 = WHITE if contrast(steps[8], WHITE) >= 4.5 else scale(hue, chroma, LIGHT_L)[11]
            group[name]["dolgu-metni"] = color_token(on9)
            r = contrast(steps[8], on9)
            report.append(f"{theme:<5} {name:<8} 9 üstü metin: {r:5.2f} (≥4.5)" + ("" if r >= 4.5 else "  YETERSİZ"))
            # odak halkası ve kenarlıklar (8. ve 9. adım) zemine karşı ≥ 3:1 (WCAG 1.4.11)
            r = contrast(steps[8], steps[0])
            report.append(f"{theme:<5} {name:<8} 9/1 grafik: {r:5.2f} (≥3.0)" + ("" if r >= 3 else "  YETERSİZ"))
        themes[theme] = group

    tokens = {
        "$description": "Zirve Platformu tasarım belirteçleri. Renkler OKLCH, 12 adımlı ölçek (Radix yapısı). "
                        "Bu dosya core/tokens.py ile üretilir; elle düzenlemeyin.",
        "renk": themes,
        "anlam": {
            "$type": "color",
            "$description": "Bileşenlerin kullandığı anlamsal takma adlar; tema ölçeğine bağlanır.",
            "zemin": {"$value": "{renk.TEMA.gri.1}"},
            "yuzey": {"$value": "{renk.TEMA.gri.2}"},
            "bilesen": {"$value": "{renk.TEMA.gri.3}"},
            "bilesen-uzerinde": {"$value": "{renk.TEMA.gri.4}"},
            "bilesen-secili": {"$value": "{renk.TEMA.gri.5}"},
            "kenar": {"$value": "{renk.TEMA.gri.6}"},
            "kenar-etkilesim": {"$value": "{renk.TEMA.gri.7}"},
            "kenar-guclu": {"$value": "{renk.TEMA.gri.8}"},
            "metin": {"$value": "{renk.TEMA.gri.12}"},
            "metin-ikincil": {"$value": "{renk.TEMA.gri.11}"},
            "vurgu": {"$value": "{renk.TEMA.vurgu.9}"},
            "vurgu-uzerinde": {"$value": "{renk.TEMA.vurgu.10}"},
            "vurgu-metin": {"$value": "{renk.TEMA.vurgu.11}"},
            "vurgu-zemin": {"$value": "{renk.TEMA.vurgu.3}"},
            "vurgu-dolgu-metni": {"$value": "{renk.TEMA.vurgu.dolgu-metni}"},
            "odak": {"$value": "{renk.TEMA.vurgu.9}"},
            "olumlu": {"$value": "{renk.TEMA.olumlu.11}"},
            "olumlu-zemin": {"$value": "{renk.TEMA.olumlu.3}"},
            "olumsuz": {"$value": "{renk.TEMA.olumsuz.11}"},
            "olumsuz-zemin": {"$value": "{renk.TEMA.olumsuz.3}"},
            "uyari": {"$value": "{renk.TEMA.uyari.11}"},
            "uyari-zemin": {"$value": "{renk.TEMA.uyari.3}"},
        },
        "bosluk": {"$type": "dimension", **{k: {"$value": {"value": v, "unit": "rem"}} for k, v in
                                            {"1": 0.25, "2": 0.5, "3": 0.75, "4": 1, "5": 1.5, "6": 2, "7": 3}.items()}},
        "kose": {"$type": "dimension", **{k: {"$value": {"value": v, "unit": "rem"}} for k, v in
                                          {"kucuk": 0.25, "orta": 0.375, "buyuk": 0.625}.items()}},
        "yazi": {
            "aile": {
                "$type": "fontFamily",
                "govde": {"$value": ["Segoe UI", "system-ui", "-apple-system", "Roboto", "Helvetica Neue", "sans-serif"]},
                "baslik": {"$value": ["Palatino Linotype", "Book Antiqua", "Iowan Old Style", "Palatino", "Georgia", "serif"]},
                "sabit": {"$value": ["Cascadia Mono", "Consolas", "ui-monospace", "monospace"]},
            },
            "boyut": {"$type": "dimension", **{k: {"$value": {"value": v, "unit": "rem"}} for k, v in
                                               {"kucuk": 0.8125, "normal": 0.9375, "orta": 1.0625, "buyuk": 1.375,
                                                "baslik": 1.875, "dev": 2.5}.items()}},
        },
        "hedef": {"$type": "dimension", "$description": "WCAG 2.5.8: en küçük tıklama hedefi",
                  "en-kucuk": {"$value": {"value": 1.5, "unit": "rem"}},
                  "rahat": {"$value": {"value": 2.75, "unit": "rem"}}},
        "sure": {"$type": "duration", "kisa": {"$value": {"value": 120, "unit": "ms"}},
                 "orta": {"$value": {"value": 240, "unit": "ms"}}},
    }
    return tokens, report


# ----------------------------------------------------------------------------- CSS çıktısı
def _css_value(v) -> str:
    if isinstance(v, dict) and v.get("colorSpace") == "oklch":
        l, c, h = v["components"]
        return f"oklch({l * 100:.2f}% {c:.4f} {h:.1f})"
    if isinstance(v, dict) and "unit" in v:
        return f"{v['value']}{v['unit']}"
    if isinstance(v, list):
        return ", ".join(f'"{x}"' if " " in x else x for x in v)
    return str(v)


def _flat(node: dict, prefix: str = "") -> dict[str, str]:
    out = {}
    for k, v in node.items():
        if k.startswith("$"):
            continue
        name = f"{prefix}-{k}" if prefix else k
        if isinstance(v, dict) and "$value" in v:
            out[name] = v["$value"]
        elif isinstance(v, dict):
            out.update(_flat(v, name))
    return out


def to_css(tokens: dict) -> str:
    def resolve(val, theme):
        if isinstance(val, str) and val.startswith("{"):
            path = val.strip("{}").replace("TEMA", theme).split(".")
            node = tokens
            for p in path:
                node = node[p]
            return _css_value(node["$value"])
        return _css_value(val)

    shared = {k: v for k, v in _flat({x: tokens[x] for x in tokens if x not in ("renk", "anlam")}).items()}
    lines = ["/* Bu dosya web/tokens.json'dan üretilir. */", ":root {"]
    lines += [f"  --{k}: {_css_value(v)};" for k, v in shared.items()]
    lines.append("  color-scheme: light dark;")
    lines.append("}")

    def theme_block(theme: str) -> list[str]:
        out = [f"  --{k}: {_css_value(v)};" for k, v in _flat(tokens["renk"][theme], "renk").items()]
        out += [f"  --{k}: {resolve(v, theme)};" for k, v in _flat(tokens["anlam"]).items()]
        return out

    light, dark = theme_block("acik"), theme_block("koyu")
    lines += [":root, :root[data-tema=\"acik\"] {", "  color-scheme: light;", *light, "}"]
    lines += ["@media (prefers-color-scheme: dark) {", "  :root:not([data-tema=\"acik\"]) {", "    color-scheme: dark;",
              *("  " + x for x in dark), "  }", "}"]
    lines += [":root[data-tema=\"koyu\"] {", "  color-scheme: dark;", *dark, "}"]
    return "\n".join(lines) + "\n"


_css_cache: tuple[float, str] | None = None


def css() -> str:
    """tokens.json değiştiyse CSS'i yeniden üretir."""
    global _css_cache
    mtime = TOKENS_FILE.stat().st_mtime
    if not _css_cache or _css_cache[0] != mtime:
        _css_cache = (mtime, to_css(json.loads(TOKENS_FILE.read_text(encoding="utf-8"))))
    return _css_cache[1]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tokens, report = build()
    TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report))
    bad = [r for r in report if "YETERSİZ" in r]
    print(f"\n{TOKENS_FILE} yazıldı. Yetersiz kontrast: {len(bad)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
