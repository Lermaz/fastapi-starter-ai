from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings, settings
from app.core.errors import register_exception_handlers
from app.core.limiter import limiter
from app.core.middleware.request_id import RequestIdMiddleware
from app.core.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth_router, health_router, videogames_router


def create_app(cfg: Settings | None = None) -> FastAPI:
    s = cfg or settings
    app = FastAPI(
        title=s.app_name,
        version=s.app_version,
        docs_url="/docs" if s.openapi_enabled else None,
        redoc_url="/redoc" if s.openapi_enabled else None,
        openapi_url="/openapi.json" if s.openapi_enabled else None,
    )
    app.state.limiter = limiter
    app.state.settings = s

    if s.allowed_host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_host_list)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=s)
    if s.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(auth_router, prefix=s.api_v1_prefix)
    app.include_router(videogames_router, prefix=s.api_v1_prefix)

    @app.get("/", tags=["root"])
    async def read_root() -> dict[str, str]:
        return {"message": "FastAPI Videogames API"}

    register_exception_handlers(app)
    return app


app = create_app()
