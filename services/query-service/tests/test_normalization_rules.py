import json
import os

from app.core import normalize


def test_normalization_replacements(tmp_path):
    rules = {
        "rules": {
            "replacements": [
                {"pattern": "sci fi", "replacement": "science fiction"},
                {"pattern": "\\s+", "replacement": " ", "regex": True},
            ]
        }
    }
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    os.environ["NORMALIZATION_RULES_PATH"] = str(path)
    normalize.reload_normalization_rules()

    assert normalize.normalize_query("sci   fi") == "science fiction"

    os.environ.pop("NORMALIZATION_RULES_PATH", None)
    normalize.reload_normalization_rules()
