from app.core.chat_book_normalization import BookQuerySlots
from app.core.chat_book_normalization import canonical_book_query
from app.core.chat_book_normalization import extract_book_query_slots
from app.core.chat_book_normalization import normalize_isbn


def test_normalize_isbn_accepts_hyphenated_isbn13():
    assert normalize_isbn("978-0-306-40615-7") == "9780306406157"


def test_extract_book_query_slots_parses_isbn_volume_and_format():
    slots = extract_book_query_slots("ISBN 978-0-306-40615-7 전자책 2권 추천해줘")
    assert slots.isbn == "9780306406157"
    assert slots.volume == 2
    assert slots.format == "ebook"


def test_extract_book_query_slots_parses_quoted_title():
    slots = extract_book_query_slots("도서 '周易辭典' 기준으로 비슷한 책 추천")
    assert slots.title == "周易辭典"


def test_canonical_book_query_prefers_isbn_then_title():
    with_isbn = BookQuerySlots(isbn="9780306406157", title="周易辭典", series=None, volume=None, format=None)
    assert canonical_book_query(with_isbn, "fallback") == "9780306406157"

    with_title = BookQuerySlots(isbn=None, title="周易辭典", series=None, volume=None, format=None)
    assert canonical_book_query(with_title, "fallback") == "周易辭典"
