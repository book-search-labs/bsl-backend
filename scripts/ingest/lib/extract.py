import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


def extract_record_id(node: Dict[str, Any]) -> Optional[str]:
    for key in ("@id", "id", "record_id", "identifier"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("@id") or value.get("id") or value.get("value")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def extract_types(node: Dict[str, Any]) -> List[str]:
    value = node.get("@type") or node.get("type")
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [value]
    return []


def extract_updated_at(node: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[str]]:
    for key in ("updated_at", "modified", "dateModified", "updated", "lastModified"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            parsed = parse_datetime(value.strip())
            return parsed, value.strip()
        if isinstance(value, dict):
            nested = value.get("@value") or value.get("value")
            if isinstance(nested, str) and nested.strip():
                parsed = parse_datetime(nested.strip())
                return parsed, nested.strip()
    return None, None


def parse_datetime(value: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        safe = value.replace("Z", "+00:00")
        return datetime.fromisoformat(safe)
    except ValueError:
        return None


def extract_title(node: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    title_keys = ("title", "name", "label", "prefLabel", "mainTitle", "title_ko", "caption")
    value = pick_first(node, title_keys)
    if not value:
        return None, None
    text = value.strip()
    if is_ascii(text):
        return None, text
    return text, None


def extract_language(node: Dict[str, Any]) -> Optional[str]:
    value = pick_first(node, ("language", "language_code", "lang"))
    if value:
        return value.strip()
    return None


def extract_publisher(node: Dict[str, Any]) -> Optional[str]:
    value = pick_first(node, ("publisher", "publisherName", "publisher_name"))
    if value:
        return value.strip()
    return None


def extract_series_name(node: Dict[str, Any]) -> Optional[str]:
    value = pick_first(node, ("series_name", "seriesName", "series", "collection", "setName"))
    if value:
        return value.strip()
    return None


def extract_issued_year(node: Dict[str, Any]) -> Optional[int]:
    value = pick_first(node, ("issued", "dateIssued", "publicationYear", "year"))
    if not value:
        return None
    match = re.search(r"\d{4}", value)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def extract_volume(node: Dict[str, Any]) -> Optional[int]:
    value = pick_first(node, ("volume", "volumeNumber"))
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    if len(match.group()) > 18:
        return None
    try:
        parsed = int(match.group())
    except ValueError:
        return None
    if parsed > 9223372036854775807:
        return None
    return parsed


def extract_identifiers(node: Dict[str, Any]) -> Dict[str, str]:
    identifiers: Dict[str, str] = {}
    isbn = pick_first(node, ("isbn", "isbn13", "isbn_13"))
    if isbn:
        identifiers["isbn13"] = isbn
    isbn10 = pick_first(node, ("isbn10", "isbn_10"))
    if isbn10:
        identifiers["isbn10"] = isbn10
    return identifiers


def extract_edition_labels(node: Dict[str, Any]) -> List[str]:
    value = node.get("edition") or node.get("edition_labels") or node.get("editionLabel")
    labels: List[str] = []
    for item in extract_strings(value):
        trimmed = item.strip()
        if trimmed:
            labels.append(trimmed)
    return labels


def extract_contributors(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    contributors: List[Dict[str, Any]] = []
    keys = ("author", "authors", "creator", "contributor", "editor")
    for key in keys:
        value = node.get(key)
        for entry in normalize_list(value):
            contributor = normalize_contributor(entry, key)
            if contributor:
                contributors.append(contributor)
    return contributors


def extract_concept_ids(node: Dict[str, Any]) -> List[str]:
    values: List[Any] = []
    for key in ("subject", "subjects", "topic", "topics", "concept", "concepts"):
        values.extend(normalize_list(node.get(key)))

    seen = set()
    concept_ids: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("nlk:") and candidate not in seen:
                seen.add(candidate)
                concept_ids.append(candidate)
            return
        if isinstance(value, dict):
            for key in ("@id", "id", "identifier", "concept_id", "conceptId"):
                entry = value.get(key)
                if isinstance(entry, list):
                    for item in entry:
                        add(item)
                else:
                    add(entry)
            return
        if isinstance(value, list):
            for item in value:
                add(item)

    for value in values:
        add(value)

    return concept_ids


def normalize_contributor(entry: Any, source_key: str) -> Optional[Dict[str, Any]]:
    role = "AUTHOR" if source_key in ("author", "authors", "creator") else "CONTRIBUTOR"
    if isinstance(entry, str):
        name = entry.strip()
        if not name:
            return None
        return build_contributor(name, role, None)
    if isinstance(entry, dict):
        agent_id = entry.get("@id") or entry.get("id")
        name = pick_first(entry, ("name", "label", "prefLabel", "name_ko", "name_en"))
        if name:
            return build_contributor(name, role, agent_id)
        nested = entry.get("value") or entry.get("@value")
        if isinstance(nested, str) and nested.strip():
            return build_contributor(nested, role, agent_id)
    return None


def build_contributor(name: str, role: str, agent_id: Optional[str]) -> Dict[str, Any]:
    cleaned = name.strip()
    contributor: Dict[str, Any] = {"role": role}
    if agent_id:
        contributor["agent_id"] = agent_id
    if is_ascii(cleaned):
        contributor["name_en"] = cleaned
    else:
        contributor["name_ko"] = cleaned
    return contributor


def pick_first(node: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = node.get(key)
        for item in extract_strings(value):
            if item.strip():
                return item.strip()
    return None


def extract_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        items: List[str] = []
        for entry in value:
            items.extend(extract_strings(entry))
        return items
    if isinstance(value, dict):
        for key in ("@value", "value", "name", "label", "prefLabel"):
            nested = value.get(key)
            if isinstance(nested, str):
                return [nested]
        return []
    return []


def normalize_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True
