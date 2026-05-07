"""Prompt 模板变量解析与校验。

当前模板支持的占位符仅 ``{prompt}``。任何 ``{xxx}``（xxx 为合法 Python 变量名）
都会被识别为变量；未支持的变量在创建任务时会发出 warning（不阻断），保留
未来扩展空间（例如增加 ``{aspect}``、``{seed}``）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 仅匹配单 {var}，不匹配 {{escaped}}（避免 KaTeX/JSON 这类转义场景）。
_VAR_PATTERN = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")

KNOWN_VARS: set[str] = {"prompt"}


@dataclass(frozen=True)
class PromptValidation:
    placeholders: list[str]      # 模板中出现的所有变量
    unknown: list[str]           # 未知变量（不在 KNOWN_VARS）
    requires_user_prompt: bool   # 是否包含 {prompt} 但用户未填


def extract_placeholders(template: str) -> list[str]:
    if not template:
        return []
    seen: list[str] = []
    for m in _VAR_PATTERN.finditer(template):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def validate_prompt(template: str, user_prompt: str) -> PromptValidation:
    placeholders = extract_placeholders(template)
    unknown = [p for p in placeholders if p not in KNOWN_VARS]
    requires_user = "prompt" in placeholders and not user_prompt.strip()
    return PromptValidation(
        placeholders=placeholders,
        unknown=unknown,
        requires_user_prompt=requires_user,
    )
