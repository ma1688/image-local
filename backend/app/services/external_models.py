"""调外部 OpenAI 兼容接口的 /v1/models。"""

from __future__ import annotations

import httpx
from loguru import logger

from app.schemas.api_profile import ModelInfo

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def _normalize(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


async def fetch_models(base_url: str, api_key: str) -> list[ModelInfo]:
    """调用 GET <base>/v1/models，返回模型列表。"""
    base = _normalize(base_url)
    url = f"{base}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("fetch_models network error: {}", exc)
            raise
        if resp.status_code in (401, 403):
            raise PermissionError("API Key 无效或无权限")
        if resp.status_code == 404:
            raise LookupError(f"模型列表接口不存在：{url}")
        resp.raise_for_status()
        body = resp.json()

    raw = body.get("data") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        raw = body if isinstance(body, list) else []

    out: list[ModelInfo] = []
    for item in raw:
        if isinstance(item, dict) and "id" in item:
            out.append(
                ModelInfo(
                    id=str(item["id"]),
                    object=item.get("object"),
                    owned_by=item.get("owned_by"),
                )
            )
        elif isinstance(item, str):
            out.append(ModelInfo(id=item))
    return out
