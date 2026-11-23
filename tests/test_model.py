"""Модульні та інтеграційні тести моделі (pytest)."""
import itertools
import pytest

from trainplan import config as C
from trainplan.adaptation import SetLog, next_session, e1rm, target_load
from trainplan.baselines import annealing, greedy, template
from trainplan.domain import load_exercises, Profile, filter_exercises
from trainplan.generator import generate, cyclic_gap, build_model
from trainplan.linmodel import LinearModel, solve_highs, _int_row
from trainplan.metrics import evaluate, violations
from trainplan.screening import screen

E = load_exercises()
GYM = frozenset('штанга гантелі лава власна_вага турнік бруси тренажер блок'.split())
HOME = frozenset('гантелі лава власна_вага турнік'.split())


def P(**kw):
    d = dict(goal='гіпертрофія', level=2, days=(1, 3, 5), tmax=60, equipment=GYM)
    d.update(kw)
    return Profile(**d)


# ------------------------------------------------------------- дані та фільтрація
def test_exercise_base_consistent():
    assert len({e.id for e in E}) == len(E) >= 70
    for e in E:
        assert e.a[e.primary] == 1.0 and e.pattern in C.PATTERN_NAMES and 1 <= e.level <= 3


def test_filter_respects_equipment_contra_level():
    p = P(equipment=HOME, contra=frozenset({'поперек', 'коліно'}), level=1)
    for e in filter_exercises(E, p):
        assert e.equipment <= p.equipment and not (e.contra & p.contra) and e.level <= 1


def test_cyclic_gap():
    assert cyclic_gap(1, 2) == 1 and cyclic_gap(7, 1) == 1 and cyclic_gap(1, 4) == 3 and cyclic_gap(1, 5) == 3


# ------------------------------------------------------------- розв'язувач
def test_int_row_scaling():
    ic, lo, hi, den = _int_row({0: 2.5, 1: 1 / 3}, -float('inf'), 10)
    assert den == 6 and ic == {0: 15, 1: 2} and hi == 60


def test_highs_small_model():
    m = LinearModel()
    m.var('a', 0, 10, -1); m.var('b', 0, 10, -1)
    m.add([('a', 1), ('b', 2)], hi=8)
    sol = solve_highs(m)
    assert sol.status == 'optimal' and sol.objective == -8


# ------------------------------------------------------------- властивості плану
PROFILES = [P(), P(days=(1, 2, 4, 5)), P(days=(1, 2, 3, 4, 5, 6), tmax=75), P(equipment=HOME, contra=frozenset({'поперек'})),
            P(goal='сила', level=1, days=(2, 4, 6), tmax=45, contra=frozenset({'плече'})), P(goal='витривалість', level=3)]


@pytest.mark.parametrize('profile', PROFILES)
def test_plan_has_no_hard_violations(profile):
    plan = generate(profile, E, solver='highs', time_limit=20)
    assert plan.status in ('optimal', 'feasible')
    assert sum(violations(plan).values()) == 0
    for d, items in plan.days.items():
        assert C.N_MIN <= len(items) <= C.N_MAX
        assert any(it.exercise.compound for it in items)
        smin, smax = C.LEVELS[profile.level]['sets']
        assert all(smin <= it.sets <= smax for it in items)


def test_full_gym_four_days_meets_all_soft_constraints():
    plan = generate(P(days=(1, 2, 4, 5)), E, solver='highs')
    r = evaluate(plan)
    assert r['K2'] == 0 and r['K3'] == 1 and r['K4'] == 1 and r['K5'] == 1


def test_recovery_splits_groups_on_consecutive_days():
    plan = generate(P(days=(1, 2, 4, 5)), E, solver='highs')
    for d1, d2 in [(1, 2), (4, 5)]:
        g1 = {it.exercise.primary for it in plan.days[d1]}
        g2 = {it.exercise.primary for it in plan.days[d2]}
        assert not (g1 & g2)


def test_infeasible_when_too_short():
    plan = generate(P(tmax=15), E, solver='highs')
    assert plan.status == 'infeasible'


@pytest.mark.parametrize('method', [greedy, template])
def test_baselines_respect_safety(method):
    p = P(equipment=HOME, contra=frozenset({'поперек', 'плече'}))
    v = violations(method(p, E))
    assert v['equipment'] == v['contra'] == v['level'] == 0


# ------------------------------------------------------------- адаптація
def test_load_formula_cancels_e1rm():
    L = target_load(60, 12, 2, 8, 2)
    assert L == pytest.approx(66.0)
    assert e1rm(60, 12, 2) == pytest.approx(e1rm(L, 8, 2))


@pytest.mark.parametrize('sets,expected,load', [
    ([SetLog(60, 12, 2)] * 3, 'прогрес', 65.0),
    ([SetLog(60, 10, 2), SetLog(60, 10, 2), SetLog(60, 9, 2)], 'у межах діапазону', 60.0),
    ([SetLog(60, 10, 4)] * 3, 'занадто легко', 62.5),
    ([SetLog(60, 8, 0), SetLog(60, 7, 0), SetLog(60, 6, 0)], 'занадто важко', 55.0),
])
def test_table_2_3_examples(sets, expected, load):
    rec = next_session(sets, (8, 12), 2, step=2.5)
    assert rec['situation'] == expected and rec['load'] == load


def test_load_change_is_bounded():
    rec = next_session([SetLog(100, 30, 4)] * 3, (8, 12), 2, step=2.5)
    assert rec['load'] <= 110


# ------------------------------------------------------------- скринінг
def test_screening():
    assert not screen([True] + [False] * 6, [])['allowed']
    s = screen([False] * 7, ['плече', 'невідоме'])
    assert s['allowed'] and s['contra'] == {'плече'}


def test_annealing_feasible_and_not_better_than_model():
    p = P(days=(1, 3, 5), tmax=60)
    sa = annealing(p, E, iters=8000, seed=0)
    csp = generate(p, E, solver='highs')
    assert sa.status == 'feasible' and evaluate(sa)['K1'] == 0
    # з урахуванням допустимого відносного розриву розв'язувача 1 %
    assert sa.objective >= csp.objective * (1 - C.SOLVER_REL_GAP) - 1e-6
