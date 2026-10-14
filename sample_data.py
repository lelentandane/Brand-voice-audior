"""sample_data.py - a built-in example report so the dashboard works with no API key.

The brand is fictional. The report has the same shape as a real /audit response.
"""

import scoring


def sample_report() -> dict:
    voice = {
        "detected_tone": "warm, but drifts formal",
        "consistency_score": 68,
        "guideline_adherence_score": 61,
        "voice_score": 66,
        "summary": ("The homepage opens in a friendly, sensory voice, then shifts into "
                    "corporate wording in the wholesale and shipping sections. The "
                    "guidelines ask for short sentences, and several paragraphs run long."),
        "strengths": [
            "The hero copy is specific and sensory (roast, steam, the first pour).",
            "Calls to action use plain verbs such as \"Pick your roast\".",
        ],
        "issues": [
            {"issue": "Tone turns corporate in the wholesale section",
             "evidence": "We leverage best-in-class sourcing partnerships to deliver value",
             "fix": "Say it the way the hero does: \"We buy straight from four farms we have visited.\""},
            {"issue": "Sentences are longer than the guidelines allow",
             "evidence": "Our small-batch approach means that every single roast is profiled, tasted and logged before it ever reaches your door",
             "fix": "Split it: \"Every roast is profiled and tasted. Then we log it. Then it ships.\""},
            {"issue": "Generic filler weakens the brand promise",
             "evidence": "We are passionate about quality coffee",
             "fix": "Replace it with one concrete detail, such as the roast date printed on every bag."},
        ],
    }
    checks = [
        {"check": "Title length is 30-60 characters", "passed": True, "detail": "47 characters",
         "advice": "Rewrite the page title so it is 30 to 60 characters and names the brand and what it offers."},
        {"check": "Meta description is 70-160 characters", "passed": False, "detail": "missing",
         "advice": "Add a meta description of 70 to 160 characters that says what the page offers and why to click."},
        {"check": "Exactly one H1", "passed": True, "detail": "1 found",
         "advice": "Use a single H1 that states the page's main promise, and turn any other H1s into H2s."},
        {"check": "Has H2 subheadings", "passed": True, "detail": "4 found",
         "advice": "Break the page into sections with at least two H2 subheadings that describe each section."},
        {"check": "Body copy of at least 300 words", "passed": True, "detail": "412 words",
         "advice": "Add body copy until the page has at least 300 words, focused on what visitors want to know."},
        {"check": "Target keywords appear in title, meta or headings", "passed": False,
         "detail": "1 of 2 found (specialty coffee)",
         "advice": "Work your target keywords into the page title, meta description and headings."},
    ]
    seo = {"score": 67, "checks": checks, "word_count": 412}
    visual = {
        "brand_palette": [
            {"hex": "#b4531f", "weight": 0.38, "sources": ["css", "image"]},
            {"hex": "#2f4a3a", "weight": 0.27, "sources": ["css"]},
            {"hex": "#e9b44c", "weight": 0.19, "sources": ["css", "image"]},
        ],
        "css_colors": [], "image_colors": [],
        "neutrals": [{"hex": "#1c1a17", "weight": 6}, {"hex": "#f4efe6", "weight": 5}],
        "metrics": {"palette_size": 3, "hue_families": 3, "avg_saturation": 0.52,
                    "css_image_agreement": 0.67},
        "sources": {"stylesheets_fetched": 2, "images_analyzed": 4},
    }
    visual_score = scoring.visual_score(visual)
    return {
        "is_sample": True,
        "url": "https://emberandoak.example/",
        "page": {"title": "Ember & Oak | Small-batch specialty coffee roasters",
                 "meta_description": "", "word_count": 412, "image_count": 6},
        "brand_health": scoring.health_score(voice["voice_score"], seo["score"], visual_score),
        "priorities": scoring.priorities(voice, seo),
        "voice": voice,
        "seo": seo,
        "visual": visual,
        "warnings": [],
    }
