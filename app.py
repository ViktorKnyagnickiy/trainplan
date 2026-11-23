"""Вебзастосунок (Flask). Запуск: python app.py → http://127.0.0.1:5000"""
import os
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, abort, session, g

from trainplan import config as C
from trainplan import auth
from trainplan.demo import ensure_demo, DEMO_LOGIN
from trainplan.adaptation import SetLog
from trainplan.domain import Profile, DATA
from trainplan.linmodel import available_solvers
from trainplan.repository import Repository
from trainplan.screening import GENERAL_QUESTIONS, LOCAL_TAGS
from trainplan.generator import set_time
from trainplan.service import PlanService

BASE = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE / 'web' / 'templates'), static_folder=str(BASE / 'web' / 'static'))
DEMO_ENABLED = os.environ.get('TRAINPLAN_DEMO', '1') != '0'
DB_PATH = Path(os.environ.get('TRAINPLAN_DB', BASE / 'trainplan.db'))
repo = Repository(DB_PATH)
app.secret_key = os.environ.get('TRAINPLAN_SECRET') or auth.secret_key(DB_PATH.with_suffix('.key'))
repo.import_exercises_csv(DATA / 'exercises.csv')
service = PlanService(repo)

EQUIPMENT = ['штанга', 'гантелі', 'лава', 'турнік', 'бруси', 'тренажер', 'блок', 'гиря', 'гума']


@app.before_request
def load_user():
    uid = session.get('uid')
    g.user = repo.user_by_id(uid) if uid else None


@app.context_processor
def ctx():
    u = g.get('user')
    return dict(DAY_NAMES=C.DAY_NAMES, DAY_NAMES_FULL=DAY_NAMES_FULL, solver=available_solvers()[0], user=u,
                demo_mode=bool(u and u['login'] == DEMO_LOGIN), demo_enabled=DEMO_ENABLED)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            return redirect(url_for('login', next=request.path))
        return view(*a, **kw)
    return wrapped


DAY_NAMES_FULL = {1: 'Понеділок', 2: 'Вівторок', 3: 'Середа', 4: 'Четвер', 5: 'П’ятниця', 6: 'Субота', 7: 'Неділя'}
LEVEL_NAMES = {1: 'початковий', 2: 'середній', 3: 'високий'}
CONTRA_SHORT = {'плече': 'плечовий суглоб', 'поперек': 'поперек / хребет', 'коліно': 'колінний суглоб'}


def profile_summary(data_json):
    """Параметри профілю, з якими сформовано план, у вигляді для показу."""
    import json
    d = json.loads(data_json)
    return dict(
        goal=d['goal'], level=LEVEL_NAMES.get(int(d['level']), d['level']),
        days=', '.join(C.DAY_NAMES[int(x)] for x in d['days']), tmax=f"{float(d['tmax']):g} хв",
        equipment=', '.join(q.replace('власна_вага', 'власна вага') for q in d['equipment']) or '—',
        contra=', '.join(CONTRA_SHORT.get(t, t) for t in d.get('contra', [])) or 'немає',
        name=d.get('name') or '')


def check_owner(user_id):
    """Користувач бачить лише власні плани та журнал."""
    if user_id != g.user['id']:
        abort(403)


# ------------------------------------------------------------ акаунти
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        f = request.form
        if f.get('password') != f.get('password2'):
            error = 'Паролі не збігаються.'
        else:
            uid, error = auth.register(repo, f.get('login', '').strip(), f.get('password', ''))
            if uid:
                session.clear(); session['uid'] = uid
                return redirect(url_for('index'))
    return render_template('auth.html', mode='register', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        uid = auth.authenticate(repo, request.form.get('login', '').strip(), request.form.get('password', ''))
        if uid:
            session.clear(); session['uid'] = uid
            nxt = request.args.get('next', '')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('index'))
        error = 'Невірний логін або пароль.'
    return render_template('auth.html', mode='login', error=error)


@app.post('/demo')
def demo():
    if not DEMO_ENABLED:
        abort(404)
    uid = ensure_demo(repo, service)
    session.clear(); session['uid'] = uid
    return redirect(url_for('index'))


@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ------------------------------------------------------------ плани


@app.get('/')
@login_required
def index():
    plans = [dict(row=p, prof=profile_summary(p['profile_data'])) for p in repo.latest_plans(g.user['id'], 50)]
    return render_template('index.html', plans=plans)


@app.get('/new')
@login_required
def new_plan():
    return render_template('new.html', goals=list(C.GOALS), equipment=EQUIPMENT,
                           questions=GENERAL_QUESTIONS, local=LOCAL_TAGS)


@app.post('/plan')
@login_required
def create_plan():
    f = request.form
    days = tuple(sorted(int(d) for d in f.getlist('days')))
    if not days:
        return render_template('message.html', title='Помилка', text='Оберіть хоча б один тренувальний день.')
    profile = Profile(goal=f['goal'], level=int(f['level']), days=days, tmax=float(f['tmax']),
                      equipment=frozenset(f.getlist('equipment')) | {'власна_вага'}, name=f.get('name', ''))
    answers = [f.get(f'q{i}') == 'так' for i in range(len(GENERAL_QUESTIONS))]
    res = service.create_plan(profile, answers, f.getlist('local'), user_id=g.user['id'])
    if not res['ok']:
        return render_template('message.html', title='План не сформовано', text=res['message'])
    return redirect(url_for('show_plan', plan_id=res['plan_id']))


