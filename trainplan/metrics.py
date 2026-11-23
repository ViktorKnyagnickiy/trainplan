"""Незалежна перевірка плану та критерії якості K1–K5 (п. 2.3). Не використовує код моделі,
тому застосовується однаково до планів, отриманих будь-яким методом."""
from __future__ import annotations
import math

from . import config as C


def _set_time(e, goal):
    gp = C.GOALS[goal]
    return (sum(gp['reps']) / 2 * C.TEMPO + (gp['rest_c'] if e.compound else gp['rest_i'])) / 60


def _gap(d1, d2):
    a = (d2 - d1) % 7
    return min(a, 7 - a)


def violations(plan) -> dict:
    """Порушення жорстких обмежень за типами (критерій K1)."""
    p = plan.profile
    v = dict(equipment=0, contra=0, level=0, duration=0, recovery=0)
    prim = {}
    for d, items in plan.days.items():
        for it in items:
            e = it.exercise
            v['equipment'] += not (e.equipment <= p.equipment)
            v['contra'] += bool(e.contra & p.contra)
            v['level'] += e.level > p.level
            prim.setdefault(e.primary, set()).add(d)
        dur = C.T_WARMUP + sum(C.T_TRANSITION + it.sets * _set_time(it.exercise, p.goal) for it in items)
        v['duration'] += dur > p.tmax + 1e-6
    for g, ds in prim.items():
        ds = sorted(ds)
        for i in range(len(ds)):
            for j in range(i + 1, len(ds)):
                v['recovery'] += _gap(ds[i], ds[j]) < C.RECOVERY_DAYS
    return v


def volume(plan) -> dict:
    vol = {g: 0.0 for g in C.GROUPS}
    for _, it in plan.items():
        for g in C.GROUPS:
            vol[g] += it.exercise.a[g] * it.sets
    return vol


def evaluate(plan) -> dict:
    p = plan.profile
    gp, lp = C.GOALS[p.goal], C.LEVELS[p.level]
    vmin, vmax = gp['vmin'], lp['vmax']
    if not plan.days or not any(plan.days.values()):
        return dict(feasible=False)
    viol = violations(plan)
    vol = volume(plan)
    dev = [max(0, vmin - vol[g]) / vmin + max(0, vol[g] - vmax) / vmax for g in C.GROUPS]
    freq = {g: sum(1 for items in plan.days.values() if any(it.exercise.primary == g for it in items))
            for g in C.GROUPS}
    push = sum(it.sets for _, it in plan.items() if it.exercise.pattern in C.PUSH)
    pull = sum(it.sets for _, it in plan.items() if it.exercise.pattern in C.PULL)
    slots = [it.exercise.id for _, it in plan.items()]
    durs = [C.T_WARMUP + sum(C.T_TRANSITION + it.sets * _set_time(it.exercise, p.goal) for it in items)
            for items in plan.days.values()]
    return dict(
        feasible=True,
        K1=sum(viol.values()), **{f'viol_{k}': n for k, n in viol.items()},
        K2=sum(dev) / len(dev),
        K2_groups_in_range=sum(vmin <= vol[g] <= vmax for g in C.GROUPS) / len(C.GROUPS),
        K3=sum(freq[g] >= min(C.F_MIN, len(p.days)) for g in C.GROUPS) / len(C.GROUPS),
        K4=(push / pull) if pull else (math.inf if push else 1.0),
        K4_log=abs(math.log(push / pull)) if push and pull else (0.0 if not push and not pull else 3.0),
        K5=len(set(slots)) / len(slots),
        n_exercises=len(slots), total_sets=sum(it.sets for _, it in plan.items()),
        max_duration=max(durs), runtime=plan.runtime,
    )
