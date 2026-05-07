"""4 套内置流程模板（与截图截图流程模板 Tab 1:1 对齐）。"""

from __future__ import annotations

from typing import TypedDict


class BuiltinTemplate(TypedDict):
    code: str
    name: str
    prompt_template: str
    default_model: str | None
    default_size: str | None


BUILTIN_TEMPLATES: list[BuiltinTemplate] = [
    {
        "code": "ref_batch",
        "name": "参考图批量生成",
        "prompt_template": (
            "请参考参考图中的主体进行风格化处理，保持主体结构不变，"
            "提升质感与光影效果，生成适合电商展示的精致图片。\n"
            "{prompt}"
        ),
        "default_model": "gpt-image-2",
        "default_size": "1024x1024",
    },
    {
        "code": "product_style",
        "name": "商品图风格化",
        "prompt_template": (
            "保持原商品主体结构不变，仅替换背景与光影风格，"
            "突出产品质感，背景干净简洁。\n{prompt}"
        ),
        "default_model": "gpt-image-2",
        "default_size": "1024x1024",
    },
    {
        "code": "gift_box",
        "name": "贺卡/礼盒改图",
        "prompt_template": (
            "基于参考图生成节日主题贺卡/礼盒外观图，"
            "突出节日氛围、配色温暖。\n{prompt}"
        ),
        "default_model": "gpt-image-2",
        "default_size": "1024x1024",
    },
    {
        "code": "custom",
        "name": "自定义流程",
        "prompt_template": "{prompt}",
        "default_model": None,
        "default_size": "1024x1024",
    },
]
