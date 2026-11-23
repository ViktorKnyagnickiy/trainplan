"""Генерування стратифікованої вибірки синтетичних профілів користувачів."""
import itertools
import json
import random
from pathlib import Path

from trainplan.domain import Profile

EQUIP = {
    'зал': frozenset('штанга гантелі лава власна_вага турнік бруси тренажер блок гиря гума'.split()),
    'дім': frozenset('гантелі лава власна_вага турнік гума'.split()),
    'мінімум': frozenset('власна_вага турнік гума'.split()),
}
DAYS = {
    2: [(1, 4), (2, 5)],
    3: [(1, 3, 5), (2, 4, 6), (1, 2, 4)],
    4: [(1, 2, 4, 5), (1, 3, 5, 6), (1, 2, 3, 5)],
    5: [(1, 2, 3, 4, 5), (1, 2, 4, 5, 6)],
    6: [(1, 2, 3, 4, 5, 6)],
}
CONTRA = [frozenset()] * 5 + [frozenset({'плече'}), frozenset({'поперек'}), frozenset({'коліно'}),
                              frozenset({'плече', 'поперек'})]
GOALS = ['гіпертрофія', 'сила', 'витривалість']


def make_profiles(n_per_cell=8, seed=2026):
    """Страти: ціль (3) × рівень (3) × обладнання (3) = 27 комірок; у кожній n_per_cell профілів
    з випадковими днями (2–6), тривалістю (45/60/75/90 хв) і протипоказаннями."""
    rnd = random.Random(seed)
    out = []
    for goal, level, eq in itertools.product(GOALS, (1, 2, 3), EQUIP):
        for k in range(n_per_cell):
            nd = rnd.choice([2, 3, 3, 4, 4, 5, 6])
            out.append(Profile(goal=goal, level=level, days=rnd.choice(DAYS[nd]),
                               tmax=rnd.choice([45, 60, 75, 90]), equipment=EQUIP[eq],
                               contra=rnd.choice(CONTRA), name=f'{eq}'))
    for i, p in enumerate(out):
        p.name = f'P{i + 1:03d}|{p.name}'
    return out


def save(profiles, path):
    Path(path).write_text(json.dumps([p.to_dict() for p in profiles], ensure_ascii=False, indent=1), 'utf-8')


def load(path):
    return [Profile.from_dict(d) for d in json.loads(Path(path).read_text('utf-8'))]


if __name__ == '__main__':
    ps = make_profiles()
    save(ps, Path(__file__).parent / 'results' / 'profiles.json')
    print(len(ps))
