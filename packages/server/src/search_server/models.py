from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_FIELD_LENGTH = 200


class TrackEventRequest(BaseModel):
    prefix: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH)
    selected: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH)
    action: Literal["suggestion_click", "final_search"]
    session_id: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH, alias="sessionId")

    model_config = {"populate_by_name": True}

    @field_validator("prefix", "selected", "session_id")
    @classmethod
    def _strip_and_reject_blank(cls, value: str) -> str:
        """공백만 있는 값은 min_length 체크를 통과하므로 strip 후 다시 검사한다.

        여기서 막아야 AI 배치 파이프라인(scoring/cooccurrence)이 " " 같은 노이즈로
        오염되지 않는다.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped
