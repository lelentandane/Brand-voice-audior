import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

PAGE = {
    "url": "https://example.com/", "title": "Ember and Oak | Small-batch specialty coffee",
    "meta_description": "", "h1": ["Coffee"], "h2": ["A", "B"],
    "paragraphs": ["word " * 320], "images": [], "stylesheets": [], "inline_css": "",
}
VOICE = {"detected_tone": "warm", "consistency_score": 80, "guideline_adherence_score": None,
         "voice_score": 80, "summary": "ok", "strengths": [],
         "issues": [{"issue": "Too formal", "evidence": "x", "fix": "Say it simply."}]}


@pytest.fixture(autouse=True)
def reset_limiter():
    main._hits.clear()
    yield
    main._hits.clear()


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(main.scraper, "scrape", lambda url: PAGE)
    monkeypatch.setattr(main.ai_analyzer, "analyze_voice", lambda page, g: VOICE)
    monkeypatch.setattr(main.visual_processor, "analyze_visuals", lambda *a: None)


def test_status_reports_whether_a_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/api/status").json() == {"ai_configured": False}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert client.get("/api/status").json() == {"ai_configured": True}


def test_sample_report_needs_no_key_and_has_the_real_shape(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = client.get("/api/sample").json()
    assert body["is_sample"] is True
    assert 0 <= body["brand_health"]["overall"] <= 100
    assert body["priorities"] and body["voice"]["issues"] and body["seo"]["checks"]


def test_audit_without_a_key_explains_what_to_do(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post("/audit", json={"url": "example.com"})
    assert res.status_code == 503
    assert "sample" in res.json()["detail"].lower()


def test_audit_returns_a_full_report(live):
    res = client.post("/audit", json={"url": "example.com", "keywords": ["coffee"]})
    assert res.status_code == 200
    body = res.json()
    assert body["is_sample"] is False
    assert body["brand_health"]["components"]["visual"] is None
    assert body["priorities"][0]["area"] == "Voice"


def test_scrape_errors_become_400(live, monkeypatch):
    def boom(url):
        raise main.scraper.ScrapeError("That address is not allowed.")
    monkeypatch.setattr(main.scraper, "scrape", boom)
    res = client.post("/audit", json={"url": "localhost"})
    assert res.status_code == 400


def test_page_with_no_text_becomes_422(live, monkeypatch):
    monkeypatch.setattr(main.scraper, "scrape", lambda url: {**PAGE, "paragraphs": [], "h1": []})
    assert client.post("/audit", json={"url": "example.com"}).status_code == 422


def test_rate_limit_returns_429(live, monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_PER_HOUR", 1)
    assert client.post("/audit", json={"url": "example.com"}).status_code == 200
    assert client.post("/audit", json={"url": "example.com"}).status_code == 429
