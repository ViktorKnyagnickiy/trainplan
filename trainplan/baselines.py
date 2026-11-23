"""Базові методи для порівняння: жадібна евристика та шаблонні програми."""
from __future__ import annotations
import time

from . import config as C
from .domain import Plan, filter_exercises
from .generator import cyclic_gap, set_time, make_item, order_items


# ----------------------------------------------------------------- жадібна евристика
def greedy(profile, exercises) -> Plan:
    """Для кожного дня послідовно додає вправу з найбільшим зменшенням дефіциту обсягу
    на хвилину часу, дотримуючись жорстких обмежень (обладнання, протипоказання,
    тривалість, відновлення, ≤2 вправи на групу, ≤2 повтори на тиждень)."""
    t0 = time.perf_counter()
    EU = filter_exercises(exercises, profile)
    gp, lp = C.GOALS[profile.goal], C.LEVELS[profile.level]
    smin, smax = lp['sets']
    vmin, vmax = gp['vmin'], lp['vmax']
    vol = {g: 0.0 for g in C.GROUPS}
    used_days = {}               # група -> множина днів, де вона основна
    uses = {}
    plan = Plan(profile=profile, method='Жадібний')
    for d in profile.days:
        items, t = [], C.T_WARMUP
        while len(items) < C.N_MAX:
            best, best_score = None, 0.0
            for e in EU:
                if uses.get(e.id, 0) >= C.MAX_REPEAT_WEEK or any(it.exercise.id == e.id for it in items):
                    continue
                if sum(it.exercise.primary == e.primary for it in items) >= C.PER_GROUP_DAY:
                    continue
                if any(cyclic_gap(d, d2) < C.RECOVERY_DAYS for d2 in used_days.get(e.primary, ())):
                    continue
                need = [vmax - vol[g] for g in C.GROUPS if e.a[g]]
                s = max(smin, min(smax, int(max(0, min(need)) // 1) if need else smax))
                tt = C.T_TRANSITION + s * set_time(e, profile.goal)
                if t + tt > profile.tmax:
                    s = smin
                    tt = C.T_TRANSITION + s * set_time(e, profile.goal)
                    if t + tt > profile.tmax:
                        continue
                gain = sum(C.GROUP_WEIGHT[g] * min(e.a[g] * s, max(0.0, vmin - vol[g])) for g in C.GROUPS)
                score = gain / tt + (0.01 if e.compound and not any(i.exercise.compound for i in items) else 0)
                if score > best_score:
                    best, best_score, best_s, best_t = e, score, s, tt
            if best is None:
                break
            items.append(make_item(best, best_s, profile.goal))
            t += best_t
            uses[best.id] = uses.get(best.id, 0) + 1
            for g in C.GROUPS:
                vol[g] += best.a[g] * best_s
        for it in items:
            used_days.setdefault(it.exercise.primary, set()).add(d)
        plan.days[d] = order_items(items)
    plan.runtime = time.perf_counter() - t0
    plan.status = 'feasible' if any(plan.days.values()) else 'infeasible'
    return plan


# ----------------------------------------------------------------- шаблонні програми
# слот шаблону: (основна група, бажаний патерн або None)
FULL_A = [('КВ', 'ПС'), ('ГР', 'ГЖ'), ('СП', 'ГТ'), ('ЗС', 'ТЗ'), ('ПЛ', 'ВЖ'), ('БІ', None), ('ТР', None)]
FULL_B = [('ЗС', 'ТЗ'), ('СП', 'ВТ'), ('ГР', 'ГЖ'), ('КВ', 'ВП'), ('ПЛ', None), ('ПР', None), ('ЛК', None)]
UPPER = [('ГР', 'ГЖ'), ('СП', 'ГТ'), ('ПЛ', 'ВЖ'), ('СП', 'ВТ'), ('БІ', None), ('ТР', None)]
LOWER = [('КВ', 'ПС'), ('ЗС', 'ТЗ'), ('КВ', 'ВП'), ('СД', None), ('ЛК', None), ('ПР', None)]
PUSH_D = [('ГР', 'ГЖ'), ('ПЛ', 'ВЖ'), ('ГР', None), ('ПЛ', None), ('ТР', None), ('ТР', None)]
PULL_D = [('СП', 'ВТ'), ('СП', 'ГТ'), ('ПЛ', 'ГТ'), ('БІ', None), ('БІ', None), ('ПР', None)]
LEGS_D = [('КВ', 'ПС'), ('ЗС', 'ТЗ'), ('КВ', 'ВП'), ('ЗС', None), ('ЛК', None), ('ПР', None)]

TEMPLATES = {
    1: ('Full body', [FULL_A]),
    2: ('Full body', [FULL_A, FULL_B]),
    3: ('Full body', [FULL_A, FULL_B, FULL_A]),
    4: ('Upper/Lower', [UPPER, LOWER, UPPER, LOWER]),
    5: ('Upper/Lower + Full body', [UPPER, LOWER, FULL_A, UPPER, LOWER]),
    6: ('Push/Pull/Legs', [PUSH_D, PULL_D, LEGS_D, PUSH_D, PULL_D, LEGS_D]),
    7: ('Push/Pull/Legs', [PUSH_D, PULL_D, LEGS_D, PUSH_D, PULL_D, LEGS_D, FULL_A]),
}


def template(profile, exercises, sets=3, trim_to_time=True) -> Plan:
    """Шаблонна програма за кількістю днів. Слоти заповнюються першою допустимою вправою
    (за патерном, інакше за групою); за потреби кінцеві вправи відкидаються, щоб вкластися в T_max."""
    t0 = time.perf_counter()
    EU = filter_exercises(exercises, profile)
    lp = C.LEVELS[profile.level]
    s = max(lp['sets'][0], min(lp['sets'][1], sets))
    name, days_tpl = TEMPLATES[len(profile.days)]
    plan = Plan(profile=profile, method=f'Шаблон ({name})')
    for d, slots in zip(profile.days, days_tpl):
        items = []
        for g, pat in slots:
            cands = [e for e in EU if e.primary == g and (pat is None or e.pattern == pat)] or \
                    [e for e in EU if e.primary == g]
            cands = [e for e in cands if all(it.exercise.id != e.id for it in items)]
            cands.sort(key=lambda e: (not e.compound if pat else e.compound, e.id))
            if cands:
                items.append(make_item(cands[0], s, profile.goal))
        if trim_to_time:
            while items and C.T_WARMUP + sum(C.T_TRANSITION + it.sets * set_time(it.exercise, profile.goal)
                                             for it in items) > profile.tmax:
                items.pop()
        plan.days[d] = order_items(items)
    plan.runtime = time.perf_counter() - t0
    plan.status = 'feasible'
    return plan


# ----------------------------------------------------------------- імітація відпалу
HARD_PENALTY = 1000.0


def _sa_cost(state, profile, byid, W, smin, smax, vmin, vmax, st):
    """Цільова функція (2.21) + штраф за порушення жорстких обмежень (2.6)–(2.13)."""
    days = profile.days
    vol = {g: 0.0 for g in C.GROUPS}
    prim_days = {g: set() for g in C.GROUPS}
    uses = {}
    push = pull = n = 0
    hard = 0.0
    for d in days:
        day = state[d]
        n += len(day)
        hard += max(0, C.N_MIN - len(day)) + max(0, len(day) - C.N_MAX)
        t = C.T_WARMUP
        per = {}
        comp = False
        for eid, s in day.items():
            e = byid[eid]
            t += C.T_TRANSITION + s * st[eid]
            per[e.primary] = per.get(e.primary, 0) + 1
            prim_days[e.primary].add(d)
            uses[eid] = uses.get(eid, 0) + 1
            comp |= e.compound
            for g in C.GROUPS:
                if e.a[g]:
                    vol[g] += e.a[g] * s
            if e.pattern in C.PUSH:
                push += s
            elif e.pattern in C.PULL:
                pull += s
        hard += max(0.0, t - profile.tmax) + (not comp) + sum(max(0, k - C.PER_GROUP_DAY) for k in per.values())
    for g, ds in prim_days.items():
        ds = sorted(ds)
        hard += sum(cyclic_gap(a, b) < C.RECOVERY_DAYS for i, a in enumerate(ds) for b in ds[i + 1:])
    hard += sum(max(0, k - C.MAX_REPEAT_WEEK) for k in uses.values())
    fmin = min(C.F_MIN, len(days))
    soft = W['count'] * n + W['pushpull'] * abs(push - pull) + W['repeat'] * sum(max(0, k - 1) for k in uses.values())
    for g in C.GROUPS:
        wg = C.GROUP_WEIGHT[g]
        soft += wg * (W['under'] * max(0.0, vmin - vol[g]) + W['over'] * max(0.0, vol[g] - vmax)
                      + W['freq'] * max(0, fmin - len(prim_days[g])))
    return soft + HARD_PENALTY * hard, hard


def annealing(profile, exercises, iters=50000, t0=50.0, t1=0.05, seed=0) -> Plan:
    """Метаевристика імітації відпалу (simulated annealing) для тієї самої задачі:
    мінімізується зважена сума штрафів (2.21), а порушення жорстких обмежень (2.6)–(2.13)
    штрафуються великим коефіцієнтом. Початковий розв’язок — жадібний; сусідні розв’язки:
    додавання, вилучення, заміна вправи в занятті, зміна кількості підходів на ±1.
    Температура знижується геометрично від t0 до t1."""
    import math
    import random
    start = time.perf_counter()
    rnd = random.Random(seed)
    EU = filter_exercises(exercises, profile)
    plan = Plan(profile=profile, method='Відпал')
    if not EU:
        plan.status = 'infeasible'
        return plan
    W = C.WEIGHTS
    smin, smax = C.LEVELS[profile.level]['sets']
    vmin, vmax = C.GOALS[profile.goal]['vmin'], C.LEVELS[profile.level]['vmax']
    byid = {e.id: e for e in EU}
    ids = list(byid)
    st = {e.id: set_time(e, profile.goal) for e in EU}
    g0 = greedy(profile, exercises)
    state = {d: {it.exercise.id: it.sets for it in g0.days.get(d, [])} for d in profile.days}
    args = (profile, byid, W, smin, smax, vmin, vmax, st)
    cur, cur_h = _sa_cost(state, *args)
    best, best_cost, best_h = {d: dict(v) for d, v in state.items()}, cur, cur_h
    alpha = (t1 / t0) ** (1 / iters)
    T = t0
    days = list(profile.days)
    for _ in range(iters):
        d = rnd.choice(days)
        day = state[d]
        mv = rnd.random()
        undo = dict(day)
        if mv < 0.25 and len(day) < C.N_MAX:                       # додати вправу
            eid = rnd.choice(ids)
            if eid in day:
                T *= alpha; continue
            day[eid] = rnd.randint(smin, smax)
        elif mv < 0.45 and len(day) > 1:                           # вилучити вправу
            del day[rnd.choice(list(day))]
        elif mv < 0.75 and day:                                    # замінити вправу
            old = rnd.choice(list(day))
            eid = rnd.choice(ids)
            if eid in day:
                T *= alpha; continue
            day[eid] = day.pop(old)
        elif day:                                                  # змінити кількість підходів
            eid = rnd.choice(list(day))
            day[eid] = min(smax, max(smin, day[eid] + rnd.choice((-1, 1))))
        new, new_h = _sa_cost(state, *args)
        if new <= cur or rnd.random() < math.exp((cur - new) / T):
            cur, cur_h = new, new_h
            if cur < best_cost:
                best, best_cost, best_h = {k: dict(v) for k, v in state.items()}, cur, cur_h
        else:
            state[d] = undo
        T *= alpha
    for d in profile.days:
        plan.days[d] = order_items([make_item(byid[eid], s, profile.goal) for eid, s in best[d].items()])
    plan.objective = best_cost
    plan.runtime = time.perf_counter() - start
    plan.status = 'feasible' if best_h == 0 else 'infeasible'
    return plan
