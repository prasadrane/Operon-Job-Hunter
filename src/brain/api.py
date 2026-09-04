"""FastAPI router for Career Brain endpoints."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.brain.config import get_brain_settings
from src.brain.inference import BrainInference


class BrainQueryRequest(BaseModel):
    """Request body for ``POST /brain/query``."""

    query: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field(default="auto", pattern="^(auto|avatar|tailoring|qa)$")
    job_desc: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


class BrainQueryResponse(BaseModel):
    """Response body for ``POST /brain/query``."""

    answer: str
    mode: str
    citations: List[dict] = Field(default_factory=list)
    confidence: float
    warnings: List[str] = Field(default_factory=list)
    retrieved_chunks: int = 0
    latency_ms: float = 0.0


def create_brain_router(brain: Optional[BrainInference] = None) -> APIRouter:
    """Create the brain API router.

    Parameters
    ----------
    brain:
        Optional pre-built :class:`BrainInference` instance — used by tests to
        inject a mock.  When omitted, a default instance is constructed lazily.
    """
    router = APIRouter(prefix="/brain", tags=["brain"])
    _brain = brain or BrainInference()

    @router.post("/query", response_model=BrainQueryResponse)
    async def query_brain(request: BrainQueryRequest) -> BrainQueryResponse:
        settings = get_brain_settings()
        if not settings.BRAIN_ENABLED:
            raise HTTPException(status_code=503, detail="Brain service disabled")

        response = _brain.query(
            query=request.query,
            mode=request.mode,
            job_desc=request.job_desc,
            top_k=request.top_k,
        )
        return BrainQueryResponse(**response.to_dict())

    @router.post("/batch")
    async def batch_query_brain(queries: List[str], mode: str = "qa", job_desc: Optional[str] = None):
        settings = get_brain_settings()
        if not settings.BRAIN_ENABLED:
            raise HTTPException(status_code=503, detail="Brain service disabled")

        responses = _brain.batch_query(
            queries=queries,
            mode=mode,
            job_desc=job_desc,
        )
        return {"results": [r.to_dict() for r in responses]}

    @router.post("/stream")
    async def stream_brain(request: BrainQueryRequest):
        from fastapi.responses import StreamingResponse

        settings = get_brain_settings()
        if not settings.BRAIN_ENABLED:
            raise HTTPException(status_code=503, detail="Brain service disabled")

        def event_gen():
            for evt in _brain.query_stream(request.query, mode=request.mode,
                                           job_desc=request.job_desc, top_k=request.top_k):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @router.get("/status")
    async def brain_status():
        return {
            "enabled": get_brain_settings().BRAIN_ENABLED,
            "ollama_available": _brain.ollama.is_available(),
            "model": _brain.ollama.model,
        }

    @router.get("/models")
    async def list_models():
        from src.brain.model_registry import get_model_registry

        registry = get_model_registry()
        return {"models": registry.list_models()}

    return router
