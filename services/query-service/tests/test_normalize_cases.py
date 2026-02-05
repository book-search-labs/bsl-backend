import json
from pathlib import Path

from app.core.analyzer import analyze_query


def test_normalize_cases():
    path = Path(__file__).parent / "fixtures" / "normalize_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    for case in cases:
        result = analyze_query(case["raw"], "ko-KR")
        assert result["norm"] == case["norm"]
        if "volume" in case:
            assert result["volume"] == case["volume"]
        if "isbn" in case:
            assert result["isbn"] == case["isbn"]
        if "mode" in case:
            assert result["mode"] == case["mode"]
