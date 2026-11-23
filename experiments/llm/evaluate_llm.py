"""Оцінювання планів, сформованих великою мовною моделлю (JSON-відповіді на фіксовані запити)."""
import csv
import json
from pathlib import Path

from trainplan.domain import load_exercises, Plan
from trainplan.generator import make_item, order_items
from experiments.profiles import load
from experiments.run_compare import row

HERE = Path(__file__).parent
RES = HERE.parent / 'results'


def parse(p, data, byid):
    """Перетворює відповідь LLM на план. Невідомі id та дні поза D_U фіксуються як помилки формату."""
    plan = Plan(profile=p, method='LLM', status='feasible')
    errors = dict(unknown_id=0, wrong_day=0)
    for day, lst in data['days'].items():
        d = int(day)
        if d not in p.days:
            errors['wrong_day'] += 1
        items = []
        for x in lst:
            e = byid.get(int(x['id']))
            if e is None:
                errors['unknown_id'] += 1
                continue
            it = make_item(e, int(x['sets']), p.goal)
            items.append(it)
        plan.days[d] = order_items(items)
    return plan, errors


if __name__ == '__main__':
    E = load_exercises()
    byid = {e.id: e for e in E}
    ps = {p.name.split('|')[0]: p for p in load(RES / 'profiles.json')}
    rows = []
    for f in sorted((HERE / 'plans').glob('P*.json')):
        p = ps[f.stem]
        plan, err = parse(p, json.loads(f.read_text('utf-8')), byid)
        r = row(p, plan)
        r.update(err, days_used=len(plan.days))
        rows.append(r)
    with open(RES / 'llm.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(len(rows))
