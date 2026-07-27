from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from search_server.config import Settings, get_settings
from search_server.routers import suggest, track


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="search-server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(suggest.router)
    app.include_router(track.router)
    return app


app = create_app()
