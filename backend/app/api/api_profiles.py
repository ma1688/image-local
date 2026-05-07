from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.crypto import decrypt, encrypt, mask
from app.models.api_profile import ApiProfile
from app.schemas.api_profile import (
    ApiProfileCreate,
    ApiProfileRead,
    ApiProfileUpdate,
    ModelListResponse,
)
from app.services.external_models import fetch_models

router = APIRouter(prefix="/api-profiles", tags=["api-profiles"])


def _to_read(obj: ApiProfile) -> ApiProfileRead:
    """ORM → ApiProfileRead，附带 api_key_masked。"""
    try:
        plain = decrypt(obj.api_key_cipher)
    except ValueError:
        plain = ""
    return ApiProfileRead(
        id=obj.id,
        name=obj.name,
        base_url=obj.base_url,
        default_model=obj.default_model,
        api_key_masked=mask(plain),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@router.get("", response_model=list[ApiProfileRead])
async def list_profiles(db: AsyncSession = Depends(get_db)) -> list[ApiProfileRead]:
    rs = await db.execute(select(ApiProfile).order_by(ApiProfile.id.asc()))
    return [_to_read(p) for p in rs.scalars().all()]


@router.post("", response_model=ApiProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ApiProfileCreate, db: AsyncSession = Depends(get_db)
) -> ApiProfileRead:
    obj = ApiProfile(
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        api_key_cipher=encrypt(payload.api_key),
        default_model=payload.default_model,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_read(obj)


async def _get_or_404(db: AsyncSession, profile_id: int) -> ApiProfile:
    obj = await db.get(ApiProfile, profile_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="api_profile not found")
    return obj


@router.patch("/{profile_id}", response_model=ApiProfileRead)
async def update_profile(
    profile_id: int,
    payload: ApiProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiProfileRead:
    obj = await _get_or_404(db, profile_id)
    if payload.name is not None:
        obj.name = payload.name
    if payload.base_url is not None:
        obj.base_url = payload.base_url.rstrip("/")
    if payload.default_model is not None:
        obj.default_model = payload.default_model
    if payload.api_key:  # 空字符串视为不修改
        obj.api_key_cipher = encrypt(payload.api_key)
    await db.commit()
    await db.refresh(obj)
    return _to_read(obj)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db)) -> None:
    obj = await _get_or_404(db, profile_id)
    await db.delete(obj)
    await db.commit()


@router.post("/{profile_id}/models", response_model=ModelListResponse)
async def list_external_models(
    profile_id: int, db: AsyncSession = Depends(get_db)
) -> ModelListResponse:
    obj = await _get_or_404(db, profile_id)
    try:
        plain_key = decrypt(obj.api_key_cipher)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="无法解密 API Key（密钥可能已变更）",
        ) from exc
    try:
        models = await fetch_models(obj.base_url, plain_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"外部 API 错误：HTTP {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"无法连接外部 API：{type(exc).__name__}",
        ) from exc
    return ModelListResponse(models=models)
