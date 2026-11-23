"""Знімки екрана вебінтерфейсу для пояснювальної записки (запускається при працюючому app.py)."""
import sys
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5057'
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1280, 'height': 900}, device_scale_factor=1.5)
    pg.goto(BASE + '/')
    pg.fill('input[name=name]', 'Олена')
    pg.select_option('select[name=goal]', 'гіпертрофія')
    pg.select_option('select[name=level]', '2')
    pg.fill('input[name=tmax]', '60')
    for d in ('1', '3', '5'):
        pg.uncheck(f'input[name=days][value="{d}"]')
    for d in ('1', '2', '4', '5'):
        pg.check(f'input[name=days][value="{d}"]')
    for q in ('штанга', 'тренажер', 'блок', 'турнік'):
        pg.check(f'input[name=equipment][value="{q}"]')
    pg.check('input[name=local][value="поперек"]')
    pg.screenshot(path=f'{OUT}/ui_form.png', full_page=True)
    pg.click('button[type=submit]')
    pg.wait_for_url('**/plan/*', timeout=60000)
    pg.screenshot(path=f'{OUT}/ui_plan.png', full_page=True)
    link = pg.locator('a', has_text='журнал').first.get_attribute('href')
    pg.goto(BASE + link)
    n = pg.locator('input[name^=reps]').count()
    for i in range(n):
        pg.fill(f'input[name=load{i}]', '60')
        pg.fill(f'input[name=reps{i}]', '12')
        pg.fill(f'input[name=rir{i}]', '2')
    pg.click('button[type=submit]')
    pg.screenshot(path=f'{OUT}/ui_log.png', full_page=True)
    b.close()
