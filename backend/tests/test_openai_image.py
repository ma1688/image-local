"""单测：openai_image 服务对两种返回格式的解析与错误分类。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image


def _make_png(p: Path) -> None:
    Image.new("RGB", (8, 8), "red").save(p, format="PNG")


@pytest.fixture
def src(tmp_path: Path) -> Path:
    f = tmp_path / "src.png"
    _make_png(f)
    return f


def _b64_image_bytes() -> str:
    img_bytes = b"\x89PNG_FAKE_BYTES"
    return base64.b64encode(img_bytes).decode("utf-8")


def test_generate_one_b64_path(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import openai_image as svc

    payload = {"data": [{"b64_json": _b64_image_bytes()}]}

    class _MockResponse:
        status_code = 200

        def json(self) -> Any:
            return payload

        @property
        def text(self) -> str:
            return ""

    class _MockClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> _MockClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, *_: Any, **__: Any) -> _MockResponse:
            return _MockResponse()

        def get(self, *_: Any, **__: Any) -> _MockResponse:
            return _MockResponse()

    monkeypatch.setattr(svc.httpx, "Client", _MockClient)

    req = svc.GenerationRequest(
        base_url="http://example.test",
        api_key="sk-x",
        model="gpt-image-2",
        size="1024x1024",
        prompt="hello",
        source_image_path=src,
    )
    result = svc.generate_one(req)
    assert result.image_bytes == b"\x89PNG_FAKE_BYTES"


def test_generate_one_url_path(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """走 url 分支时会调用 cli.get(url) 拿图片字节。"""
    from app.services import openai_image as svc

    image_bytes = b"\x89PNG_FROM_URL"

    class _Resp:
        def __init__(self, status: int, j: Any | None = None, body: bytes | str = "") -> None:
            self.status_code = status
            self._j = j
            self.text = body if isinstance(body, str) else ""
            self.content = body if isinstance(body, bytes) else b""

        def json(self) -> Any:
            return self._j

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    class _MockClient:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> _MockClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, *_: Any, **__: Any) -> _Resp:
            return _Resp(
                200,
                j={"data": [{"url": "http://img/x.png"}]},
            )

        def get(self, *_: Any, **__: Any) -> _Resp:
            return _Resp(200, body=image_bytes)

    monkeypatch.setattr(svc.httpx, "Client", _MockClient)

    req = svc.GenerationRequest(
        base_url="http://example.test",
        api_key="sk-x",
        model="m",
        size="1024x1024",
        prompt="p",
        source_image_path=src,
    )
    result = svc.generate_one(req)
    assert result.image_bytes == image_bytes


def test_generate_one_connect_error(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """连接错误应转换成 GenerationError(retryable=True)。"""
    from app.services import openai_image as svc

    class _Boom:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> _Boom:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, *_: Any, **__: Any) -> Any:
            raise httpx.ConnectError("dns")

    monkeypatch.setattr(svc.httpx, "Client", _Boom)

    req = svc.GenerationRequest(
        base_url="http://no-such",
        api_key="k",
        model="m",
        size="1024x1024",
        prompt="p",
        source_image_path=src,
    )
    with pytest.raises(svc.GenerationError) as ei:
        svc.generate_one(req)
    assert ei.value.retryable is True
    assert "ConnectError" in str(ei.value)


def test_generate_one_4xx_non_retryable(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """401 应该 retryable=False。"""
    from app.services import openai_image as svc

    class _Resp:
        status_code = 401
        text = '{"error": "auth"}'

        def json(self) -> Any:
            return {"error": "auth"}

    class _Cli:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> _Cli:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, *_: Any, **__: Any) -> _Resp:
            return _Resp()

    monkeypatch.setattr(svc.httpx, "Client", _Cli)

    req = svc.GenerationRequest(
        base_url="http://x",
        api_key="bad",
        model="m",
        size="1024x1024",
        prompt="p",
        source_image_path=src,
    )
    with pytest.raises(svc.GenerationError) as ei:
        svc.generate_one(req)
    assert ei.value.retryable is False
