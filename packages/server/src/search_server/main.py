from fastapi import FastAPI

from search_server.routers import suggest, track


def create_app() -> FastAPI:
    app = FastAPI(title="search-server")
    app.include_router(suggest.router)
    app.include_router(track.router)
    return app


app = create_app()
