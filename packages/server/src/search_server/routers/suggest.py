import json
import logging

import redis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from search_server.redis_client import get_redis_client

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 200


@router.get("/suggest", response_model=None)
def suggest(
    q: str | None = None,
    client: redis.Redis = Depends(get_redis_client),
) -> JSONResponse | dict:
    if not q:
        return JSONResponse(status_code=400, content={"error": "q is required"})
    if len(q) > MAX_QUERY_LENGTH:
        return JSONResponse(status_code=400, content={"error": "q is too long"})

    try:
        raw = client.get(f"sugg:{q}")
        if raw is None:
            return {"suggestions": []}
        return {"suggestions": json.loads(raw)}
    except Exception:
        logger.exception("suggest lookup failed for q=%r", q)
        return JSONResponse(status_code=500, content={"error": "internal server error"})
