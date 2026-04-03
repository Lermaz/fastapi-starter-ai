from fastapi import FastAPI

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.routers import auth_router, health_router, videogames_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(videogames_router)
register_exception_handlers(app)


@app.get("/", tags=["root"])
async def read_root() -> dict[str, str]:
    return {"message": "FastAPI Videogames API"}
