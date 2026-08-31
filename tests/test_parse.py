import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from parse import parse


def test_keyword_present_single_ref():
    assert parse("Closes HOMELABSTA-22.") == [("HOMELABSTA", 22)]


def test_keyword_absent_with_require_keyword_finds_nothing():
    assert parse("See HOMELABSTA-22 for context.") == []


def test_no_require_keyword_finds_bare_reference():
    assert parse("See HOMELABSTA-22 for context.", require_keyword=False) == [
        ("HOMELABSTA", 22)
    ]


def test_multiple_refs_comma_and_list():
    result = parse("Closes FOO-1, FOO-2 and FOO-3.")
    assert result == [("FOO", 1), ("FOO", 2), ("FOO", 3)]


def test_lowercase_prefix_ignored():
    assert parse("Closes foo-1 and HOMELABSTA-22.") == [("HOMELABSTA", 22)]


def test_hash_prefix_tolerated():
    assert parse("Fixes #HOMELABSTA-22.") == [("HOMELABSTA", 22)]


def test_unrelated_prefix_filtered_when_prefixes_set():
    result = parse("Closes WORD-123 and HOMELABSTA-22.", prefixes=["HOMELABSTA"])
    assert result == [("HOMELABSTA", 22)]


def test_prefix_filter_is_case_insensitive():
    result = parse("Closes HOMELABSTA-22.", prefixes=["homelabsta"])
    assert result == [("HOMELABSTA", 22)]


def test_duplicate_refs_deduplicated_preserving_order():
    result = parse("Closes HOMELABSTA-22. Also closes HOMELABSTA-22 again.")
    assert result == [("HOMELABSTA", 22)]


def test_keyword_case_insensitive():
    assert parse("CLOSES HOMELABSTA-22.") == [("HOMELABSTA", 22)]
    assert parse("closed HOMELABSTA-22.") == [("HOMELABSTA", 22)]


def test_identifier_outside_keyword_window_not_matched():
    far_text = "Fixes " + ("x" * 200) + " HOMELABSTA-22"
    assert parse(far_text) == []


def test_no_keywords_and_require_keyword_true_finds_nothing():
    assert parse("HOMELABSTA-22 mentioned with no keyword.") == []


def test_custom_keywords_list():
    result = parse("Ships HOMELABSTA-22.", keywords=["ships"])
    assert result == [("HOMELABSTA", 22)]
