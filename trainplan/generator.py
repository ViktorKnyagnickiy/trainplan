"""Формування тижневого плану: побудова задачі оптимізації з обмеженнями (2.5)–(2.22),
розв'язання, упорядкування вправ і призначення параметрів навантаження."""
from __future__ import annotations
import itertools

from . import config as C
from .domain import Plan, PlanItem, Profile, filter_exercises
from .linmodel import LinearModel, solve, INF


def cyclic_gap(d1: int, d2: int) -> int:
    """Найменший інтервал між днями тижня у циклічному тижні, діб: Δ(d, d')."""
    a = (d2 - d1) % 7
    return min(a, 7 - a)


def set_time(e, goal: str) -> float:
    """τ_e — тривалість підходу з відпочинком, хв, формула (2.8)."""
    gp = C.GOALS[goal]
    r_mean = sum(gp['reps']) / 2
    rest = gp['rest_c'] if e.compound else gp['rest_i']
    return (r_mean * C.TEMPO + rest) / 60


def build_model(profile: Profile, EU: list, weights=None, vtarget=None) -> LinearModel:
    """Будує лінійну цілочисельну модель.
    vtarget — {група: V_max} для адаптації на рівні мезоциклу (2.27)."""
    W = dict(C.WEIGHTS, **(weights or {}))
    gp, lp = C.GOALS[profile.goal], C.LEVELS[profile.level]
    smin, smax = lp['sets']
    days = list(profile.days)
    G = C.GROUPS
    m = LinearModel()
    for e, d in itertools.product(EU, days):
        m.var(('x', e.id, d), 0, 1, W['count'])                     # x_{e,d}, штраф P6
        m.var(('s', e.id, d), 0, smax)                              # s_{e,d}
    for g, d in itertools.product(G, days):
        m.var(('y', g, d), 0, 1)                                    # y_{g,d}
    for g in G:
        wg = C.GROUP_WEIGHT[g]
        m.var(('u', g), 0, INF, W['under'] * wg / 2)        # дефіцит обсягу, пів-підходи
        m.var(('o', g), 0, INF, W['over'] * wg / 2)                 # надлишок обсягу
        m.var(('f', g), 0, INF, W['freq'] * wg)                     # дефіцит частоти
    m.var(('pp+',), 0, INF, W['pushpull'])
    m.var(('pp-',), 0, INF, W['pushpull'])
    for e in EU:
        m.var(('r', e.id), 0, INF, W['repeat'])                     # повтори вправи, P5

    for e, d in itertools.product(EU, days):                        # (2.5)
        m.add([(('s', e.id, d), 1), (('x', e.id, d), -smax)], hi=0)
        m.add([(('s', e.id, d), 1), (('x', e.id, d), -smin)], lo=0)
    for d in days:
        m.add([(('x', e.id, d), 1) for e in EU], C.N_MIN, C.N_MAX)  # (2.6)
        m.add([(('x', e.id, d), C.T_TRANSITION) for e in EU] +
              [(('s', e.id, d), set_time(e, profile.goal)) for e in EU],
              hi=profile.tmax - C.T_WARMUP)                          # (2.7)
        m.add([(('x', e.id, d), 1) for e in EU if e.compound], lo=1)  # (2.9)
        for g in G:
            P = [e for e in EU if e.primary == g]
            m.add([(('x', e.id, d), 1) for e in P], hi=C.PER_GROUP_DAY)  # (2.10)
            for e in P:                                             # (2.11)
                m.add([(('y', g, d), 1), (('x', e.id, d), -1)], lo=0)
            m.add([(('y', g, d), 1)] + [(('x', e.id, d), -1) for e in P], hi=0)
    for d1, d2 in itertools.combinations(days, 2):                  # (2.12)
        if cyclic_gap(d1, d2) < C.RECOVERY_DAYS:
            for g in G:
                m.add([(('y', g, d1), 1), (('y', g, d2), 1)], hi=1)
    for e in EU:
        m.add([(('x', e.id, d), 1) for d in days], hi=C.MAX_REPEAT_WEEK)          # (2.13)
        m.add([(('r', e.id), 1)] + [(('x', e.id, d), -1) for d in days], lo=-1)   # P5
    vmin2 = 2 * gp['vmin']
    for g in G:                                                     # (2.14)–(2.17), (2.22)
        vmax2 = 2 * (vtarget or {}).get(g, lp['vmax'])
        vol = [(('s', e.id, d), 2 * e.a[g]) for e in EU for d in days if e.a[g]]
        m.add(vol + [(('u', g), 1)], lo=vmin2)
        m.add(vol + [(('o', g), -1)], hi=vmax2)
        m.add([(('f', g), 1)] + [(('y', g, d), 1) for d in days],
              lo=min(C.F_MIN, len(days)))
    push = [(('s', e.id, d), 1) for e in EU for d in days if e.pattern in C.PUSH]
    pull = [(('s', e.id, d), -1) for e in EU for d in days if e.pattern in C.PULL]
    m.add(push + pull + [(('pp+',), -1), (('pp-',), 1)], 0, 0)     # (2.18)
    return m


