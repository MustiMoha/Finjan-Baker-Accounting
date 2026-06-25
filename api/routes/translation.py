"""Public UI translation (offline Argos Translate)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.translation import translate_texts

router = APIRouter(prefix="/api", tags=["translation"])

_MAX_BATCH = 100
_MAX_TEXT_LEN = 500


class TranslateRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=_MAX_BATCH)
    source: Literal["en", "ar"] = "en"
    target: Literal["en", "ar"] = "ar"


class TranslateResponse(BaseModel):
    translations: list[str]


@router.post("/translate", response_model=TranslateResponse)
def translate_batch(body: TranslateRequest) -> TranslateResponse:
    if body.source == body.target:
        return TranslateResponse(translations=list(body.texts))
    cleaned: list[str] = []
    for raw in body.texts:
        s = str(raw) if raw is not None else ""
        if len(s) > _MAX_TEXT_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"Each text must be at most {_MAX_TEXT_LEN} characters.",
            )
        cleaned.append(s)
    out = translate_texts(cleaned, source=body.source, target=body.target)
    return TranslateResponse(translations=out)
