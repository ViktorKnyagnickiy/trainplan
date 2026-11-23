import sys
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5000'
OUT = sys.argv[1]


def fill_form(pg):
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


def log_session(pg, link, load, reps, rir, name):
    pg.goto(BASE + link)
    n = pg.locator('input[name^=reps]').count()
    for i in range(n):
        pg.fill(f'input[name=load{i}]', str(load))
        r = reps[i] if isinstance(reps, list) else reps
        pg.fill(f'input[name=reps{i}]', str(r))
        pg.fill(f'input[name=rir{i}]', str(rir))
    pg.click('button[type=submit]')
    pg.wait_for_load_state()
    print(name, pg.locator('.rec').inner_text())
    pg.screenshot(path=f'{OUT}/{name}', full_page=True)


with sync_playwright() as p:
    b = p.chromium.launch()
    # --- десктоп ---
    pg = b.new_page(viewport={'width': 1280, 'height': 900}, device_scale_factor=2)
    fill_form(pg)
    pg.screenshot(path=f'{OUT}/desktop_1_form.png', full_page=True)
    pg.click('button[type=submit]')
    pg.wait_for_url('**/plan/*', timeout=60000)
    plan_url = pg.url
    pg.screenshot(path=f'{OUT}/desktop_2_plan.png', full_page=True)
    links = [pg.locator('a', has_text='журнал').nth(i).get_attribute('href') for i in range(3)]
    pg.goto(BASE + links[0])
    pg.screenshot(path=f'{OUT}/desktop_3_log_empty.png', full_page=True)
    # адаптація: три ситуації на різних вправах
    log_session(pg, links[0], 60, 12, 2, 'adapt_1_progres.png')
    log_session(pg, links[0], 65, [9, 9, 8], 2, 'adapt_2_u_mezhakh.png')
    log_session(pg, links[0], 65, 12, 4, 'adapt_3_zanadto_legko.png')
    log_session(pg, links[0], 70, [6, 5, 5], 0, 'adapt_4_zanadto_vazhko.png')
    pg.goto(BASE + '/exercises')
    pg.screenshot(path=f'{OUT}/desktop_4_exercises.png', full_page=False)
    # --- мобільна версія ---
    ctx = b.new_context(**p.devices['iPhone 13'])
    m = ctx.new_page()
    fill_form(m)
    m.screenshot(path=f'{OUT}/mobile_1_form.png', full_page=True)
    m.goto(plan_url)
    m.screenshot(path=f'{OUT}/mobile_2_plan.png', full_page=True)
    m.goto(BASE + links[0])
    m.screenshot(path=f'{OUT}/mobile_3_log.png', full_page=True)
    m.goto(BASE + '/exercises')
    m.screenshot(path=f'{OUT}/mobile_4_exercises.png', full_page=False)
    b.close()
