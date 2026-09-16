from opening_divergence.concentration import dominant_share, herfindahl_index, is_concentration_risk


def test_herfindahl_index_none_for_zero_games():
    assert herfindahl_index([]) is None
    assert herfindahl_index([0, 0]) is None


def test_herfindahl_index_uniform_distribution_is_low():
    # 4 equally popular replies -> HHI = 4 * (0.25)^2 = 0.25.
    hhi = herfindahl_index([100, 100, 100, 100])
    assert abs(hhi - 0.25) < 1e-9
    assert not is_concentration_risk(hhi)


def test_herfindahl_index_single_option_is_maximally_concentrated():
    hhi = herfindahl_index([500])
    assert hhi == 1.0
    assert is_concentration_risk(hhi)


def test_herfindahl_index_dominant_reply_flagged_as_risk():
    # One reply is 900/1000 = 90% of games.
    hhi = herfindahl_index([900, 50, 30, 20])
    assert hhi > 0.8
    assert is_concentration_risk(hhi)


def test_herfindahl_index_broad_based_not_flagged():
    # Ten roughly-even replies -> broad-based, HHI near 0.1.
    hhi = herfindahl_index([50] * 10)
    assert abs(hhi - 0.1) < 1e-9
    assert not is_concentration_risk(hhi)


def test_dominant_share_matches_max_over_total():
    assert dominant_share([900, 50, 30, 20]) == 0.9
    assert dominant_share([]) is None
    assert dominant_share([0, 0]) is None


def test_is_concentration_risk_respects_custom_threshold():
    hhi = herfindahl_index([60, 40])  # 0.36+0.16=0.52
    assert is_concentration_risk(hhi, threshold=0.5)
    assert not is_concentration_risk(hhi, threshold=0.6)
