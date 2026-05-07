"""路径穿越 / 白名单 / 扫描行为测试（覆盖方案 8.1 节）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


def _make_test_image(p: Path, size: tuple[int, int] = (32, 32), color: str = "red") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(p, format="PNG")


def test_safe_resolve_rejects_empty() -> None:
    from app.services.storage import InvalidPathError, safe_resolve

    with pytest.raises(InvalidPathError):
        safe_resolve("")
    with pytest.raises(InvalidPathError):
        safe_resolve("   ")


def test_safe_resolve_must_exist(tmp_path: Path) -> None:
    from app.services.storage import InvalidPathError, safe_resolve

    with pytest.raises(InvalidPathError):
        safe_resolve(str(tmp_path / "ghost"), must_exist=True)


def test_safe_resolve_under_blocks_traversal(tmp_path: Path) -> None:
    from app.services.storage import InvalidPathError, safe_resolve_under

    root = tmp_path / "root"
    root.mkdir()
    inside = root / "ok.txt"
    inside.write_text("hi")

    # 在 root 下 OK
    assert safe_resolve_under(str(inside), root).is_file()

    # 同盘符越级
    with pytest.raises(InvalidPathError):
        safe_resolve_under(str(tmp_path / "evil.txt"), root)

    # 相对路径 .. 越级
    with pytest.raises(InvalidPathError):
        safe_resolve_under("../evil.txt", root)


def test_scan_directory_filters_extensions(tmp_path: Path) -> None:
    from app.services.storage import scan_directory

    # 制造一些图片 + 一些非图片
    _make_test_image(tmp_path / "a.png")
    _make_test_image(tmp_path / "b.jpg", color="blue")
    (tmp_path / "c.txt").write_text("not image")
    (tmp_path / "d.exe").write_bytes(b"\x00\x01\x02")
    sub = tmp_path / "sub"
    sub.mkdir()
    _make_test_image(sub / "e.webp", color="green")

    items, total, truncated = scan_directory(str(tmp_path), recursive=False)
    names = sorted([i.name for i in items])
    assert names == ["a.png", "b.jpg"]
    assert total == 2
    assert truncated is False

    # recursive
    items_r, total_r, _ = scan_directory(str(tmp_path), recursive=True)
    assert {i.name for i in items_r} == {"a.png", "b.jpg", "e.webp"}
    assert total_r == 3


def test_scan_marks_oversize_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import settings as settings_mod
    from app.services.storage import scan_directory

    # 把单图大小上限调到 100 字节
    monkeypatch.setenv("SOURCE_IMAGE_MAX_BYTES", "100")
    settings_mod.get_settings.cache_clear()

    big = tmp_path / "big.png"
    _make_test_image(big, size=(64, 64))
    items, _, _ = scan_directory(str(tmp_path), recursive=False)
    assert len(items) == 1
    assert items[0].valid is False
    assert items[0].reason and "size" in items[0].reason

    settings_mod.get_settings.cache_clear()


def test_scan_truncates_when_too_many(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import settings as settings_mod
    from app.services.storage import scan_directory

    monkeypatch.setenv("SCAN_FILE_LIMIT", "3")
    settings_mod.get_settings.cache_clear()

    for i in range(5):
        _make_test_image(tmp_path / f"img_{i}.png")

    items, total, truncated = scan_directory(str(tmp_path), recursive=False)
    assert len(items) == 3
    assert total == 5
    assert truncated is True

    settings_mod.get_settings.cache_clear()
