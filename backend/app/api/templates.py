from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateRead

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateRead])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[TemplateRead]:
    rs = await db.execute(
        select(Template).where(Template.deleted_at.is_(None)).order_by(Template.id.asc())
    )
    items = rs.scalars().all()
    return [TemplateRead.model_validate(i) for i in items]


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> TemplateRead:
    obj = Template(
        code=payload.code,
        name=payload.name,
        prompt_template=payload.prompt_template,
        default_model=payload.default_model,
        default_size=payload.default_size,
        builtin=False,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"template code '{payload.code}' already exists",
        ) from exc
    await db.refresh(obj)
    return TemplateRead.model_validate(obj)
