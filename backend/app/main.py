"""FastAPI app. Game endpoints arrive in Phase 3; for now only a health check."""

from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title=get_settings().app_name)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
