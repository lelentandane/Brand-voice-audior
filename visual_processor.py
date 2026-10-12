"""visual_processor.py - extract brand colors from CSS and page images.

Scope: returns raw color signals and simple metrics only.
Scoring and interpretation belong in ai_analyzer.py.
"""

import colorsys
import io
import re
from collections import Counter

import requests
from colorthief import ColorThief
from PIL import Image

from scraper import HEADERS, TIMEOUT, ScrapeError, _validate_url

Image.MAX_IMAGE_PIXELS = 20_000_000  # guard against decompression bombs

MAX_STYLESHEETS = 5
MAX_CSS_BYTES = 500 * 1024
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MIN_IMAGE_SIDE = 50          # skip icons and tracking pixels
MERGE_DISTANCE = 30          # RGB distance under which colors count as one
AGREEMENT_DISTANCE = 60      # RGB distance for "image color matches CSS color"
TOKEN_WEIGHT = 3             # CSS custom properties (--primary) are design tokens
SOURCE_WEIGHT = {"css": 0.7, "image": 0.3}

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
DECL_RE = re.compile(r"([\w-]+)\s*:\s*([^;{}]+)")
HEX_RE = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})"
    r"\s*(?:[,/]\s*([\d.]+%?))?\s*\)", re.I)
HSL_RE = re.compile(
    r"hsla?\(\s*(-?[\d.]+)(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%"
    r"\s*(?:[,/]\s*([\d.]+%?))?\s*\)", re.I)


# ---------- helpers ----------

def _safe_get(url: str, max_bytes: int, truncate: bool = False):
    """Fetch bytes from a public URL with a size cap. Returns None on failure."""
    try:
        url = _validate_url(url)
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        _validate_url(resp.url)  # re-check after redirects
        data = b""
        for chunk in resp.iter_content(8192):
            data += chunk
            if len(data) > max_bytes:
                return data[:max_bytes] if truncate else None
        return data
    except (requests.RequestException, ScrapeError):
        return None


