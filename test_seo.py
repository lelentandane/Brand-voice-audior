import ai_analyzer


def page(**overrides):
    base = {
        "title": "Ember and Oak | Small-batch specialty coffee",
        "meta_description": "Small-batch specialty coffee roasted weekly and shipped fresh to your door across the country.",
        "h1": ["Coffee worth waking up for"],
        "h2": ["Our roasts", "Our farms"],
        "paragraphs": ["word " * 320],
    }
    base.update(overrides)
    return base


def by_name(result):
    return {c["check"]: c for c in result["checks"]}


def test_good_page_passes_every_check():
    result = ai_analyzer.seo_audit(page())
    assert result["score"] == 100
    assert all(c["passed"] for c in result["checks"])


def test_missing_meta_description_fails_and_says_missing():
    result = ai_analyzer.seo_audit(page(meta_description=""))
    check = by_name(result)["Meta description is 70-160 characters"]
    assert not check["passed"] and check["detail"] == "missing"


def test_two_h1s_fail():
    result = ai_analyzer.seo_audit(page(h1=["One", "Two"]))
    assert not by_name(result)["Exactly one H1"]["passed"]


def test_short_copy_fails_word_count():
    result = ai_analyzer.seo_audit(page(paragraphs=["only a few words here"]))
    assert not by_name(result)["Body copy of at least 300 words"]["passed"]


def test_keyword_check_only_appears_when_keywords_are_given():
    assert len(ai_analyzer.seo_audit(page())["checks"]) == 5
    with_kw = ai_analyzer.seo_audit(page(), ["specialty coffee", "espresso"])
    assert len(with_kw["checks"]) == 6
    assert by_name(with_kw)["Target keywords appear in title, meta or headings"]["passed"]


def test_every_check_has_advice():
    result = ai_analyzer.seo_audit(page(), ["coffee"])
    assert all(c["advice"] for c in result["checks"])


def test_same_page_always_gets_the_same_score():
    assert ai_analyzer.seo_audit(page()) == ai_analyzer.seo_audit(page())
