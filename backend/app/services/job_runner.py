"""Job 提交与排队（在 web 进程内执行）。

create_job:
1. 校验所有 source_paths 在白名单内（safe_resolve）。
2. 写入 jobs / job_items / job_candidates。
3. 把每张候选派发到 Celery（generate_one_candidate.delay）。
4. 返回创建好的 Job + items + candidates。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobCandidate, JobItem
from app.schemas.job import JobCreate
from app.services.event_bus import publish as publish_event
from app.services.storage import InvalidPathError, safe_resolve


def _enqueue_candidate(candidate_id: int) -> None:
    """间接调用 Celery，便于测试 monkeypatch。"""
    from app.tasks.generate import generate_one_candidate

    generate_one_candidate.delay(candidate_id)


class JobCreationError(ValueError):
    pass


async def create_job(payload: JobCreate, session: AsyncSession) -> Job:
    valid_paths: list[Path] = []
    for raw in payload.source_paths:
        try:
            p = safe_resolve(raw, must_exist=True)
        except InvalidPathError as exc:
            raise JobCreationError(f"invalid source path: {raw} ({exc})") from exc
        if not p.is_file():
            raise JobCreationError(f"not a file: {p.as_posix()}")
        valid_paths.append(p)

    job = Job(
        template_code=payload.template_code,
        api_profile_id=payload.api_profile_id,
        model=payload.model,
        size=payload.size,
        prompt=payload.prompt,
        candidates_per_image=payload.candidates_per_image,
        auto_retry=1 if payload.auto_retry else 0,
        retry_max=payload.retry_max,
        output_dir=payload.output_dir,
        status="queued",
        total_candidates=len(valid_paths) * payload.candidates_per_image,
    )
    session.add(job)
    await session.flush()  # 先取得 job.id

    candidate_ids: list[int] = []
    for path in valid_paths:
        item = JobItem(
            job_id=job.id,
            source_path=path.as_posix(),
            source_name=path.name,
        )
        session.add(item)
        await session.flush()
        for k in range(1, payload.candidates_per_image + 1):
            cand = JobCandidate(
                job_id=job.id,
                item_id=item.id,
                index=k,
                status="queued",
            )
            session.add(cand)
            await session.flush()
            candidate_ids.append(cand.id)

    await session.commit()
    await session.refresh(job)

    # 提前发一个 job.created 事件，方便前端 SSE 订阅时立刻拿到上下文
    try:
        publish_event(
            int(job.id),
            {
                "event": "job.created",
                "job_id": int(job.id),
                "total": int(job.total_candidates),
                "candidates_per_image": int(job.candidates_per_image),
                "items": [{"path": p.as_posix(), "name": p.name} for p in valid_paths],
            },
        )
    except Exception:
        pass  # 事件总线不可用时不阻断主流程

    # 派发 Celery 任务（commit 之后再发，避免 worker 抢先于 DB 可见）
    for cid in candidate_ids:
        _enqueue_candidate(cid)

    return job
