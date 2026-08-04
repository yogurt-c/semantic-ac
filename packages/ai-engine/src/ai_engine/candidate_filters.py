from __future__ import annotations

from pathlib import Path

DEFAULT_MIN_LENGTH = 2
DEFAULT_MAX_LENGTH = 50

# 형태소 분석기 없이도 걸러낼 수 있는 최소한의 의미없는 채움말. 도메인에 맞는
# 불용어/블록리스트는 load_wordlist()로 파일에서 읽어 확장한다.
DEFAULT_STOPWORDS: frozenset[str] = frozenset(
    {
        "그냥",
        "좀",
        "뭐",
        "이거",
        "저거",
        "그거",
        "진짜",
        "완전",
        "제발",
        "아무거나",
        "글쎄",
    }
)


def load_wordlist(path: Path | str | None) -> frozenset[str]:
    """줄 단위 단어 목록 파일을 읽어 정규화된(casefold) frozenset으로 반환한다.

    `#`로 시작하는 줄과 빈 줄은 무시한다. path가 None이거나 파일이 없으면 빈
    집합을 반환한다 (블록리스트는 운영자가 직접 채워야 하는 값이라 코드에
    하드코딩하지 않는다).
    """
    if not path:
        return frozenset()

    file_path = Path(path)
    if not file_path.exists():
        return frozenset()

    words = {
        line.strip().casefold()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return frozenset(words)


def is_clean_candidate(
    candidate: str,
    *,
    stopwords: frozenset[str] = DEFAULT_STOPWORDS,
    blocklist: frozenset[str] = frozenset(),
    min_length: int = DEFAULT_MIN_LENGTH,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> bool:
    """추천 후보 문자열 하나가 노출해도 되는 품질인지 판정한다."""
    normalized = candidate.strip()
    if not (min_length <= len(normalized) <= max_length):
        return False
    if normalized.isdigit():
        return False
    if not any(char.isalnum() for char in normalized):
        return False

    key = normalized.casefold()
    if key in stopwords or key in blocklist:
        return False
    return True


def clean_candidates(
    candidates: list[str],
    *,
    stopwords: frozenset[str] = DEFAULT_STOPWORDS,
    blocklist: frozenset[str] = frozenset(),
    min_length: int = DEFAULT_MIN_LENGTH,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> list[str]:
    """불용어/길이/특수문자·숫자만/블록리스트를 걸러내고 정규화 기준으로 dedup한다.

    호출자(pipeline._merge_unique)는 완전 일치만 dedup하므로, 대소문자나 좌우
    공백만 다른 유사 중복("Labtop " vs "labtop")은 여기서 casefold 키로 한 번 더
    걸린다. 입력 리스트의 최초 등장 순서를 그대로 보존해 레이어 우선순위를
    유지한다.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for candidate in candidates:
        if not is_clean_candidate(
            candidate,
            stopwords=stopwords,
            blocklist=blocklist,
            min_length=min_length,
            max_length=max_length,
        ):
            continue
        normalized = candidate.strip()
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned
