"""调用 OpenAI 兼容图像生成接口。

支持两种返回格式：
1. ``{"data": [{"b64_json": "..."}]}``
2. ``{"data": [{"url": "https://..."}]}``

调用约定（截图与方案 5.2 节）：
- ``POST {base_url}/v1/images/edits``：带参考图的 gpt-image-* 模型
- ``POST {base_url}/v1/images/generations``：其它兼容生成模型
- multipart 表单：``image`` = 参考图（一张），``prompt``、``model``、``size``、``n=1``
- 头部：``Authorization: Bearer <key>``
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger


class GenerationError(RuntimeError):
    """生成失败的统一异常。"""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class GenerationRequest:
    base_url: str
    api_key: str
    model: str
    size: str
    prompt: str
    source_image_path: Path
    n: int = 1
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class GenerationResultImage:
    image_bytes: bytes
    mime_type: str  # 仅用于命名扩展名


def _normalize_base(base_url: str) -> str:
    return base_url.rstrip("/")


def _endpoint_for(req: GenerationRequest) -> str:
    """选择图像接口端点。

    gpt-image-* 的参考图编辑语义应走 /v1/images/edits；如果把图片 multipart
    发到 /generations，部分 OpenAI 兼容网关会降级/转发到 DALL-E 生成链路，
    最终报出“model dall-e”而不是用户选择的 gpt-image-*。
    """
    base = _normalize_base(req.base_url)
    if req.source_image_path and req.model.lower().startswith("gpt-image"):
        return f"{base}/v1/images/edits"
    return f"{base}/v1/images/generations"


def _looks_non_retryable_provider_error(body: str) -> bool:
    """识别被上游错误地包成 5xx 的“配置/模型不可用”错误。

    一些 OpenAI 兼容网关会把模型不存在、渠道不存在、额度组无可用渠道等
    稳定失败包装成 HTTP 503。继续重试同一个请求只会重复消耗时间/队列，
    应当直接失败并把原因展示给用户。
    """
    lower = body.lower()
    markers = (
        "model_not_found",
        "model not found",
        "no available channel for model",
        "no channel available for model",
        "channel not found",
        "unsupported model",
        "invalid model",
    )
    return any(m in lower for m in markers)


def _decode_data(item: dict[str, object]) -> bytes:
    if "b64_json" in item and isinstance(item["b64_json"], str):
        return base64.b64decode(item["b64_json"])
    if "url" in item and isinstance(item["url"], str):
        # 同步下载
        with httpx.Client(timeout=30.0) as cli:
            r = cli.get(item["url"])
            r.raise_for_status()
            return r.content
    raise GenerationError("response item missing both b64_json and url", retryable=False)


def generate_one(req: GenerationRequest) -> GenerationResultImage:
    """同步调用一次生成接口，返回首张图像字节。

    单候选语义：``n=1``；多候选由调用方在 task 层并发。
    """
    url = _endpoint_for(req)

    if not req.source_image_path.exists():
        raise GenerationError(
            f"source image not found: {req.source_image_path.as_posix()}",
            retryable=False,
        )

    headers = {"Authorization": f"Bearer {req.api_key}"}
    form_data = {
        "model": req.model,
        "prompt": req.prompt,
        "size": req.size,
        "n": str(req.n),
        "response_format": "b64_json",
    }
    files = {
        "image": (
            req.source_image_path.name,
            req.source_image_path.open("rb"),
            "image/png",
        ),
    }

    logger.info(
        "[generate] POST {} model={} size={} prompt_len={} image={}",
        url,
        req.model,
        req.size,
        len(req.prompt),
        req.source_image_path.as_posix(),
    )

    try:
        with httpx.Client(timeout=req.timeout_seconds) as cli:
            resp = cli.post(url, headers=headers, data=form_data, files=files)
    except httpx.ConnectError as exc:
        raise GenerationError(f"ConnectError: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise GenerationError(f"Timeout: {exc}") from exc
    except httpx.HTTPError as exc:
        raise GenerationError(f"HTTPError: {exc}") from exc
    finally:
        files["image"][1].close()

    status = resp.status_code
    if status >= 400:
        body = resp.text[:500]
        if status in (401, 403):
            raise GenerationError(f"auth failed ({status}): {body}", retryable=False)
        if status == 429:
            raise GenerationError(f"rate limited (429): {body}", retryable=True)
        if 400 <= status < 500:
            raise GenerationError(f"client error ({status}): {body}", retryable=False)
        if _looks_non_retryable_provider_error(body):
            raise GenerationError(f"provider config error ({status}): {body}", retryable=False)
        raise GenerationError(f"server error ({status}): {body}", retryable=True)

    try:
        payload = resp.json()
    except ValueError as exc:
        raise GenerationError(f"non-json response: {resp.text[:500]}") from exc

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise GenerationError(
            f"empty data in response: {str(payload)[:500]}",
            retryable=False,
        )

    image_bytes = _decode_data(items[0])
    return GenerationResultImage(image_bytes=image_bytes, mime_type="image/png")
