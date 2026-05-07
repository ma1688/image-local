from __future__ import annotations

import io
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.core.settings import get_settings
from app.models.job import Job, JobCandidate, JobItem
from app.schemas.job import (
    CandidateSelectRequest,
    JobCandidateRead,
    JobCreate,
    JobDetail,
    JobItemRead,
    JobListResponse,
    JobRead,
)
from app.services import job_runner
from app.services.event_bus import publish as publish_event
from app.services.job_runner import JobCreationError, create_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_read(job: Job) -> JobRead:
    return JobRead(
        id=int(job.id),
        template_code=str(job.template_code),
        api_profile_id=int(job.api_profile_id),
        model=str(job.model),
        size=str(job.size),
        prompt=str(job.prompt or ""),
        candidates_per_image=int(job.candidates_per_image),
        auto_retry=bool(job.auto_retry),
        retry_max=int(job.retry_max),
        output_dir=str(job.output_dir),
        status=str(job.status),
        total_candidates=int(job.total_candidates),
        succeeded_count=int(job.succeeded_count),
        failed_count=int(job.failed_count),
        last_error=job.last_error if job.last_error else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def submit_job(
    payload: JobCreate, session: AsyncSession = Depends(get_db)
) -> JobRead:
    try:
        job = await create_job(payload, session)
    except JobCreationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _job_to_read(job)


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, session: AsyncSession = Depends(get_db)) -> JobDetail:
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.items).selectinload(JobItem.candidates))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    base = _job_to_read(job)
    return JobDetail(
        **base.model_dump(),
        items=[
            JobItemRead(
                id=int(it.id),
                job_id=int(it.job_id),
                source_path=str(it.source_path),
                source_name=str(it.source_name),
                candidates=[
                    JobCandidateRead(
                        id=int(c.id),
                        job_id=int(c.job_id),
                        item_id=int(c.item_id),
                        index=int(c.index),
                        status=str(c.status),
                        output_path=c.output_path,
                        attempts=int(c.attempts),
                        last_error=c.last_error,
                        is_selected=bool(int(c.is_selected or 0)),
                        started_at=c.started_at,
                        finished_at=c.finished_at,
                    )
                    for c in sorted(it.candidates, key=lambda x: int(x.index))
                ],
            )
            for it in job.items
        ],
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    template_code: str | None = Query(default=None, max_length=64),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """分页查询历史任务（按 created_at desc）。

    所有过滤参数都可选；时间区间使用 ISO 8601 字符串。
    """
    filters = []
    if template_code:
        filters.append(Job.template_code == template_code)
    if created_after is not None:
        filters.append(Job.created_at >= created_after)
    if created_before is not None:
        filters.append(Job.created_at <= created_before)

    base = select(Job)
    if filters:
        base = base.where(*filters)

    total_q = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(total_q)).scalar() or 0)

    page = await session.execute(
        base.order_by(Job.created_at.desc(), Job.id.desc()).offset(offset).limit(limit)
    )
    items = [_job_to_read(j) for j in page.scalars().all()]
    return JobListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(
    job_id: int, session: AsyncSession = Depends(get_db)
) -> JobRead:
    """取消任务：

    - 把 status='queued' 的候选改为 cancelled（避免 worker pickup 后再跑）
    - 把 job.status 标为 cancelled（终态）
    - worker 已经在跑的 running 候选会跑完，但 ``_aggregate_job_status`` 会
      尊重 cancelled 状态，不再回退 status；统计上 succeeded/failed 仍累计。
    """
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    await session.execute(
        update(JobCandidate)
        .where(JobCandidate.job_id == job_id, JobCandidate.status == "queued")
        .values(status="cancelled")
    )
    job.status = "cancelled"
    await session.commit()
    await session.refresh(job)

    try:
        publish_event(
            job_id,
            {
                "event": "job.updated",
                "job_id": job_id,
                "status": str(job.status),
                "succeeded": int(job.succeeded_count),
                "failed": int(job.failed_count),
                "total": int(job.total_candidates),
            },
        )
    except Exception as exc:
        logger.warning("publish job.updated on cancel failed: {}", exc)

    # cancel 立刻把 job.status 置为终态 cancelled，再发一条 job.terminated 给
    # SSE 订阅方：worker 仍可能后续完成 running 候选并再次 aggregate（也会重发
    # job.terminated），重复发送对前端无副作用——前端只 close 一次连接。
    try:
        publish_event(
            job_id,
            {
                "event": "job.terminated",
                "job_id": job_id,
                "status": str(job.status),
                "succeeded": int(job.succeeded_count),
                "failed": int(job.failed_count),
                "total": int(job.total_candidates),
            },
        )
    except Exception as exc:
        logger.warning("publish job.terminated on cancel failed: {}", exc)

    return _job_to_read(job)


