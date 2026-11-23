"""Експеримент 1: порівняння запропонованої моделі з базовими методами на синтетичних профілях."""
import csv
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from trainplan.baselines import annealing, greedy, template
from trainplan.domain import load_exercises
from trainplan.generator import generate
from trainplan.metrics import evaluate
from experiments.profiles import load

RES = Path(__file__).parent / 'results'
E = load_exercises()
KEYS = ['K1', 'viol_equipment', 'viol_contra', 'viol_level', 'viol_duration', 'viol_recovery', 'K2',
        'K2_groups_in_range', 'K3', 'K4', 'K4_log', 'K5', 'n_exercises', 'total_sets', 'max_duration', 'runtime']


def row(p, plan):
    r = evaluate(plan)
    base = dict(profile=p.name.split('|')[0], equip=p.name.split('|')[1], goal=p.goal, level=p.level,
                n_days=len(p.days), tmax=p.tmax, contra='+'.join(sorted(p.contra)) or '—',
                method=plan.method.split('/')[0].split(' (')[0], status=plan.status,
                objective=plan.objective, gap=plan.gap, n_vars=plan.n_vars, n_cons=plan.n_cons)
    base.update({k: r.get(k) for k in KEYS})
    if not r.get('feasible'):
        base['runtime'] = plan.runtime
    return base


def run_csp(p):
    return row(p, generate(p, E, solver='highs'))


def run_sa(p):
    return row(p, annealing(p, E, seed=0))


if __name__ == '__main__':
    ps = load(RES / 'profiles.json')
    t0 = time.time()
    rows = []
    with Pool(2) as pool:
        for i, r in enumerate(pool.imap(run_csp, ps)):
            rows.append(r)
            if i % 20 == 0:
                print(i, r['status'], round(r['runtime'] or 0, 2), round(time.time() - t0), flush=True)
    with Pool(2) as pool:
        rows.extend(pool.map(run_sa, ps))
    for p in ps:
        rows.append(row(p, greedy(p, E)))
        rows.append(row(p, template(p, E)))
    with open(RES / 'compare.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print('done', len(rows), round(time.time() - t0), 's')
