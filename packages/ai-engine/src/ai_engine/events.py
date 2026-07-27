from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ActionType = Literal["suggestion_click", "final_search"]


@dataclass(frozen=True, slots=True)
class SearchEvent:
    """docs/CONTRACT.md 섹션 2의 search_events 레코드 1건."""

    prefix: str
    selected: str
    action: ActionType
    event_ts: datetime
