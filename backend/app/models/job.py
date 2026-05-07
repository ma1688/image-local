from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.db import Base


class Job(Base):
    """一次批量生成任务。

    生命周期：queued → running → succeeded / failed / cancelled
    """

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_code = Column(String(64), nullable=False)
    api_profile_id = Column(Integer, ForeignKey("api_profiles.id"), nullable=False)
    model = Column(String(128), nullable=False)
    size = Column(String(32), nullable=False)
    prompt = Column(Text, nullable=False, default="")
    candidates_per_image = Column(Integer, nullable=False, default=1)
    auto_retry = Column(Integer, nullable=False, default=1)  # 0/1
    retry_max = Column(Integer, nullable=False, default=1)
    output_dir = Column(String(1024), nullable=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    total_candidates = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    extra = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    items = relationship("JobItem", back_populates="job", cascade="all, delete-orphan")
    candidates = relationship(
        "JobCandidate", back_populates="job", cascade="all, delete-orphan"
    )


class JobItem(Base):
    """一张源图（参考图）。"""

    __tablename__ = "job_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    source_path = Column(String(1024), nullable=False)
    source_name = Column(String(256), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)

    job = relationship("Job", back_populates="items")
    candidates = relationship(
        "JobCandidate", back_populates="item", cascade="all, delete-orphan"
    )


class JobCandidate(Base):
    """单张源图的某一候选生成结果。"""

    __tablename__ = "job_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("job_items.id", ondelete="CASCADE"), nullable=False)
    index = Column(Integer, nullable=False)
    status = Column(
        String(32), nullable=False, default="queued", index=True
    )  # queued | running | succeeded | failed | cancelled
    output_path = Column(String(1024), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    is_selected = Column(Integer, nullable=False, default=0, index=True)  # 0/1
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    job = relationship("Job", back_populates="candidates")
    item = relationship("JobItem", back_populates="candidates")
