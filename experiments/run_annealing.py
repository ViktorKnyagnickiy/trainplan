"""Додає до results/compare.csv результати імітації відпалу (без повторного запуску CSP)."""
import csv
import time
from multiprocessing import Pool

from experiments.run_compare import RES, run_sa
from experiments.profiles import load

if __name__ == '__main__':
    ps = load(RES / 'profiles.json')
    t0 = time.time()
    with open(RES / 'compare.csv', encoding='utf-8') as f:
        old = [r for r in csv.DictReader(f) if r['method'] != 'Відпал']
    with Pool(2) as pool:
        new = pool.map(run_sa, ps)
    fields = list(old[0])
    with open(RES / 'compare.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(old + new)
    print('done', len(new), round(time.time() - t0), 's')
