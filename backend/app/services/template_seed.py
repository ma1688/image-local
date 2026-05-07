"""幂等地把内置模板写入数据库。"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.core.db import session_scope
from app.models.template import Template
from app.templates_data.built_in import BUILTIN_TEMPLATES


async def seed_builtin_templates() -> None:
    async with session_scope() as session:
        existing_codes_result = await session.execute(
            select(Template.code).where(Template.builtin.is_(True))
        )
        existing_codes = {row[0] for row in existing_codes_result.all()}

        added = 0
        for spec in BUILTIN_TEMPLATES:
            if spec["code"] in existing_codes:
                continue
            session.add(
                Template(
                    code=spec["code"],
                    name=spec["name"],
                    prompt_template=spec["prompt_template"],
                    default_model=spec["default_model"],
                    default_size=spec["default_size"],
                    builtin=True,
                )
            )
            added += 1

        if added:
            logger.info("seeded {} builtin templates", added)
        else:
            logger.debug("builtin templates already seeded")
