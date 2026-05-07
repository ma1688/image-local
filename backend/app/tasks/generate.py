"""Celery 任务：执行单张候选图的生成。

设计要点（方案 5.3 节 + 用户确认）：
- task 粒度：每张候选一个 task。
- 重试：当 ``GenerationError.retryable`` 为 True 时使用 Celery 自动重试，max=Job.retry_max；
  超过上限则把候选标记为 failed 并写 last_error。
- 状态持久化：job_candidates.status / attempts / last_error / started_at / finished_at；
  Job 聚合的 succeeded_count / failed_count / status 由该 task 在每次结束时同步更新。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from celery import Task
from loguru import logger
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.celery_app import celery_app
from app.core.crypto import decrypt
from app.core.settings import get_settings
from app.models.api_profile import ApiProfile
from app.models.job import Job, JobCandidate, JobItem
from app.services.event_bus import publish as publish_event
from app.services.openai_image import (
    GenerationError,
    GenerationRequest,
    generate_one,
)


def _emit(job_id: int, kind: str, **fields: object) -> None:
    """统一事件发布，确保 worker 失败时不影响主流程。

    job_id 既作为 Redis Stream 的 routing key（由 publish_event 决定 stream 名），
    也注入到 payload 中方便前端直接消费；调用方不应再以 ``job_id=...`` 形式传入。
    """
    try:
        payload: dict[str, object] = {"event": kind, "job_id": job_id, **fields}
        publish_event(job_id, payload)
    except Exception as exc:
        logger.warning("publish event failed (ignored): {}", exc)


def _sync_session_factory() -> sessionmaker[Session]:
    """Celery worker 在同步上下文里跑，给它一个独立的同步 SQLAlchemy session。"""
    s = get_settings()
    sync_url = (
        f"sqlite:///{s.db_path.as_posix()}"
        if s.db_path.is_absolute()
        else f"sqlite:///{s.db_path.resolve().as_posix()}"
    )
    engine = create_engine(sync_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


_SessionLocal: sessionmaker[Session] | None = None


def _session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = _sync_session_factory()
    return _SessionLocal()


def _render_prompt(template: str, user_prompt: str) -> str:
    """渲染 prompt 模板：把 ``{prompt}`` 占位替换为用户输入；无占位则忽略 user_prompt。"""
    if not template:
        return user_prompt
    if "{prompt}" in template:
        return template.replace("{prompt}", user_prompt or "")
    return template


def _resolve_output_dir(job: Job) -> Path:
    """job_id/<item_id>/cand_<index>.png"""
    s = get_settings()
    base = Path(job.output_dir)
    if not base.is_absolute():
        base = (s.APP_DATA_DIR / base).resolve()
    return base / str(job.id)


_AGGREGATE_SQL = text(
    """
    UPDATE jobs SET
      succeeded_count = (
        SELECT COUNT(*) FROM job_candidates
        WHERE job_id = :jid AND status = 'succeeded'
      ),
      failed_count = (
        SELECT COUNT(*) FROM job_candidates
        WHERE job_id = :jid AND status = 'failed'
      ),
      status = CASE
        WHEN status = 'cancelled' THEN 'cancelled'
        WHEN (
          SELECT COUNT(*) FROM job_candidates
          WHERE job_id = :jid AND status IN ('queued','running')
        ) > 0 THEN 'running'
        WHEN (
          SELECT COUNT(*) FROM job_candidates
          WHERE job_id = :jid AND status = 'succeeded'
        ) = 0 AND (
          SELECT COUNT(*) FROM job_candidates
          WHERE job_id = :jid AND status = 'failed'
        ) = 0 THEN 'cancelled'
        WHEN (
          SELECT COUNT(*) FROM job_candidates
          WHERE job_id = :jid AND status = 'failed'
        ) = 0 THEN 'succeeded'
        ELSE 'failed'
      END
    WHERE id = :jid
    """
)


def _aggregate_job_status(session: Session, job_id: int) -> None:
    """根据所有候选状态聚合更新 job，并发出 job.updated 事件。

    并发安全：worker 是 prefork 多进程并发完成 task，每个进程独立 session。若
    用 ORM 先 SELECT 再 UPDATE，多个 session 的 commit 顺序不可控，最后 commit
    的不一定基于最新数据，会造成 succeeded_count / failed_count 写入"过时"的
    较小值。这里改为 **单条 UPDATE** 让 SQLite 写锁内重读子查询：无论谁后
    commit，最终 counts 都基于实时聚合。

    不变量：
    - ``cancelled`` 是用户主动设置的终态（CASE 中第一分支兜底），worker 后续
      聚合不会把它覆写为 failed/succeeded。
    - 全部候选都 cancelled（无 succeeded/failed）也视作终态 ``cancelled``。
    """
    session.execute(_AGGREGATE_SQL, {"jid": job_id})
    session.commit()

    job = session.get(Job, job_id)
    if not job:
        return
    session.refresh(job)
    status = str(job.status)
    _emit(
        job_id,
        "job.updated",
        status=status,
        succeeded=int(job.succeeded_count),
        failed=int(job.failed_count),
        total=int(job.total_candidates),
    )
    # job 进入终态时再发一个独立事件，前端据此可主动 close SSE 订阅，
    # 避免浏览器 EventSource 在终态后仍持有长连接（看似「连接中…」）。
    if status in ("succeeded", "failed", "cancelled"):
        _emit(
            job_id,
            "job.terminated",
            status=status,
            succeeded=int(job.succeeded_count),
            failed=int(job.failed_count),
            total=int(job.total_candidates),
        )


@celery_app.task(
    name="app.tasks.generate.generate_one_candidate",
    bind=True,
    autoretry_for=(GenerationError,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def generate_one_candidate(self: Task, candidate_id: int) -> dict[str, object]:
    """生成一张候选图。失败时按 Job.retry_max 决定是否再试。"""
    sess = _session()
    try:
        cand = sess.get(JobCandidate, candidate_id)
        if cand is None:
            return {"ok": False, "reason": f"candidate {candidate_id} not found"}
        if cand.status in ("succeeded", "cancelled"):
            return {"ok": True, "skipped": True}

        item = sess.get(JobItem, cand.item_id)
        job = sess.get(Job, cand.job_id)
        if not item or not job:
            return {"ok": False, "reason": "missing job/item"}

        # short-circuit：job 已被用户 cancelled 时不再走 generate，
        # 把仍是 queued/running 的本候选直接标记为 cancelled 并触发聚合。
        # 避免 cancel 后 worker prefetch 中的任务表面上变成 failed 误导用户。
        sess.refresh(job)
        if str(job.status) == "cancelled" and cand.status in ("queued", "running"):
            cand.status = "cancelled"
            cand.finished_at = datetime.now(UTC)
            sess.commit()
            _aggregate_job_status(sess, job.id)
            return {"ok": True, "skipped": True, "reason": "job cancelled"}

        profile = sess.get(ApiProfile, job.api_profile_id)
        if not profile:
            cand.status = "failed"
            cand.last_error = f"api profile {job.api_profile_id} missing"
            cand.finished_at = datetime.now(UTC)
            sess.commit()
            _aggregate_job_status(sess, job.id)
            return {"ok": False, "reason": cand.last_error}

        if (
            self.request.retries == 0
            and cand.attempts == 0
        ):
            cand.started_at = datetime.now(UTC)
        cand.attempts = (cand.attempts or 0) + 1
        cand.status = "running"
        sess.commit()

        _emit(
            int(job.id),
            "candidate.running",
            candidate_id=int(cand.id),
            item_id=int(cand.item_id),
            index=int(cand.index),
            attempt=int(cand.attempts),
            source_name=str(item.source_name),
        )

        from app.models.template import Template

        tpl = sess.execute(
            select(Template).where(Template.code == job.template_code)
        ).scalar_one_or_none()
        rendered_prompt = _render_prompt(
            tpl.prompt_template if tpl else "",
            job.prompt,
        )

        try:
            api_key = decrypt(profile.api_key_cipher)
            req = GenerationRequest(
                base_url=str(profile.base_url),
                api_key=api_key,
                model=str(job.model),
                size=str(job.size),
                prompt=rendered_prompt,
                source_image_path=Path(str(item.source_path)),
            )
            result = generate_one(req)

            target_dir = _resolve_output_dir(job) / str(item.id)
            target_dir.mkdir(parents=True, exist_ok=True)
            out_path = target_dir / f"cand_{cand.index}.png"
            out_path.write_bytes(result.image_bytes)

            cand.status = "succeeded"
            cand.output_path = out_path.as_posix()
            cand.last_error = None
            cand.finished_at = datetime.now(UTC)
            sess.commit()

            _emit(
                int(job.id),
                "candidate.succeeded",
                candidate_id=int(cand.id),
                item_id=int(cand.item_id),
                index=int(cand.index),
                output_path=out_path.as_posix(),
                source_name=str(item.source_name),
            )
            _aggregate_job_status(sess, int(job.id))
            logger.info(
                "candidate {} OK -> {}", candidate_id, out_path.as_posix()
            )
            return {"ok": True, "path": out_path.as_posix()}

        except GenerationError as exc:
            cand.last_error = str(exc)
            sess.execute(
                update(JobCandidate)
                .where(JobCandidate.id == candidate_id)
                .values(last_error=str(exc))
            )
            sess.commit()

            should_retry = (
                exc.retryable
                and bool(job.auto_retry)
                and self.request.retries < int(job.retry_max)
            )
            if should_retry:
                logger.warning(
                    "candidate {} attempt {} failed: {} -> retrying",
                    candidate_id,
                    cand.attempts,
                    exc,
                )
                _emit(
                    int(job.id),
                    "candidate.retry",
                    candidate_id=int(cand.id),
                    item_id=int(cand.item_id),
                    index=int(cand.index),
                    attempt=int(cand.attempts),
                    error=str(exc),
                    source_name=str(item.source_name),
                )
                raise

            # 收尾前再次检查 job.status：若用户已 cancel，把这张视为 cancelled
            # 而不是 failed，避免 cancel 后表面统计仍是大量 failed 的误导。
            sess.refresh(job)
            if str(job.status) == "cancelled":
                cand.status = "cancelled"
                cand.finished_at = datetime.now(UTC)
                sess.commit()
                _aggregate_job_status(sess, int(job.id))
                logger.info(
                    "candidate {} attempt {} failed but job cancelled -> marked cancelled",
                    candidate_id,
                    cand.attempts,
                )
                return {"ok": True, "skipped": True, "reason": "job cancelled"}

            cand.status = "failed"
            cand.finished_at = datetime.now(UTC)
            sess.commit()
            _emit(
                int(job.id),
                "candidate.failed",
                candidate_id=int(cand.id),
                item_id=int(cand.item_id),
                index=int(cand.index),
                attempt=int(cand.attempts),
                error=str(exc),
                source_name=str(item.source_name),
            )
            _aggregate_job_status(sess, int(job.id))
            logger.error(
                "candidate {} attempt {} failed (no retry): {}",
                candidate_id,
                cand.attempts,
                exc,
            )
            return {"ok": False, "reason": str(exc)}

    finally:
        sess.close()
