from pathlib import Path

from app.core.spell_candidates import get_generator

ROOT = Path(__file__).resolve().parents[3]


def test_keyboard_adjacent_generation(monkeypatch):
    monkeypatch.setenv("QS_SPELL_CANDIDATE_ENABLE", "1")
    monkeypatch.setenv("QS_SPELL_KEYBOARD_LOCALE", "en")
    monkeypatch.setenv("QS_SPELL_CANDIDATE_MAX", "20")
    monkeypatch.setenv("QS_SPELL_CANDIDATE_TOPK", "10")
    generator = get_generator()
    assert generator is not None
    candidates = generator.generate("test")
    texts = {candidate.text for candidate in candidates}
    assert "rest" in texts


def test_dictionary_candidate(monkeypatch):
    monkeypatch.setenv("QS_SPELL_CANDIDATE_ENABLE", "1")
    monkeypatch.setenv("QS_SPELL_DICT_BACKEND", "file")
    monkeypatch.setenv("QS_SPELL_DICT_PATH", str(ROOT / "data/dict/spell_aliases.jsonl"))
    generator = get_generator()
    assert generator is not None
    candidates = generator.generate("해리 포터")
    texts = {candidate.text for candidate in candidates}
    assert "해리포터" in texts


def test_candidate_bound(monkeypatch):
    monkeypatch.setenv("QS_SPELL_CANDIDATE_ENABLE", "1")
    monkeypatch.setenv("QS_SPELL_CANDIDATE_MAX", "3")
    monkeypatch.setenv("QS_SPELL_CANDIDATE_TOPK", "3")
    generator = get_generator()
    assert generator is not None
    candidates = generator.generate("harry potter")
    assert len(candidates) <= 3
