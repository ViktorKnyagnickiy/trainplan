"""Демо-режим: акаунт «demo» з готовим планом та історією тренувань.

Кожен вхід у демо-режим відновлює демо-дані до початкового стану.
"""
from __future__ import annotations
import secrets
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from .adaptation import SetLog
from .domain import Profile

DEMO_LOGIN = 'demo'
DEMO_PROFILE = dict(goal='гіпертрофія', level=2, days=(1, 2, 4, 5), tmax=75,
                    equipment=frozenset({'штанга', 'гантелі', 'лава', 'турнік', 'тренажер', 'блок', 'власна_вага'}),
                    name='Демо-профіль')


def _clear(repo, uid):
    repo.db.execute('DELETE FROM plan WHERE user_id=?', (uid,))       # plan_item і set_log видаляються каскадно
    repo.db.execute('DELETE FROM profile WHERE user_id=?', (uid,))
    repo.db.commit()


def ensure_demo(repo, service, password: str | None = None) -> int:
    """Створює (або скидає) демо-акаунт і повертає його id."""
    row = repo.user_by_login(DEMO_LOGIN)
    if row:
        uid = row['id']
        if password:
            repo.db.execute('UPDATE user SET password_hash=? WHERE id=?', (generate_password_hash(password), uid))
        _clear(repo, uid)
    else:
        uid = repo.create_user(DEMO_LOGIN, generate_password_hash(password or secrets.token_hex(16)))
    res = service.create_plan(Profile(**DEMO_PROFILE), [False] * 7, [], user_id=uid)
    if not res['ok']:
        raise RuntimeError(res['message'])
    # три заняття історії для першої вправи кожного дня (прогрес → у межах діапазону → прогрес);
    # заняття припадають на дні плану (1 = понеділок), останнє — у найближчий минулий такий день
    today = date.today()
    items = repo.db.execute('SELECT * FROM plan_item WHERE plan_id=? AND position=0', (res['plan_id'],)).fetchall()
    last = {it['id']: today - timedelta(days=(today.isoweekday() - it['day'] - 1) % 7 + 1) for it in items}
    first = min(last.values()) - timedelta(days=14)
    created = (first - timedelta(days=first.isoweekday() % 7 or 7)).isoformat() + 'T18:30:00'  # попередня неділя
    repo.db.execute('UPDATE plan SET created_at=? WHERE id=?', (created, res['plan_id']))
    repo.db.execute('UPDATE profile SET created_at=? WHERE user_id=?', (created, uid))
    for item in items:
        load = 40.0
        for week, (reps, rir) in enumerate([(item['reps_max'], 2), (item['reps_min'] + 1, 2), (item['reps_max'], 2)]):
            sets = [SetLog(load, reps, rir) for _ in range(item['sets'])]
            day = last[item['id']] - timedelta(days=7 * (2 - week))
            load = service.record_session(item['id'], sets, day)['load']
    repo.db.commit()
    return uid
