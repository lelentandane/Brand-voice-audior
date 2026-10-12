"""scraper.py - fetch a page and extract SEO, text, and image data."""

import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BrandAuditorBot/1.0)"}
TIMEOUT = 10
MAX_BYTES = 3 * 1024 * 1024  # 3 MB cap on downloaded HTML


class ScrapeError(Exception):
    pass


def _validate_url(url: str) -> str:
    """Allow only public http(s) URLs. Blocks localhost/private IPs (SSRF)."""
    if not urlparse(url).scheme:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScrapeError("URL must be a valid http(s) address.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ScrapeError("Could not resolve that domain.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise ScrapeError("That address is not allowed.")
    return url


def _fetch_html(url: str) -> tuple[str, str]:
    """Download HTML with a size cap. Returns (html, final_url)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ScrapeError(f"Could not fetch the page: {e}")

    # Re-validate after redirects so a redirect can't reach an internal host.
    _validate_url(resp.url)

    if "text/html" not in resp.headers.get("Content-Type", ""):
        raise ScrapeError("URL did not return an HTML page.")

    content = b""
    for chunk in resp.iter_content(8192):
        content += chunk
        if len(content) > MAX_BYTES:
            break
    return content.decode(resp.encoding or "utf-8", errors="replace"), resp.url


def _texts(soup: BeautifulSoup, tag: str, min_len: int = 1) -> list[str]:
    out = []
    for el in soup.find_all(tag):
        text = el.get_text(" ", strip=True)
        if len(text) >= min_len:
            out.append(text)
    return out


def scrape(url: str) -> dict:
    """Return page title, meta description, headings, paragraphs, images."""
    url = _validate_url(url)
    html, final_url = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # Collect CSS sources before <style> tags are stripped (used for colors).
    stylesheets = []
    for link in soup.find_all("link", href=True):
        if "stylesheet" in (link.get("rel") or []):
            href = urljoin(final_url, link["href"])
            if href not in stylesheets:
                stylesheets.append(href)
    inline_css = "\n".join(s.get_text() for s in soup.find_all("style"))

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    meta_desc = soup.find("meta", attrs={"name": "description"})
    og_image = soup.find("meta", property="og:image")

    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src or src.startswith("data:"):
            continue
        full = urljoin(final_url, src)
        if full not in images:
            images.append(full)
    if og_image and og_image.get("content"):
        og = urljoin(final_url, og_image["content"])
        if og not in images:
            images.insert(0, og)

    return {
        "url": final_url,
        "title": soup.title.get_text(strip=True) if soup.title else "",
        "meta_description": (meta_desc.get("content", "").strip()
                             if meta_desc else ""),
        "h1": _texts(soup, "h1"),
        "h2": _texts(soup, "h2"),
        "paragraphs": _texts(soup, "p", min_len=20),  # skip tiny fragments
        "images": images,
        "stylesheets": stylesheets,
        "inline_css": inline_css,
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    try:
        print(json.dumps(scrape(target), indent=2, ensure_ascii=False))
    except ScrapeError as e:
        print(f"Error: {e}")
