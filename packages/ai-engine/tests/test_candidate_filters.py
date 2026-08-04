from __future__ import annotations

from pathlib import Path

from ai_engine.candidate_filters import (
    DEFAULT_STOPWORDS,
    clean_candidates,
    is_clean_candidate,
    load_wordlist,
)


def test_is_clean_candidate_accepts_ordinary_keyword():
    assert is_clean_candidate("노트북 추천") is True


def test_is_clean_candidate_rejects_below_min_length():
    assert is_clean_candidate("아", min_length=2) is False


def test_is_clean_candidate_rejects_above_max_length():
    assert is_clean_candidate("가" * 51, max_length=50) is False


def test_is_clean_candidate_rejects_digits_only():
    assert is_clean_candidate("12345") is False


def test_is_clean_candidate_rejects_special_characters_only():
    assert is_clean_candidate("!!!???") is False


def test_is_clean_candidate_accepts_mixed_alnum_and_symbols():
    assert is_clean_candidate("labtop-13") is True


def test_is_clean_candidate_rejects_known_stopword():
    assert is_clean_candidate("그냥", stopwords=DEFAULT_STOPWORDS) is False


def test_is_clean_candidate_rejects_stopword_regardless_of_case():
    assert is_clean_candidate("그냥".upper(), stopwords=DEFAULT_STOPWORDS) is False


def test_is_clean_candidate_rejects_blocklisted_term():
    assert is_clean_candidate("스팸단어", blocklist=frozenset({"스팸단어"})) is False


def test_clean_candidates_preserves_first_seen_order():
    result = clean_candidates(["노트북 추천", "가성비 노트북", "맥북"])
    assert result == ["노트북 추천", "가성비 노트북", "맥북"]


def test_clean_candidates_deduplicates_case_and_whitespace_variants():
    result = clean_candidates(["Labtop ", " labtop", "LABTOP"])
    assert result == ["Labtop"]


def test_clean_candidates_drops_filtered_items_without_breaking_order():
    result = clean_candidates(["노트북 추천", "123", "그냥", "맥북"])
    assert result == ["노트북 추천", "맥북"]


def test_clean_candidates_returns_empty_list_for_empty_input():
    assert clean_candidates([]) == []


def test_load_wordlist_returns_empty_set_for_none_path():
    assert load_wordlist(None) == frozenset()


def test_load_wordlist_returns_empty_set_for_missing_file(tmp_path: Path):
    assert load_wordlist(tmp_path / "missing.txt") == frozenset()


def test_load_wordlist_reads_terms_and_ignores_comments_and_blanks(tmp_path: Path):
    path = tmp_path / "blocklist.txt"
    path.write_text("스팸1\n# 주석\n\n스팸2\n", encoding="utf-8")

    words = load_wordlist(path)

    assert words == frozenset({"스팸1", "스팸2"})


def test_load_wordlist_normalizes_case(tmp_path: Path):
    path = tmp_path / "blocklist.txt"
    path.write_text("SpamWord\n", encoding="utf-8")

    words = load_wordlist(path)

    assert "spamword" in words