def _to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hsl(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return h * 360, s, l


def _is_neutral(rgb) -> bool:
    """Near-white, near-black, or grey: not a brand color on its own."""
    _, s, l = _hsl(rgb)
    return s < 0.12 or l > 0.95 or l < 0.08


def _distance(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _alpha(raw) -> float:
    if raw is None:
        return 1.0
    return float(raw[:-1]) / 100 if raw.endswith("%") else float(raw)


def _parse_colors(value: str) -> list:
    """Return RGB tuples for every hex/rgb()/hsl() color in a CSS value.
    Mostly-transparent colors are skipped. Named colors (e.g. 'red') are not parsed."""
    found = []
    for m in HEX_RE.finditer(value):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        alpha = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        if alpha >= 0.5:
            found.append(rgb)
    for m in RGB_RE.finditer(value):
        rgb = tuple(min(int(m.group(i)), 255) for i in (1, 2, 3))
        if _alpha(m.group(4)) >= 0.5:
            found.append(rgb)
    for m in HSL_RE.finditer(value):
        h = (float(m.group(1)) / 360) % 1
        s = min(float(m.group(2)), 100) / 100
        l = min(float(m.group(3)), 100) / 100
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        if _alpha(m.group(4)) >= 0.5:
            found.append((round(r * 255), round(g * 255), round(b * 255)))
    return found


# ---------- extraction ----------

def extract_css_colors(css_text: str) -> Counter:
    """Count colors used in color-bearing CSS properties.
    Custom properties (--brand: #...) are weighted higher as design tokens."""
    counts = Counter()
    css_text = COMMENT_RE.sub("", css_text)
    for prop, value in DECL_RE.findall(css_text):
        prop = prop.lower()
        if prop.startswith("--"):
            weight = TOKEN_WEIGHT
        elif prop in ("color", "fill", "stroke") or prop.startswith(
                ("background", "border", "outline")):
            weight = 1
        else:
            continue  # ignore shadows, filters, etc.
        for rgb in _parse_colors(value):
            counts[rgb] += weight
    return counts


def extract_image_colors(image_urls: list) -> tuple:
    """Return (Counter of chromatic palette colors, number of images analyzed)."""
    counts = Counter()
    used = 0
    for url in image_urls:
        if used >= MAX_IMAGES:
            break
        data = _safe_get(url, MAX_IMAGE_BYTES)
        if not data:
            continue
        try:
            with Image.open(io.BytesIO(data)) as img:
                if min(img.size) < MIN_IMAGE_SIDE:
                    continue
                img = img.convert("RGB")
                img.thumbnail((200, 200))
                buf = io.BytesIO()
                img.save(buf, "PNG")
            buf.seek(0)
            palette = ColorThief(buf).get_palette(color_count=4, quality=5)
        except Exception:
            # Unsupported formats (SVG, corrupt files) or ColorThief edge cases:
            # skip the image rather than fail the whole audit.
            continue
        used += 1
        for rgb in palette:
            if not _is_neutral(rgb):
                counts[rgb] += 1
    return counts, used


# ---------- combining ----------

def _normalise(counter: Counter) -> dict:
    total = sum(counter.values())
    return {k: v / total for k, v in counter.items()} if total else {}


def merge_palette(css_counts: Counter, image_counts: Counter, top_n: int = 6) -> list:
    """Blend CSS and image colors into one palette, merging near-identical shades."""
    entries = []
    for source, counts in (("css", css_counts), ("image", image_counts)):
        for rgb, share in _normalise(counts).items():
            entries.append((rgb, share * SOURCE_WEIGHT[source], source))
    entries.sort(key=lambda e: e[1], reverse=True)

    clusters = []
    for rgb, score, source in entries:
        for c in clusters:
            if _distance(rgb, c["rgb"]) < MERGE_DISTANCE:
                c["score"] += score
                c["sources"].add(source)
                break
        else:
            clusters.append({"rgb": rgb, "score": score, "sources": {source}})

    clusters.sort(key=lambda c: c["score"], reverse=True)
    return [
        {"hex": _to_hex(c["rgb"]), "rgb": list(c["rgb"]),
         "score": round(c["score"], 3), "sources": sorted(c["sources"])}
        for c in clusters[:top_n]
    ]


def _top(counter: Counter, n: int) -> list:
    return [{"hex": _to_hex(rgb), "weight": w} for rgb, w in counter.most_common(n)]


def _metrics(palette: list, css_counts: Counter, image_counts: Counter) -> dict:
    """Raw signals for the analyzer. No scoring here."""
    hues, sats = [], []
    for c in palette:
        h, s, _ = _hsl(tuple(c["rgb"]))
        hues.append(h)
        sats.append(s)

    agreement = None
    if css_counts and image_counts:
        matched = sum(
            1 for img_rgb in image_counts
            if any(_distance(img_rgb, css_rgb) < AGREEMENT_DISTANCE for css_rgb in css_counts)
        )
        agreement = round(matched / len(image_counts), 2)

    return {
        "palette_size": len(palette),
        "hue_families": len({int(h // 30) for h in hues}),  # distinct 30-degree hue bins
        "avg_saturation": round(sum(sats) / len(sats), 2) if sats else None,
        "css_image_agreement": agreement,  # share of image colors that resemble a CSS color
    }


# ---------- public entry point ----------

def analyze_visuals(stylesheets: list, inline_css: str, image_urls: list) -> dict:
    css_text = inline_css or ""
    fetched = 0
    for href in stylesheets[:MAX_STYLESHEETS]:
        data = _safe_get(href, MAX_CSS_BYTES, truncate=True)
        if data:
            css_text += "\n" + data.decode("utf-8", errors="replace")
            fetched += 1

    all_css = extract_css_colors(css_text)
    css_counts = Counter({k: v for k, v in all_css.items() if not _is_neutral(k)})
    neutral_counts = Counter({k: v for k, v in all_css.items() if _is_neutral(k)})

    image_counts, images_used = extract_image_colors(image_urls)
    palette = merge_palette(css_counts, image_counts)

    return {
        "brand_palette": palette,
        "css_colors": _top(css_counts, 8),
        "image_colors": _top(image_counts, 8),
        "neutrals": _top(neutral_counts, 3),  # keeps black/white brands from looking empty
        "metrics": _metrics(palette, css_counts, image_counts),
        "sources": {"stylesheets_fetched": fetched, "images_analyzed": images_used},
    }


if __name__ == "__main__":
    import json
    import sys

    from scraper import scrape

    page = scrape(sys.argv[1] if len(sys.argv) > 1 else "https://example.com")
    result = analyze_visuals(page["stylesheets"], page["inline_css"], page["images"])
    print(json.dumps(result, indent=2))
