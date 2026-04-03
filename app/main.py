from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.limiter import limiter
from app.routers import auth_router, health_router, videogames_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(videogames_router)
register_exception_handlers(app)


@app.get("/", tags=["root"])
async def read_root() -> dict[str, str]:
    return {"message": "FastAPI Videogames API"}
