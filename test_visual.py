import visual_processor as vp


def test_neutrals_are_recognised():
    assert vp._is_neutral((255, 255, 255))
    assert vp._is_neutral((20, 20, 20))
    assert not vp._is_neutral((180, 83, 31))


def test_hex_colors_are_found_in_css():
    counts = vp.extract_css_colors(":root { --brand: #b4531f } a { color: #2f4a3a }")
    assert (180, 83, 31) in counts
    assert (47, 74, 58) in counts


def test_rgb_function_colors_are_found():
    counts = vp.extract_css_colors("h1 { color: rgb(180, 83, 31) }")
    assert (180, 83, 31) in counts


def test_css_without_colors_gives_nothing():
    assert not vp.extract_css_colors("body { margin: 0 }")
