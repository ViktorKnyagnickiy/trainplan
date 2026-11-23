"""Тести акаунтів: реєстрація, вхід, розмежування доступу до планів."""
import importlib
import os
import re

FORM = {'name': 'Тест', 'goal': 'гіпертрофія', 'level': '2', 'tmax': '60', 'days': ['1', '3', '5'],
        'equipment': ['гантелі', 'лава', 'турнік']}
FORM.update({f'q{i}': 'ні' for i in range(7)})


def make_client(tmp_path):
    os.environ['TRAINPLAN_DB'] = str(tmp_path / 'auth.db')
    import app as appmod
    importlib.reload(appmod)
    return appmod


def signup(c, login, pw='secret123'):
    return c.post('/register', data={'login': login, 'password': pw, 'password2': pw})


def test_password_is_hashed_and_login_works(tmp_path):
    appmod = make_client(tmp_path)
    c = appmod.app.test_client()
    assert c.get('/').status_code == 302                       # без входу – переадресація на вхід
    assert signup(c, 'viktor').status_code == 302
    row = appmod.repo.user_by_login('viktor')
    assert row['password_hash'] != 'secret123' and row['password_hash'].startswith(('scrypt:', 'pbkdf2:'))
    c.post('/logout')
    assert 'Невірний' in c.post('/login', data={'login': 'viktor', 'password': 'wrong!!'}).get_data(as_text=True)
    assert c.post('/login', data={'login': 'viktor', 'password': 'secret123'}).status_code == 302
    assert c.get('/').status_code == 200


def test_validation(tmp_path):
    c = make_client(tmp_path).app.test_client()
    assert 'Логін' in signup(c, 'ab').get_data(as_text=True)
    assert 'Пароль' in signup(c, 'valid_login', '123').get_data(as_text=True)
    signup(c, 'same')
    c.post('/logout')
    assert 'уже існує' in signup(c, 'same').get_data(as_text=True)


def test_users_see_only_own_plans(tmp_path):
    appmod = make_client(tmp_path)
    a, b = appmod.app.test_client(), appmod.app.test_client()
    signup(a, 'alice'); signup(b, 'bob')
    loc = a.post('/plan', data=FORM).headers['Location']
    plan_id = int(re.search(r'/plan/(\d+)', loc).group(1))
    page = a.get(loc).get_data(as_text=True)
    item_id = int(re.search(r'/log/(\d+)', page).group(1))
    assert b.get(f'/plan/{plan_id}').status_code == 403          # чужий план
    assert b.get(f'/log/{item_id}').status_code == 403           # чужий журнал
    assert f'/plan/{plan_id}' not in b.get('/').get_data(as_text=True)
    assert f'/plan/{plan_id}' in a.get('/').get_data(as_text=True)


def test_demo_mode_resets_data(tmp_path):
    appmod = make_client(tmp_path)
    c = appmod.app.test_client()
    assert 'Демо-режим' in c.get('/login').get_data(as_text=True)
    assert c.post('/demo').status_code == 302
    page = c.get('/').get_data(as_text=True)
    assert 'Демо-режим' in page and 'Демо-профіль' in page
    uid = appmod.repo.user_by_login('demo')['id']
    n_logs = appmod.repo.db.execute('SELECT COUNT(*) FROM set_log').fetchone()[0]
    assert n_logs > 0
    c.post('/plan', data=FORM)                                   # демо-користувач створив ще один план
    assert len(appmod.repo.latest_plans(uid)) == 2
    c.post('/logout'); c.post('/demo')                           # повторний вхід – дані відновлено
    assert len(appmod.repo.latest_plans(uid)) == 1
    assert appmod.repo.db.execute('SELECT COUNT(*) FROM set_log').fetchone()[0] == n_logs


def test_delete_plan(tmp_path):
    appmod = make_client(tmp_path)
    a, b = appmod.app.test_client(), appmod.app.test_client()
    signup(a, 'owner'); signup(b, 'other')
    loc = a.post('/plan', data=FORM).headers['Location']
    plan_id = int(re.search(r'/plan/(\d+)', loc).group(1))
    item_id = int(re.search(r'/log/(\d+)', a.get(loc).get_data(as_text=True)).group(1))
    a.post(f'/log/{item_id}', data={'load0': '20', 'reps0': '12', 'rir0': '2'})
    assert b.post(f'/plan/{plan_id}/delete').status_code == 403      # чужий план видалити не можна
    assert a.post(f'/plan/{plan_id}/delete').status_code == 302
    assert a.get(f'/plan/{plan_id}').status_code == 404
    db = appmod.repo.db
    assert db.execute('SELECT COUNT(*) FROM plan_item WHERE plan_id=?', (plan_id,)).fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM set_log').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM profile').fetchone()[0] == 0
