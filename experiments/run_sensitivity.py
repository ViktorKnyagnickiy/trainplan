"""Експеримент 2: локальна перевірка стійкості до ваг цільової функції (по одній вазі ×0,5 і ×2)."""
import csv
import time
from multiprocessing import Pool
from pathlib import Path

from trainplan import config as C
from trainplan.domain import load_exercises
from trainplan.generator import generate
from trainplan.metrics import evaluate
from experiments.profiles import load

RES = Path(__file__).parent / 'results'
E = load_exercises()


def configs():
    yield 'базова', {}
    for k in C.WEIGHTS:
        for f in (0.5, 2.0):
            yield f'{k}×{f:g}', {k: C.WEIGHTS[k] * f}


def job(args):
    name, w, p = args
    plan = generate(p, E, solver='highs', weights=w)
    r = evaluate(plan)
    return dict(config=name, profile=p.name.split('|')[0], status=plan.status,
                **{k: r.get(k) for k in ('K1', 'K2', 'K3', 'K4', 'K4_log', 'K5', 'n_exercises', 'total_sets')},
                runtime=plan.runtime)


if __name__ == '__main__':
    ps = load(RES / 'profiles.json')[::8]           # перший профіль кожної з 27 страт
    jobs = [(n, w, p) for n, w in configs() for p in ps]
    t0 = time.time()
    with Pool(2) as pool:
        rows = pool.map(job, jobs)
    with open(RES / 'sensitivity.csv', 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader(); wr.writerows(rows)
    print('done', len(rows), round(time.time() - t0))
