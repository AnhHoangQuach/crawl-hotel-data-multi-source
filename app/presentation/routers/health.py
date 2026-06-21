from fastapi import APIRouter

from app.infrastructure.providers.registry import available_sources

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/sources")
async def get_sources():
    return {"sources": available_sources()}
