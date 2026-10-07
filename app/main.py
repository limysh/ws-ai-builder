import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routes import router

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def parse_allowed_origins(value: str | None) -> list[str]:
    """Parse and validate credentialed CORS origins from configuration."""
    candidates = (
        [origin.strip() for origin in value.split(",") if origin.strip()]
        if value and value.strip()
        else list(DEFAULT_ALLOWED_ORIGINS)
    )

    origins = []
    for origin in candidates:
        if origin == "*":
            raise ValueError("ALLOWED_ORIGINS cannot contain '*' with credentials")

        parsed = urlsplit(origin)
        has_invalid_parts = (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or "*" in parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or bool(parsed.query)
            or bool(parsed.fragment)
        )
        try:
            parsed.port
        except ValueError as error:
            raise ValueError(f"Invalid CORS origin: {origin}") from error
        if has_invalid_parts:
            raise ValueError(f"Invalid CORS origin: {origin}")

        normalized = origin.rstrip("/")
        if normalized not in origins:
            origins.append(normalized)

    return origins


def create_app() -> FastAPI:
    app = FastAPI(title="WS AI Builder Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=parse_allowed_origins(os.getenv("ALLOWED_ORIGINS")),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    Base.metadata.create_all(bind=engine)
    app.include_router(router)
    return app


app = create_app()
