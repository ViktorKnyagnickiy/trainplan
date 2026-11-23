"""Наскрізний тест вебзастосунку: формування плану, перегляд, журнал і адаптація."""
import os
import re


def test_end_to_end(tmp_path):
    os.environ['TRAINPLAN_DB'] = str(tmp_path / 'test.db')
    import importlib, app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    c.post('/register', data={'login': 'tester', 'password': 'secret123', 'password2': 'secret123'})
    assert c.get('/').status_code == 200
    form = {'name': 'Тест', 'goal': 'гіпертрофія', 'level': '2', 'tmax': '60', 'days': ['1', '3', '5'],
            'equipment': ['гантелі', 'лава', 'турнік'], 'local': ['поперек']}
    form.update({f'q{i}': 'ні' for i in range(7)})
    r = c.post('/plan', data=form)
    assert r.status_code == 302
    page = c.get(r.headers['Location']).get_data(as_text=True)
    assert 'Тижневий план' in page
    item_id = int(re.search(r'/log/(\d+)', page).group(1))
    r = c.post(f'/log/{item_id}', data={'load0': '20', 'reps0': '12', 'rir0': '2', 'load1': '20', 'reps1': '12',
                                        'rir1': '2', 'load2': '20', 'reps2': '12', 'rir2': '2',
                                        'load3': '20', 'reps3': '12', 'rir3': '2'})
    assert 'Ситуація: прогрес' in r.get_data(as_text=True)
    # позитивна відповідь на загальне питання скринінгу блокує формування плану
    form['q0'] = 'так'
    assert 'лікар' in c.post('/plan', data=form).get_data(as_text=True)
