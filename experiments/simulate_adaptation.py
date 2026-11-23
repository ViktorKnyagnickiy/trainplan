"""Експеримент 4: імітаційне моделювання (метод Монте-Карло) правила адаптації навантаження.

Модель «користувача» (припущення автора, параметри обґрунтовано в п. 4.1):
- істинний 1RM зростає за спадною кривою: M(t) = M0·(1 + A·(1 − exp(−t/τ))), A ~ U(0,10; 0,20) за 12 тижнів;
- щоденна варіабельність 1RM — нормальна з коефіцієнтом варіації 4,2 % (Grgic et al., 2020);
- «істинна» кількість повторень до відмови за навантаження L: формула Бжицкі RTF = 37 − 36·L/M
  (правило адаптації використовує формулу Епплі, тож модель і «реальність» навмисно відрізняються);
- користувач виконує цільову кількість повторень або менше (якщо настає відмова);
- самооцінка RIR занижена: q_зв = q_іст − b + ε, b ~ N(0,95; 1,45²) для користувача (Halperin et al., 2022),
  ε ~ N(0; 0,5²) для підходу,
  результат округлюється й обмежується діапазоном [0; 4].
Стратегії: запропоноване правило (β_U = 0, β_U = 1 і з ідеальною самооцінкою), лінійна прогресія (+2,5 кг після успішного заняття,
−10 % після двох невдач поспіль), фіксоване навантаження 75 % від початкового 1RM."""
import csv
import math
import random
from pathlib import Path
from statistics import mean

from trainplan.adaptation import SetLog, next_session

RES = Path(__file__).parent / 'results'
WEEKS, SESS, SETS = 12, 2, 3
REPS, Q_T, STEP = (8, 12), 2, 2.5


def rtf(L, M):
    return max(0.0, 37 - 36 * L / M)


def simulate(strategy, seed):
    rnd = random.Random(seed)
    M0 = rnd.uniform(50, 120)
    A, tau = rnd.uniform(0.10, 0.20), 8.0
    bias = rnd.gauss(0.95, 1.45)
    L = round((M0 / (1 + (REPS[0] + 4) / 30)) / STEP) * STEP     # калібрування: ~8 повт. з RIR 4 (Епплі)
    if strategy == 'fixed':
        L = round(0.75 * M0 / STEP) * STEP
    r_target, fails = REPS[0], 0
    out = dict(true_rir=[], failures=0, sets=0, rel_load=[])
    for w in range(WEEKS):
        for s in range(SESS):
            t = w + s / SESS
            M = M0 * (1 + A * (1 - math.exp(-t / tau)))
            M_day = M * (1 + rnd.gauss(0, 0.042))
            logs = []
            capacity = rtf(L, M_day)
            for k in range(SETS):
                cap = max(0.0, capacity - 1.0 * k)                  # втома між підходами (−1 повт./підхід)
                goal = r_target if strategy != 'fixed' else 10
                reps = int(min(goal if strategy != 'linear' else 10, math.floor(cap)))
                true_q = cap - reps
                if strategy == 'rule_exact':
                    rep_q = max(0, min(4, round(true_q)))           # ідеальна самооцінка (верхня межа)
                else:
                    rep_q = max(0, min(4, round(true_q - bias + rnd.gauss(0, 0.5))))
                logs.append(SetLog(L, reps, rep_q))
                out['true_rir'].append(true_q); out['sets'] += 1
                out['failures'] += reps < (goal if strategy != 'linear' else 10) or true_q < 0.5
            out['rel_load'].append(L / M)
            if strategy.startswith('rule'):
                beta = 1.0 if strategy == 'rule_beta1' else 0.0
                rec = next_session(logs, REPS, Q_T, step=STEP, beta=beta)
                out.setdefault('situations', []).append(rec['situation'])
                L, r_target = rec['load'], rec['reps_target']
            elif strategy == 'linear':
                if all(x.reps >= 10 for x in logs):
                    L += STEP; fails = 0
                else:
                    fails += 1
                    if fails >= 2:
                        L = round(0.9 * L / STEP) * STEP; fails = 0
    M_end = M0 * (1 + A * (1 - math.exp(-(WEEKS - 0.5) / tau)))
    return dict(strategy=strategy, seed=seed, M0=M0, gain=A,
                mean_true_rir=mean(out['true_rir']),
                mae_rir=mean(abs(q - Q_T) for q in out['true_rir']),
                in_zone=mean(1 <= q <= 3 for q in out['true_rir']),
                failure_rate=out['failures'] / out['sets'],
                final_rel_load=out['rel_load'][-1], load_gain=(L - out['rel_load'][0] * M0) / (out['rel_load'][0] * M0),
                true_gain=(M_end - M0) / M0,
                share_hard=mean(x == 'занадто важко' for x in out.get('situations', [''])),
                share_progress=mean(x in ('прогрес', 'занадто легко') for x in out.get('situations', [''])))


if __name__ == '__main__':
    rows = [simulate(st, seed) for st in ('rule', 'rule_beta1', 'rule_exact', 'linear', 'fixed') for seed in range(1000)]
    with open(RES / 'adaptation.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    import pandas as pd
    print(pd.DataFrame(rows).groupby('strategy').mean(numeric_only=True).round(3).to_string())
