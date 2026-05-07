"""验证 _InterceptHandler 在消息含裸 ``{ }`` 时不会因二次 format 失败。

复现历史风险：``record.getMessage()`` 已经被 stdlib 按 ``%`` 占位符展开，
若再被 loguru 当作 ``str.format`` 模板，遇到 ``{xxx}`` 会抛 IndexError/KeyError。
"""

from __future__ import annotations

import io
import logging as stdlib_logging

from loguru import logger as loguru_logger


def _attach_string_sink() -> tuple[io.StringIO, int]:
    buf = io.StringIO()
    sink_id = loguru_logger.add(buf, level="DEBUG", format="{message}")
    return buf, sink_id


def test_intercept_handler_preserves_literal_braces() -> None:
    """SQL / 未占位的模板里 `{ids}` 应原样落到日志，不被 format 二次解析。"""
    from app.core.logging import _InterceptHandler

    buf, sink_id = _attach_string_sink()
    try:
        root = stdlib_logging.getLogger("test.intercept_brace")
        root.handlers.clear()
        root.addHandler(_InterceptHandler())
        root.setLevel(stdlib_logging.DEBUG)

        msg = "Running upgrade with sql: SELECT * FROM x WHERE id IN ({ids})"
        root.info(msg)
        loguru_logger.complete()

        output = buf.getvalue()
        assert "{ids}" in output, f"expected raw braces preserved, got: {output!r}"
        assert "Running upgrade" in output
    finally:
        loguru_logger.remove(sink_id)


def test_intercept_handler_handles_dict_repr_with_braces() -> None:
    """%s 展开后包含 dict repr（带 `{key: value}`）也不应触发二次 format。"""
    from app.core.logging import _InterceptHandler

    buf, sink_id = _attach_string_sink()
    try:
        root = stdlib_logging.getLogger("test.intercept_dict_repr")
        root.handlers.clear()
        root.addHandler(_InterceptHandler())
        root.setLevel(stdlib_logging.DEBUG)

        payload = {"key": "value with {placeholder}"}
        root.info("got payload: %s", payload)
        loguru_logger.complete()

        output = buf.getvalue()
        assert "got payload" in output
        assert "{placeholder}" in output
    finally:
        loguru_logger.remove(sink_id)


def test_intercept_handler_keeps_existing_format_call() -> None:
    """一般无大括号的消息也应正常透传。"""
    from app.core.logging import _InterceptHandler

    buf, sink_id = _attach_string_sink()
    try:
        root = stdlib_logging.getLogger("test.intercept_plain")
        root.handlers.clear()
        root.addHandler(_InterceptHandler())
        root.setLevel(stdlib_logging.DEBUG)

        root.info("plain message %d", 42)
        loguru_logger.complete()

        output = buf.getvalue()
        assert "plain message 42" in output
    finally:
        loguru_logger.remove(sink_id)
