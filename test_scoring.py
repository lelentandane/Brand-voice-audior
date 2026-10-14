import scoring


def test_visual_score_rewards_fewer_hue_families():
    def v(families):
        return {"metrics": {"palette_size": 3, "hue_families": families}}

    assert scoring.visual_score(v(1)) == 100
    assert scoring.visual_score(v(3)) == 80
    assert scoring.visual_score(v(9)) == 40


def test_visual_score_is_none_when_nothing_was_found():
    assert scoring.visual_score(None) is None
    assert scoring.visual_score({"metrics": {"palette_size": 0, "hue_families": 0}}) is None


def test_health_score_uses_default_weights():
    result = scoring.health_score(80, 60, 100)
    assert result["overall"] == 78  # 0.5*80 + 0.3*60 + 0.2*100
    assert result["weights"] == {"voice": 0.5, "seo": 0.3, "visual": 0.2}


def test_health_score_rescales_when_a_part_is_missing():
    result = scoring.health_score(80, 60, None)
    assert result["overall"] == 72  # (0.5*80 + 0.3*60) / 0.8
    assert "visual" not in result["weights"]
    assert result["components"]["visual"] is None


def test_health_score_with_nothing_scored():
    assert scoring.health_score(None, None, None)["overall"] is None


def test_priorities_puts_voice_first_and_skips_passed_checks():
    voice = {"issues": [{"issue": "Too formal", "evidence": "x", "fix": "Say it simply."}]}
    seo = {"checks": [
        {"check": "Exactly one H1", "passed": True, "detail": "1 found", "advice": "n/a"},
        {"check": "Has H2 subheadings", "passed": False, "detail": "0 found", "advice": "Add H2s."},
    ]}
    items = scoring.priorities(voice, seo)
    assert [i["area"] for i in items] == ["Voice", "SEO"]
    assert items[1]["action"] == "Add H2s."


def test_priorities_respects_limit():
    voice = {"issues": [{"issue": str(i), "evidence": "", "fix": ""} for i in range(8)]}
    assert len(scoring.priorities(voice, None, limit=3)) == 3
