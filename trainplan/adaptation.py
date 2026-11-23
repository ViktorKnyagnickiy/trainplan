"""Модель адаптації навантаження за RPE/RIR (п. 2.5): формули (2.23)–(2.27)."""
from __future__ import annotations
from dataclasses import dataclass

from . import config as C


@dataclass
class SetLog:
    load: float     # L, кг
    reps: int       # r
    rir: int        # q (0..4)


def corrected_rir(q: float, beta: float = 0.0) -> float:
    """(2.23): q_к = q + β_U, оцінка обмежується діапазоном [0; 4]."""
    return max(0.0, min(4.0, q)) + beta


def e1rm(load: float, reps: int, rir: float) -> float:
    """(2.24): e1RM = L·(1 + (r + q_к)/30)."""
    return load * (1 + (reps + rir) / 30)


def target_load(load, reps, rir, r_target, q_target) -> float:
    """(2.25): L* = L·(30 + r + q_к)/(30 + r* + q*)."""
    return load * (30 + reps + rir) / (30 + r_target + q_target)


def round_to_step(x: float, step: float) -> float:
    return round(x / step) * step


def classify(sets: list[SetLog], reps_range, q_target, beta=0.0) -> tuple[str, int, float]:
    """Ситуація з табл. 2.3; повертає (ситуація, r_ф, q_сер)."""
    r_min, r_max = reps_range
    r_f = min(s.reps for s in sets)
    q_mean = sum(corrected_rir(s.rir, beta) for s in sets) / len(sets)
    if r_f < r_min or q_mean < q_target - 1:
        return 'занадто важко', r_f, q_mean
    if q_mean > q_target + 1:
        return 'занадто легко', r_f, q_mean
    if r_f >= r_max and q_mean >= q_target:
        return 'прогрес', r_f, q_mean
    return 'у межах діапазону', r_f, q_mean


def next_session(sets: list[SetLog], reps_range, q_target, step=2.5, beta=0.0,
                 delta=C.ADAPT_DELTA, min_change=C.ADAPT_MIN_CHANGE) -> dict:
    """Навантаження і цільова кількість повторень на наступне заняття
    (табл. 2.3, формули (2.25)–(2.26))."""
    r_min, r_max = reps_range
    situation, r_f, q_mean = classify(sets, reps_range, q_target, beta)
    L = sets[0].load
    if situation == 'у межах діапазону':
        return dict(situation=situation, load=L, reps_target=min(r_max, r_f + 1))
    # «занадто легко»: та сама кількість повторень, більше навантаження;
    # інакше — нижня межа діапазону
    r_target = min(r_max, r_f) if situation == 'занадто легко' else r_min
    # оцінка за найважчим (останнім) підходом — найменший запас повторень
    last = min(sets, key=lambda s: s.reps + corrected_rir(s.rir, beta))
    L_star = target_load(last.load, last.reps, corrected_rir(last.rir, beta),
                         r_target, q_target)
    L_new = min(max(L_star, (1 - delta) * L), (1 + delta) * L)
    if abs(L_new - L) / L < min_change:
        L_new = L
    L_new = max(step, round_to_step(L_new, step))
    return dict(situation=situation, load=L_new, reps_target=r_target, l_star=L_star)


def adapt_volume(v_current: dict, share_hard: dict, stagnation: dict, vmin: int, vmax: int) -> dict:
    """(2.27): корекція цільового обсягу груп на наступний мезоцикл."""
    out = {}
    for g, v in v_current.items():
        if share_hard.get(g, 0) >= 0.5:
            out[g] = max(vmin, v - 2)
        elif stagnation.get(g) and share_hard.get(g, 0) < 0.25:
            out[g] = min(vmax, v + 2)
        else:
            out[g] = v
    return out


def needs_deload(week: int, share_hard_groups: float, meso_len: int = 5) -> bool:
    """Розвантаження після мезоциклу або достроково, якщо «занадто важко» для ≥ половини груп."""
    return week % (meso_len + 1) == 0 or share_hard_groups >= 0.5
