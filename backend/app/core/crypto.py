"""Fernet 对称加密：用于 API Key 等敏感字段持久化。"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from .settings import get_settings


def _is_valid_fernet_key(key: bytes) -> bool:
    """合法 Fernet key 必须是 32 字节经 url-safe base64 编码后 44 字节。"""
    try:
        Fernet(key)
        return True
    except (ValueError, TypeError):
        return False


def _load_or_create_key() -> bytes:
    settings = get_settings()

    env_value = settings.SECRET_FERNET_KEY.strip()
    if env_value:
        env_bytes = env_value.encode("utf-8")
        if _is_valid_fernet_key(env_bytes):
            return env_bytes
        logger.warning(
            "SECRET_FERNET_KEY 不是合法的 Fernet key（应为 32 字节 url-safe base64 编码），已忽略并改用 {}",
            settings.fernet_key_path,
        )

    key_file = settings.fernet_key_path
    if key_file.exists():
        existing = key_file.read_bytes().strip()
        if _is_valid_fernet_key(existing):
            return existing
        logger.warning("{} 中的 fernet key 无效，将重新生成", key_file)

    key_file.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()
    key_file.write_bytes(new_key)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    logger.warning(
        "未配置 SECRET_FERNET_KEY，已自动生成并写入 {}。备份此文件以避免数据无法解密。",
        key_file,
    )
    return new_key


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Fernet token invalid; key mismatch?") from exc


def mask(plain: str, keep: int = 4) -> str:
    """返回掩码形式（用于前端展示）。"""
    if not plain:
        return ""
    if len(plain) <= keep:
        return "*" * len(plain)
    return f"{'*' * (len(plain) - keep)}{plain[-keep:]}"