@app.get('/plan/<int:plan_id>')
@login_required
def show_plan(plan_id):
    plan = repo.plan_row(plan_id) or abort(404)
    check_owner(plan['user_id'])
    items = repo.plan_items(plan_id)
    days = {}
    for it in items:
        days.setdefault(it['day'], []).append(it)
    import json
    pdata = json.loads(repo.db.execute('SELECT data FROM profile WHERE id=?', (plan['profile_id'],)).fetchone()['data'])
    prof = profile_summary(json.dumps(pdata))
    # тривалість заняття за формулою (2.7): розминка + перехід і підходи кожної вправи
    minutes = {d: round(C.T_WARMUP + sum(C.T_TRANSITION + it['sets'] * set_time(service.byid[it['exercise_id']], pdata['goal'])
                                         for it in its)) for d, its in days.items()}
    group_days = {}
    for it in items:
        group_days.setdefault(service.byid[it['exercise_id']].primary, set()).add(it['day'])
    stats = dict(n_ex=len(items), n_sets=sum(it['sets'] for it in items),
                 freq=sum(len(v) >= 2 for v in group_days.values()), n_groups=len(C.GROUP_NAMES))
    return render_template('plan.html', plan=plan, days=days, prof=prof, minutes=minutes, stats=stats)


@app.post('/plan/<int:plan_id>/delete')
@login_required
def delete_plan(plan_id):
    plan = repo.plan_row(plan_id) or abort(404)
    check_owner(plan['user_id'])
    repo.delete_plan(plan_id)
    return redirect(url_for('index'))


@app.route('/log/<int:item_id>', methods=['GET', 'POST'])
@login_required
def log(item_id):
    item = repo.db.execute('SELECT pi.*, e.name FROM plan_item pi JOIN exercise e ON e.id=pi.exercise_id '
                           'WHERE pi.id=?', (item_id,)).fetchone() or abort(404)
    check_owner(repo.plan_row(item['plan_id'])['user_id'])
    rec = None
    if request.method == 'POST':
        f = request.form
        sets = [SetLog(float(f[f'load{i}']), int(f[f'reps{i}']), int(f[f'rir{i}']))
                for i in range(item['sets']) if f.get(f'reps{i}')]
        if sets:
            rec = service.record_session(item_id, sets)
            item = repo.db.execute('SELECT pi.*, e.name FROM plan_item pi JOIN exercise e ON e.id=pi.exercise_id '
                                   'WHERE pi.id=?', (item_id,)).fetchone()
    rec = rec or service.last_recommendation(item_id)
    logs = repo.item_logs(item_id)
    sessions = []                                             # заняття: дата, вага, повторення, RIR
    for l in logs:
        if not sessions or sessions[-1]['date'] != l['session_date']:
            sessions.append(dict(date=l['session_date'], load=l['load'], reps=[], rir=[]))
        s = sessions[-1]; s['load'] = max(s['load'], l['load']); s['reps'].append(l['reps']); s['rir'].append(l['rir'])
    plan_day = repo.db.execute('SELECT day FROM plan_item WHERE id=?', (item_id,)).fetchone()['day']
    return render_template('log.html', item=item, rec=rec, sessions=sessions, chart=weight_chart(sessions, rec),
                           day=C.DAY_NAMES[plan_day], rest=item['rest'])


MONTHS = ['січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру']


@app.template_filter('num')
def num(v):
    """Число з десятковою комою (47,5)."""
    return f'{float(v):g}'.replace('.', ',')


@app.template_filter('short_date')
def short_date(iso):
    y, m, d = iso[:10].split('-')
    return f'{int(d)} {MONTHS[int(m) - 1]}'


def weight_chart(sessions, rec, W=340, H=130, px=34, py=16):
    """SVG-графік робочої ваги за заняттями з прогнозом на наступне заняття (пунктир)."""
    pts = [(short_date(s['date']), s['load']) for s in sessions[-8:]]
    if rec and pts:
        pts.append(('далі', rec['load']))
    if len(pts) < 2:
        return None
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi - lo < 5:
        lo, hi = lo - 2.5, hi + 2.5
    X = lambda i: px + i * (W - 2 * px) / (len(pts) - 1)
    Y = lambda v: H - py - 12 - (v - lo) * (H - 2 * py - 12) / (hi - lo)
    n_hist = len(pts) - (1 if rec else 0)
    grid = sorted({lo, (lo + hi) / 2, hi})
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Графік робочої ваги">']
    out += [f'<line x1="{px}" x2="{W - px + 6}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="g"/>'
            f'<text x="2" y="{Y(v) + 4:.1f}" class="t">{num(v)}</text>' for v in grid]
    hist = ' '.join(f'{X(i):.1f},{Y(v):.1f}' for i, (_, v) in enumerate(pts[:n_hist]))
    out.append(f'<polyline points="{hist}" class="line"/>')
    if rec:
        i = len(pts) - 1
        out.append(f'<line x1="{X(i - 1):.1f}" y1="{Y(pts[i - 1][1]):.1f}" x2="{X(i):.1f}" y2="{Y(pts[i][1]):.1f}" class="next"/>'
                   f'<circle cx="{X(i):.1f}" cy="{Y(pts[i][1]):.1f}" r="5.5" class="dot-next"/>')
    out += [f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4.5" class="dot"/>' for i, (_, v) in enumerate(pts[:n_hist])]
    out += [f'<text x="{X(i):.1f}" y="{H - 2}" class="t" text-anchor="middle">{lbl}</text>' for i, (lbl, _) in enumerate(pts)]
    out.append('</svg>')
    return ''.join(out)


@app.get('/exercises')
def exercises():
    return render_template('exercises.html', rows=repo.exercises_csv_rows(), groups=C.GROUP_NAMES)


@app.errorhandler(403)
def forbidden(e):
    return render_template('message.html', title='Доступ заборонено',
                           text='Цей план належить іншому користувачеві.'), 403


if __name__ == '__main__':
    app.run(debug=False)