def order_items(items):
    """Упорядкування: базові → ізолюючі, великі групи → малі."""
    rank = {g: k for k, g in enumerate(C.GROUP_ORDER)}
    return sorted(items, key=lambda it: (not it.exercise.compound,
                                         rank[it.exercise.primary], it.exercise.id))


def make_item(e, sets, goal):
    gp = C.GOALS[goal]
    return PlanItem(exercise=e, sets=sets, reps=gp['reps'], rir=gp['rir'],
                    rest=gp['rest_c'] if e.compound else gp['rest_i'])


def generate(profile: Profile, exercises, solver='auto', weights=None, vtarget=None,
             time_limit=C.SOLVER_TIME_LIMIT, rel_gap=C.SOLVER_REL_GAP) -> Plan:
    EU = filter_exercises(exercises, profile)
    plan = Plan(profile=profile, method='CSP')
    if not EU:
        plan.status = 'infeasible'
        return plan
    m = build_model(profile, EU, weights, vtarget)
    sol = solve(m, solver=solver, time_limit=time_limit, rel_gap=rel_gap)
    plan.status, plan.objective, plan.gap, plan.runtime = sol.status, sol.objective, sol.gap, sol.runtime
    plan.n_vars, plan.n_cons, plan.method = m.n_vars, m.n_cons, f'CSP/{sol.solver}'
    if sol.status not in ('optimal', 'feasible'):
        return plan
    byid = {e.id: e for e in EU}
    for d in profile.days:
        items = [make_item(byid[eid], sol.values[('s', eid, d)], profile.goal)
                 for eid in byid if sol.values[('x', eid, d)] == 1]
        plan.days[d] = order_items(items)
    return plan


def diagnose(profile: Profile, exercises) -> list[str]:
    """Пояснення причин недопустимості (крок 4 алгоритму)."""
    EU = filter_exercises(exercises, profile)
    msgs = []
    if len(EU) < C.N_MIN:
        msgs.append(f'Доступно лише {len(EU)} вправ: розширте перелік обладнання або зменште протипоказання.')
    if not any(e.compound for e in EU):
        msgs.append('Немає жодної базової вправи для наявного обладнання.')
    smin = C.LEVELS[profile.level]['sets'][0]
    cheapest = sorted(C.T_TRANSITION + smin * set_time(e, profile.goal) for e in EU)[:C.N_MIN]
    if len(cheapest) == C.N_MIN and C.T_WARMUP + sum(cheapest) > profile.tmax:
        msgs.append(f'Заняття не вміщується в {profile.tmax:.0f} хв: збільште тривалість заняття.')
    return msgs or ['Обмеження несумісні: спробуйте змінити тренувальні дні (уникайте трьох днів поспіль).']
