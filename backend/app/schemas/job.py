from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    template_code: str = Field(min_length=1, max_length=64)
    api_profile_id: int
    model: str = Field(min_length=1, max_length=128)
    size: str = Field(default="1024x1024", max_length=32)
    prompt: str = Field(default="")
    candidates_per_image: int = Field(default=1, ge=1, le=6)
    auto_retry: bool = True
    retry_max: int = Field(default=1, ge=1, le=5)
    output_dir: str = Field(min_length=1)
    source_paths: list[str] = Field(min_length=1)


class JobCandidateRead(BaseModel):
    id: int
    job_id: int
    item_id: int
    index: int
    status: str
    output_path: str | None = None
    attempts: int
    last_error: str | None = None
    is_selected: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class CandidateSelectRequest(BaseModel):
    is_selected: bool


class JobItemRead(BaseModel):
    id: int
    job_id: int
    source_path: str
    source_name: str
    candidates: list[JobCandidateRead] = []

    model_config = {"from_attributes": True}


class JobRead(BaseModel):
    id: int
    template_code: str
    api_profile_id: int
    model: str
    size: str
    prompt: str
    candidates_per_image: int
    auto_retry: bool
    retry_max: int
    output_dir: str
    status: str
    total_candidates: int
    succeeded_count: int
    failed_count: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetail(JobRead):
    items: list[JobItemRead] = []


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int
