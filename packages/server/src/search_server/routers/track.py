from datetime import UTC, datetime

import duckdb
from fastapi import APIRouter, Depends, Response

from search_server.db import get_db_connection, insert_event
from search_server.models import TrackEventRequest

router = APIRouter()


@router.post("/track", status_code=202)
def track(
    event: TrackEventRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_db_connection),
) -> Response:
    event_ts = datetime.now(UTC).replace(tzinfo=None)
    insert_event(conn, event.prefix, event.selected, event.action, event_ts, event.session_id)
    return Response(status_code=202)
