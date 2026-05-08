"""输出目录兼容：早期前端默认 data/outputs 不应生成到 data/data/outputs。"""

from __future__ import annotations


def test_resolve_output_dir_compat_data_outputs() -> None:
    from app.core.settings import get_settings
    from app.models import Job
    from app.tasks.generate import _resolve_output_dir

    s = get_settings()
    job = Job(id=123, output_dir="data/outputs")

    assert _resolve_output_dir(job) == (s.APP_DATA_DIR / "outputs" / "123").resolve()


def test_resolve_output_dir_plain_outputs() -> None:
    from app.core.settings import get_settings
    from app.models import Job
    from app.tasks.generate import _resolve_output_dir

    s = get_settings()
    job = Job(id=456, output_dir="outputs")

    assert _resolve_output_dir(job) == (s.APP_DATA_DIR / "outputs" / "456").resolve()
