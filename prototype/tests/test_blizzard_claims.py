"""BlizzCon 공식 발표의 결정적 claim 규칙."""
from orc_citadel.extract_claims import _PREDICATE_RULES


def test_announcement_rule_matches_official_blizzcon_language():
    assert any(predicate == "announces" and pattern.search("Blizzard announced Diablo V.")
               for pattern, predicate, _modality, _event_type in _PREDICATE_RULES)
