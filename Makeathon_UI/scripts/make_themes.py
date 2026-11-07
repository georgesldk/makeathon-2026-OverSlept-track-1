"""Builds src/themes.css: the colour palettes for dark mode, high contrast and colour-blind safe mode.

Every colour in src/index.css is a token named after its light colour and its role, e.g.
var(--t-fg-17241c) or var(--t-bg-fbfaf5f5) (8 digits = with alpha). Run this script after adding
colours to index.css: it turns new literal colours into tokens and rewrites themes.css.
    python3 scripts/make_themes.py
"""
import math, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS, OUT = ROOT / "src" / "index.css", ROOT / "src" / "themes.css"
NAMED = {"white": "ffffff", "black": "000000"}
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b")
TOKEN = re.compile(r"--t-(fg|bg|line|shadow)-([0-9a-f]{6,8})\b")


def to_hex(lit):
    lit = lit.strip().lower()
    if lit in NAMED: return NAMED[lit]
    if lit.startswith("#"):
        h = lit[1:]
        if len(h) in (3, 4): h = "".join(c * 2 for c in h)
        return h[:6] + ("" if len(h) == 6 or h[6:] == "ff" else h[6:])
    nums = [float(x) for x in re.findall(r"[\d.]+", lit)]
    r, g, b = (round(x) for x in nums[:3])
    a = nums[3] if len(nums) > 3 else 1
    return f"{r:02x}{g:02x}{b:02x}" + ("" if a >= 1 else f"{round(a * 255):02x}")


def role(prop, block=""):
    p = prop.lower()
    # SVG text: the fill is the text colour and a stroke drawn under it (paint-order) is a halo, i.e. background
    if p == "stroke" and "paint-order" in block: return "bg"
    if p == "fill" and re.search(r"(^|[;{\s])font(-size|-family)?\s*:", block): return "fg"
    if p.startswith("--"):
        return "line" if re.search(r"edge|stroke|grid|line|border", p) else "bg" if re.search(r"bg|background|sea|fill|surface", p) else "fg"
    if p.startswith("background") or p == "fill": return "bg"
    if re.match(r"(border|outline|stroke|column-rule|text-decoration)", p): return "line"
    if p in ("box-shadow", "text-shadow", "filter"): return "shadow"
    return "fg"


def tokenise(css):
    def block(m):
        body = m.group(1)
        def decl(d):
            prop, val = d.group(1), d.group(2)
            if prop.startswith("--t-"): return d.group(0)
            rl = role(prop, body)
            val = COLOR.sub(lambda c: f"var(--t-{rl}-{to_hex(c.group(0))})", val)
            # existing tokens get the role this declaration implies (so role rules can be refined later)
            val = re.sub(r"var\(--t-(?:fg|bg|line|shadow)-([0-9a-f]{6,8})\)", lambda t: f"var(--t-{rl}-{t.group(1)})", val)
            return f"{prop}:{val}"
        return "{" + re.sub(r"([\w-]+)\s*:([^;{}]+)", decl, body) + "}"
    return re.sub(r"\{([^{}]*)\}", block, css)


# --- colour maths (sRGB <-> OKLCH) ---
def lin(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def gam(c): return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

def to_oklch(r, g, b):
    r, g, b = lin(r), lin(g), lin(b)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360

def from_oklch(L, C, h):
    for _ in range(40):  # reduce chroma until the colour fits in sRGB
        A, B = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
        l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
        m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
        s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3
        rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
               -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
               -0.0041960863 * l - 0.7034186147 * m + 1.7076953130 * s)
        if all(-1e-4 <= c <= 1.0001 for c in rgb): break
        C *= 0.9
    return tuple(min(255, max(0, round(gam(min(1, max(0, c))) * 255))) for c in rgb)


def contrast(rl, L, C, h):
    if rl == "fg": return (1.0 if L > 0.7 else min(L * 0.55, 0.24)), C, h
    if rl == "bg": return (1 - (1 - L) * 0.35 if L > 0.7 else min(L * 0.6, 0.27)), C, h
    if rl == "line": return (0.32 if L > 0.5 else L * 0.6), C, h
    return L, C, h

def colourblind(rl, L, C, h):
    """Red–green safe: greens become blue, reds become vermillion, browns/ochres become amber (Okabe–Ito hues)."""
    if C < 0.015: return L, C, h
    strong = C >= 0.03 and 0.15 < L < 0.92   # accents, not near-white tints or near-black text
    if 95 <= h < 215: return L, (max(C * 1.8, 0.09) if strong else max(C, 0.025)), 255   # greens -> blue
    if h < 50 or h >= 330: return L, (max(C * 1.4, 0.13) if strong else C), 35            # reds -> vermillion
    if 50 <= h < 95: return min(L + 0.05, 1), (max(C * 1.3, 0.1) if strong else C), 85     # ochre -> amber
    return L, C, h

def dark(rl, L, C, h, hc):
    lo, hi = (0.06, 1.0) if hc else (0.15, 0.95)
    return min(hi, max(lo, 1.17 - 1.03 * L)), C * (0.85 if rl == "bg" else 1), h


def value(rl, hexa, theme, vision):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))
    a = int(hexa[6:8], 16) / 255 if len(hexa) == 8 else 1
    L, C, h = to_oklch(r, g, b)
    if vision == "cvd": L, C, h = colourblind(rl, L, C, h)
    if vision == "contrast":
        L, C, h = contrast(rl, L, C, h)
        if a < 1 and rl != "shadow": a = min(1, a + 0.4)
    if theme == "dark":
        if rl == "shadow" and L < 0.6: return f"rgba(0,0,0,{min(0.7, a * 2.2):.2f})"
        L, C, h = dark(rl, L, C, h, vision == "contrast")
    R, G, B = from_oklch(L, C, h)
    return f"#{R:02x}{G:02x}{B:02x}" if a >= 1 else f"rgba({R},{G},{B},{a:.2f})"


def main():
    css = tokenise(CSS.read_text(encoding="utf-8"))
    CSS.write_text(css, encoding="utf-8")
    tokens = sorted(set(TOKEN.findall(css)))
    blocks = [(":root", "light", ""), (':root[data-theme="dark"]', "dark", ""),
              (':root[data-vision="contrast"]', "light", "contrast"), (':root[data-theme="dark"][data-vision="contrast"]', "dark", "contrast"),
              (':root[data-vision="cvd"]', "light", "cvd"), (':root[data-theme="dark"][data-vision="cvd"]', "dark", "cvd")]
    out = ["/* Generated by scripts/make_themes.py from the colours in index.css. Do not edit by hand. */"]
    for sel, theme, vision in blocks:
        extra = " color-scheme: dark;" if theme == "dark" else ""
        out.append(sel + " {" + extra + "\n" + "\n".join(f"  --t-{rl}-{hx}: {value(rl, hx, theme, vision)};" for rl, hx in tokens) + "\n}")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(tokens)} colour tokens, {len(blocks)} palettes -> {OUT.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