@router.patch(
    "/{job_id}/candidates/{candidate_id}/select",
    response_model=JobCandidateRead,
)
async def select_candidate(
    job_id: int,
    candidate_id: int,
    payload: CandidateSelectRequest,
    session: AsyncSession = Depends(get_db),
) -> JobCandidateRead:
    """设/取消同 item 下的某个候选选中。

    语义：同 item 互斥，至多一个候选选中；仅允许 succeeded 候选被选中。
    """
    cand = await session.get(JobCandidate, candidate_id)
    if cand is None or int(cand.job_id) != job_id:
        raise HTTPException(
            status_code=404,
            detail=f"candidate {candidate_id} not found in job {job_id}",
        )
    if payload.is_selected and str(cand.status) != "succeeded":
        raise HTTPException(
            status_code=400,
            detail="only succeeded candidates can be selected",
        )

    if payload.is_selected:
        await session.execute(
            update(JobCandidate)
            .where(
                JobCandidate.item_id == cand.item_id,
                JobCandidate.id != candidate_id,
            )
            .values(is_selected=0)
        )
        cand.is_selected = 1
    else:
        cand.is_selected = 0
    await session.commit()
    await session.refresh(cand)

    try:
        publish_event(
            job_id,
            {
                "event": "candidate.selected",
                "job_id": job_id,
                "item_id": int(cand.item_id),
                "candidate_id": int(cand.id),
                "is_selected": bool(int(cand.is_selected)),
            },
        )
    except Exception as exc:
        logger.warning("publish candidate.selected failed (ignored): {}", exc)

    return JobCandidateRead(
        id=int(cand.id),
        job_id=int(cand.job_id),
        item_id=int(cand.item_id),
        index=int(cand.index),
        status=str(cand.status),
        output_path=cand.output_path,
        attempts=int(cand.attempts),
        last_error=cand.last_error,
        is_selected=bool(int(cand.is_selected or 0)),
        started_at=cand.started_at,
        finished_at=cand.finished_at,
    )


def _resolve_candidate_path(raw: str) -> Path | None:
    """把候选 output_path 解析为绝对路径，并强制落在 APP_DATA_DIR 之下。"""
    if not raw:
        return None
    s = get_settings()
    root = s.APP_DATA_DIR.resolve()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (s.APP_DATA_DIR / p)
    try:
        rp = p.resolve(strict=False)
    except OSError:
        return None
    try:
        rp.relative_to(root)
    except ValueError:
        logger.warning("candidate output path escapes data dir: {}", rp)
        return None
    if not rp.exists() or not rp.is_file():
        return None
    return rp


@router.get("/{job_id}/download")
async def download_job_zip(
    job_id: int,
    scope: str = Query(default="all", pattern="^(all|selected)$"),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """打包下载某 job 的候选图。

    scope=all      下载所有 succeeded 候选
    scope=selected 仅下载 is_selected=1 的候选
    """
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")

    rows = await session.execute(
        select(JobCandidate, JobItem)
        .join(JobItem, JobCandidate.item_id == JobItem.id)
        .where(
            JobCandidate.job_id == job_id,
            JobCandidate.status == "succeeded",
        )
    )
    pairs = list(rows.all())
    if scope == "selected":
        pairs = [pair for pair in pairs if int(pair[0].is_selected or 0) == 1]
    if not pairs:
        raise HTTPException(
            status_code=404,
            detail=f"no candidates to download (scope={scope})",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for cand, item in pairs:
            real = _resolve_candidate_path(str(cand.output_path or ""))
            if real is None:
                continue
            stem = Path(str(item.source_name)).stem
            ext = real.suffix or ".png"
            arcname = f"{stem}_cand_{int(cand.index)}{ext}"
            zf.write(real, arcname=arcname)

    body = buf.getvalue()
    filename = f"job_{job_id}_{scope}.zip"
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(body)),
        },
    )


@router.post("/{job_id}/retry-failed", response_model=JobRead)
async def retry_failed(
    job_id: int, session: AsyncSession = Depends(get_db)
) -> JobRead:
    """把当前 job 中 ``status='failed'`` 的候选重置为 queued 并重新派发。

    succeeded / cancelled 候选保持不变；运行中的候选不动（避免冲突）。
    """
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")

    failed_rows = await session.execute(
        select(JobCandidate.id).where(
            JobCandidate.job_id == job_id, JobCandidate.status == "failed"
        )
    )
    failed_ids = [int(r) for r in failed_rows.scalars().all()]
    if not failed_ids:
        raise HTTPException(
            status_code=400, detail="no failed candidates to retry"
        )

    await session.execute(
        update(JobCandidate)
        .where(JobCandidate.id.in_(failed_ids))
        .values(
            status="queued",
            attempts=0,
            last_error=None,
            output_path=None,
            is_selected=0,
            started_at=None,
            finished_at=None,
        )
    )
    job.failed_count = 0
    if str(job.status) in ("failed", "cancelled", "succeeded"):
        job.status = "queued"
    await session.commit()
    await session.refresh(job)

    for cid in failed_ids:
        try:
            job_runner._enqueue_candidate(cid)
        except Exception as exc:
            logger.error("enqueue candidate {} on retry failed: {}", cid, exc)

    try:
        publish_event(
            job_id,
            {
                "event": "job.updated",
                "job_id": job_id,
                "status": str(job.status),
                "succeeded": int(job.succeeded_count),
                "failed": int(job.failed_count),
                "total": int(job.total_candidates),
            },
        )
    except Exception as exc:
        logger.warning("publish job.updated on retry failed: {}", exc)

    return _job_to_read(job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: int, session: AsyncSession = Depends(get_db)
) -> Response:
    """删除一个历史 job：包括 DB 记录和 outputs/<job_id>/ 目录。

    queued / running 任务必须先取消才能删除（409）。
    """
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    if str(job.status) in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="job is still queued/running; cancel it before delete",
        )

    s = get_settings()
    outputs_root = s.outputs_dir.resolve()
    target_dir = (outputs_root / str(job_id)).resolve()
    try:
        target_dir.relative_to(outputs_root)
    except ValueError:
        # 理论不可能；但若不是 outputs_root 子目录则拒绝删除
        raise HTTPException(
            status_code=500,
            detail="resolved output path escapes outputs root",
        ) from None
    if target_dir.exists() and target_dir.is_dir():
        try:
            shutil.rmtree(target_dir)
        except OSError as exc:
            logger.warning("rmtree {} failed: {}", target_dir, exc)

    await session.delete(job)
    await session.commit()

    return Response(status_code=204)
