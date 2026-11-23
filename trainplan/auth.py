"""Реєстрація та автентифікація користувачів (логін і пароль, без електронної пошти).

Пароль не зберігається: у базі лежить лише його хеш (werkzeug.security, алгоритм scrypt).
"""
from __future__ import annotations
import re
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

LOGIN_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
MIN_PASSWORD = 6


def validate(login: str, password: str) -> str | None:
    """Повертає текст помилки або None, якщо дані коректні."""
    if not LOGIN_RE.match(login or ''):
        return 'Логін: 3–32 символи – латинські літери, цифри, «_», «.», «-».'
    if len(password or '') < MIN_PASSWORD:
        return f'Пароль має містити щонайменше {MIN_PASSWORD} символів.'
    return None


def register(repo, login: str, password: str) -> tuple[int | None, str | None]:
    err = validate(login, password)
    if err:
        return None, err
    if repo.user_by_login(login):
        return None, 'Користувач з таким логіном уже існує.'
    return repo.create_user(login, generate_password_hash(password)), None


def authenticate(repo, login: str, password: str) -> int | None:
    u = repo.user_by_login(login or '')
    if u and check_password_hash(u['password_hash'], password or ''):
        return u['id']
    return None


def secret_key(path: Path) -> str:
    """Ключ підпису сесій: зберігається у файлі поруч із базою, щоб сесії не скидалися після перезапуску."""
    path = Path(path)
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_hex(32)
    path.write_text(key)
    return key
