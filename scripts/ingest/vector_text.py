import hashlib
import re
import unicodedata
from typing import Any, Iterable, List, Optional

from lib.extract import extract_strings, is_ascii


LABEL_SEP = " | "


def build_vector_text_v2(book_doc: dict, node: Optional[dict] = None) -> str:
    parts: List[str] = []

    def add(label: str, values: Iterable[Any], lowercase: bool = False) -> None:
        cleaned = []
        seen = set()
        for value in values:
            if value is None:
                continue
            text = normalize_text(str(value), lowercase=lowercase)
            if not text:
                continue
            key = text.lower() if lowercase else text
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        if cleaned:
            parts.append(f"{label}: {', '.join(cleaned)}")

    title_ko = book_doc.get("title_ko")
    title_en = book_doc.get("title_en")
    if title_ko:
        add("TITLE_KO", [title_ko])
    if title_en:
        add("TITLE_EN", [title_en], lowercase=True)

    subtitle_values = []
    if node:
        subtitle_values.extend(extract_strings(node.get("subtitle")))
        subtitle_values.extend(extract_strings(node.get("subTitle")))
        subtitle_values.extend(extract_strings(node.get("alt_title")))
        subtitle_values.extend(extract_strings(node.get("altTitle")))
        subtitle_values.extend(extract_strings(node.get("alternativeTitle")))
    add("SUBTITLE", subtitle_values, lowercase=all(is_ascii(str(v)) for v in subtitle_values))

    author_values = []
    for author in book_doc.get("authors", []) or []:
        name = author.get("name_ko") or author.get("name_en")
        if not name:
            continue
        role = author.get("role")
        label = f"{name} ({role})" if role else name
        author_values.append(label)
    add("AUTHOR", author_values, lowercase=all(is_ascii(str(v)) for v in author_values))

    publisher = book_doc.get("publisher_name")
    if publisher:
        add("PUBLISHER", [publisher], lowercase=is_ascii(str(publisher)))

    issued_year = book_doc.get("issued_year")
    if issued_year:
        add("ISSUED_YEAR", [str(issued_year)])

    volume = book_doc.get("volume")
    if volume:
        add("VOLUME", [format_volume(volume)])

    series_values = []
    if node:
        series_values.extend(extract_strings(node.get("series")))
        series_values.extend(extract_strings(node.get("series_name")))
        series_values.extend(extract_strings(node.get("seriesTitle")))
    add("SERIES", series_values, lowercase=all(is_ascii(str(v)) for v in series_values))

    kdc_values = []
    keyword_values = []
    subject_values = []
    if node:
        kdc_values.extend(extract_strings(node.get("kdc")))
        kdc_values.extend(extract_strings(node.get("classification")))
        keyword_values.extend(extract_strings(node.get("keywords")))
        keyword_values.extend(extract_strings(node.get("keyword")))
        subject_values.extend(extract_strings(node.get("subjects")))
        subject_values.extend(extract_strings(node.get("subject")))
        subject_values.extend(extract_strings(node.get("topic")))
        subject_values.extend(extract_strings(node.get("topics")))
    add("KDC", kdc_values, lowercase=True)
    add("KEYWORDS", keyword_values, lowercase=all(is_ascii(str(v)) for v in keyword_values))
    add("SUBJECTS", subject_values, lowercase=all(is_ascii(str(v)) for v in subject_values))

    identifiers = book_doc.get("identifiers") or {}
    identifier_values = []
    isbn13 = identifiers.get("isbn13")
    if isbn13:
        identifier_values.append(f"ISBN13={isbn13}")
    add("IDENTIFIERS", identifier_values, lowercase=True)

    return LABEL_SEP.join(parts).strip()


def normalize_text(text: str, lowercase: bool = False) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text)
    value = canonicalize_volume(value)
    value = replace_symbols(value)
    value = collapse_whitespace(value)
    if lowercase:
        value = value.lower()
    return value.strip()


def replace_symbols(value: str) -> str:
    if not value:
        return value
    value = re.sub(r"[|/\\\\,:;]+", " ", value)
    value = re.sub(r"[-_]+", " ", value)
    value = value.replace("(", " ").replace(")", " ")
    return value


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_volume(value: str) -> str:
    if not value:
        return value
    value = re.sub(r"0+(\d+)\s*권", r"\1권", value, flags=re.IGNORECASE)
    value = re.sub(r"\bvol\.?\s*0*(\d+)\b", r"\1권", value, flags=re.IGNORECASE)
    value = re.sub(r"\bvolume\s*0*(\d+)\b", r"\1권", value, flags=re.IGNORECASE)
    value = re.sub(r"\bno\.?\s*0*(\d+)\b", r"\1권", value, flags=re.IGNORECASE)
    return value


def format_volume(volume: Any) -> str:
    try:
        return f"{int(volume)}권"
    except Exception:
        return str(volume)


def hash_vector_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
