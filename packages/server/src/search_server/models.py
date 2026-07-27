from typing import Literal

from pydantic import BaseModel, Field

MAX_FIELD_LENGTH = 200


class TrackEventRequest(BaseModel):
    prefix: str = Field(max_length=MAX_FIELD_LENGTH)
    selected: str = Field(max_length=MAX_FIELD_LENGTH)
    action: Literal["suggestion_click", "final_search"]
