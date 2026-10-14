"""main.py - FastAPI app. Run from backend/: uvicorn main:app --reload"""

import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ai_analyzer
import scoring
import scraper
import sample_data
import visual_processor

app = FastAPI(title="Brand Voice & Visual Style Auditor")

RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "20"))
_hits: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(client: str) -> None:
    """In-memory sliding window per client address. Resets on restart."""
    now = time.time()
    window = _hits[client]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Limit of {RATE_LIMIT_PER_HOUR} audits per hour reached. Try again later.")
    window.append(now)


class AuditRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    brand_tone: Optional[str] = Field(None, max_length=200,
                                      description="e.g. 'warm, playful, premium'")
    keywords: list[str] = Field(default_factory=list, max_length=20)
    guidelines: Optional[str] = Field(None, max_length=3000,
                                      description="Free-text brand voice guidelines")


@app.get("/api/status")
def status():
    """Tells the dashboard whether live audits are available."""
    return {"ai_configured": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.get("/api/sample")
def sample():
    """A complete example report. Needs no API key and makes no network calls."""
    return sample_data.sample_report()


@app.post("/audit")
def audit(req: AuditRequest, request: Request):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Live audits need an ANTHROPIC_API_KEY on the server. "
                   "Open the sample audit to see a full report.")
    _check_rate_limit(request.client.host if request.client else "unknown")

    # 1. Scrape
    try:
        page = scraper.scrape(req.url)
    except scraper.ScrapeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not page["paragraphs"] and not page["h1"]:
        raise HTTPException(
            status_code=422,
            detail="No readable text found. The site may render its content with JavaScript.")

    guidelines = {"brand_tone": req.brand_tone, "keywords": req.keywords,
                  "guidelines": req.guidelines}
    warnings = []

    # 2. Voice (LLM) and visuals (network + image work) run in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        voice_future = pool.submit(ai_analyzer.analyze_voice, page, guidelines)
        visual_future = pool.submit(
            visual_processor.analyze_visuals,
            page["stylesheets"], page["inline_css"], page["images"])

        try:
            voice = voice_future.result()
        except ai_analyzer.AnalysisError as e:
            raise HTTPException(status_code=502, detail=str(e))

        try:
            visuals = visual_future.result()
        except Exception:
            # A visual failure should not sink the whole audit.
            visuals = None
            warnings.append("Visual analysis failed and was left out of the score.")

    # 3. SEO (deterministic) and scoring
    seo = ai_analyzer.seo_audit(page, req.keywords)
    visual_score = scoring.visual_score(visuals)
    if visuals is not None and visual_score is None:
        warnings.append("No chromatic brand colors were found, so visuals were not scored.")

    return {
        "url": page["url"],
        "is_sample": False,
        "page": {"title": page["title"], "meta_description": page["meta_description"],
                 "word_count": seo["word_count"], "image_count": len(page["images"])},
        "brand_health": scoring.health_score(voice["voice_score"], seo["score"], visual_score),
        "priorities": scoring.priorities(voice, seo),
        "voice": voice,
        "seo": seo,
        "visual": visuals,
        "warnings": warnings,
    }


# Serve the dashboard from the same origin (avoids CORS). Must stay last.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
