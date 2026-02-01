import pytest

from app.core.spell import accept_spell_candidate


@pytest.mark.parametrize(
    "original,candidate,accepted,reason",
    [
        ("harry pottre", "harry potter", True, None),
        ("해리포터 1권", "해리 포터 1권", True, None),
        ("vol 2 해리포터", "해리포터 vol 2", True, None),
        ("harry potter", "harry  potter", True, None),
        ("테스트 1권", "테스트 1 권", True, None),
        ("C++ 11", "c++ 11", True, None),
        ("isbn 978-89-123-4567-8", "isbn 978-89-123-4567-8", False, "no_change"),
        ("isbn 978-89-123-4567-8", "isbn 978-89-123-4567-0", False, "numeric_mismatch"),
        ("2024 edition", "edition", False, "numeric_mismatch"),
        ("vol 2 해리포터", "해리포터 vol 3", False, "volume_mismatch"),
        ("원피스 3권", "원피스", False, "volume_mismatch"),
        ("abcdef", "uvwxyz", False, "edit_distance"),
        ("harry potter", "hp", False, "length_ratio"),
        ("hp", "harry potter and the chamber of secrets", False, "length_ratio"),
        ("hello", "he\u0000llo", False, "forbidden_char"),
        ("hello", "", False, "empty"),
        ("hello", "   ", False, "empty"),
        ("short", "a" * 200, False, "too_long"),
        ("vol 10", "vol 11", False, "volume_mismatch"),
        ("isbn 9781234567890", "isbn 9781234567890", False, "no_change"),
        ("isbn 9781234567890", "isbn 978123456789", False, "numeric_mismatch"),
    ],
)
def test_accept_spell_candidate(original, candidate, accepted, reason):
    ok, reject_reason = accept_spell_candidate(original, candidate)
    assert ok is accepted
    if accepted:
        assert reject_reason is None
    else:
        assert reject_reason == reason
