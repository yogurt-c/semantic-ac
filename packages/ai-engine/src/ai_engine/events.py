from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ActionType = Literal["suggestion_click", "final_search"]


@dataclass(frozen=True, slots=True)
class SearchEvent:
    """docs/CONTRACT.md 섹션 2의 search_events 레코드 1건.

    session_id는 co-occurrence 학습(ai_engine.cooccurrence)이 "같은 세션에서
    함께 selected된 키워드"를 찾기 위한 키다. 옛 스키마 데이터 호환을 위해
    선택 필드로 두되, 실제로는 서버가 항상 채워 보낸다.
    """

    prefix: str
    selected: str
    action: ActionType
    event_ts: datetime
    session_id: str | None = None
