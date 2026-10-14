import socket

import pytest

import scraper


def fake_dns(ip):
    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
    return getaddrinfo


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254"])
def test_private_and_internal_addresses_are_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns(ip))
    with pytest.raises(scraper.ScrapeError):
        scraper._validate_url("http://internal.example")


def test_public_address_is_allowed_and_https_is_added(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns("93.184.216.34"))
    assert scraper._validate_url("example.com") == "https://example.com"


def test_non_http_schemes_are_rejected():
    with pytest.raises(scraper.ScrapeError):
        scraper._validate_url("ftp://example.com")


def test_unresolvable_domain_gives_a_clear_error(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(scraper.ScrapeError, match="resolve"):
        scraper._validate_url("nope.example")


HTML = """<html><head><title>Ember and Oak</title>
<meta name="description" content="Small-batch coffee.">
<link rel="stylesheet" href="/site.css"><style>:root{--brand:#b4531f}</style></head>
<body><h1>Coffee worth waking up for</h1><h2>Our roasts</h2>
<p>This paragraph is long enough to be kept by the scraper.</p><p>tiny</p>
<img src="/hero.jpg"><script>var secret = 1;</script></body></html>"""


def test_scrape_extracts_the_parts_the_audit_needs(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns("93.184.216.34"))
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: (HTML, "https://example.com/"))
    page = scraper.scrape("example.com")
    assert page["title"] == "Ember and Oak"
    assert page["meta_description"] == "Small-batch coffee."
    assert page["h1"] == ["Coffee worth waking up for"]
    assert page["paragraphs"] == ["This paragraph is long enough to be kept by the scraper."]
    assert page["images"] == ["https://example.com/hero.jpg"]
    assert page["stylesheets"] == ["https://example.com/site.css"]
    assert "--brand:#b4531f" in page["inline_css"]
