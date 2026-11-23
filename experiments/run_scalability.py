"""Експеримент 3: масштабованість — час розв'язання залежно від кількості вправ і тренувальних днів.
Використовується розширена база, імпортована з free-exercise-db (tools/import_free_exercise_db.py)."""
import csv
import random
import time
from pathlib import Path

from trainplan.baselines import greedy
from trainplan.domain import load_exercises, Profile, DATA
from trainplan.generator import generate
from trainplan.metrics import evaluate

RES = Path(__file__).parent / 'results'
ALL = frozenset('штанга гантелі лава власна_вага турнік бруси тренажер блок гиря гума'.split())
DAYS = {3: (1, 3, 5), 4: (1, 2, 4, 5), 5: (1, 2, 3, 4, 5), 6: (1, 2, 3, 4, 5, 6)}

if __name__ == '__main__':
    big = load_exercises(DATA / 'exercises_large.csv')
    rows = []
    for n in (25, 50, 100, 200, 400):
        for nd in (3, 4, 6):
            for rep in range(3):
                rnd = random.Random(1000 * n + 10 * nd + rep)
                sample = rnd.sample(big, n)
                p = Profile('гіпертрофія', 3, DAYS[nd], 90, ALL)
                plan = generate(p, sample, solver='highs', time_limit=30)
                g = greedy(p, sample)
                r, rg = evaluate(plan), evaluate(g)
                rows.append(dict(n_ex=n, n_days=nd, rep=rep, status=plan.status, runtime=plan.runtime,
                                 gap=plan.gap, objective=plan.objective, n_vars=plan.n_vars, n_cons=plan.n_cons,
                                 K2=r.get('K2'), greedy_runtime=g.runtime, greedy_K2=rg.get('K2')))
                print(rows[-1], flush=True)
    with open(RES / 'scalability.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
