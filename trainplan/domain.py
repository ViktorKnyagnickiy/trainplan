"""Доменні сутності: профіль користувача U (2.1), вправа e (2.2), план P."""
from __future__ import annotations
import csv
from dataclasses import dataclass, field
from pathlib import Path
from .config import GROUPS

DATA = Path(__file__).resolve().parent.parent / 'data'


@dataclass(frozen=True)
class Exercise:
    id: int
    name: str
    pattern: str                 # π_e
    compound: bool               # μ_e
    equipment: frozenset         # Q_e
    level: int                   # l_e
    primary: str                 # g_e
    a: dict                      # a_{e,g}
    contra: frozenset            # K_e

    def __hash__(self):
        return hash(self.id)


@dataclass
class Profile:
    goal: str                    # γ
    level: int                   # λ
    days: tuple                  # D_U (номери 1..7)
    tmax: float                  # T_max, хв
    equipment: frozenset         # Q_U
    contra: frozenset = frozenset()   # K_U
    excluded: frozenset = frozenset()  # B_U (id вправ)
    name: str = ''

    def to_dict(self):
        return dict(goal=self.goal, level=self.level, days=list(self.days), tmax=self.tmax,
                    equipment=sorted(self.equipment), contra=sorted(self.contra),
                    excluded=sorted(self.excluded), name=self.name)

    @staticmethod
    def from_dict(d):
        return Profile(goal=d['goal'], level=int(d['level']), days=tuple(sorted(int(x) for x in d['days'])),
                       tmax=float(d['tmax']), equipment=frozenset(d['equipment']),
                       contra=frozenset(d.get('contra', ())), excluded=frozenset(d.get('excluded', ())),
                       name=d.get('name', ''))


@dataclass
class PlanItem:
    exercise: Exercise
    sets: int
    reps: tuple = (0, 0)
    rir: int = 2
    rest: int = 90               # с
    load: float | None = None    # кг; None — калібрувальний тиждень


@dataclass
class Plan:
    profile: Profile
    days: dict = field(default_factory=dict)        # день -> [PlanItem]
    method: str = ''
    status: str = ''
    objective: float | None = None
    gap: float | None = None
    runtime: float = 0.0
    n_vars: int = 0
    n_cons: int = 0

    def items(self):
        for d, lst in self.days.items():
            for it in lst:
                yield d, it


def load_exercises(path: Path | str = DATA / 'exercises.csv') -> list[Exercise]:
    out = []
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            a = {g: 0.0 for g in GROUPS}
            a[r['primary']] = 1.0
            for g in filter(None, r['secondary'].split(';')):
                a[g] = max(a[g], 0.5)
            out.append(Exercise(
                id=int(r['id']), name=r['name'], pattern=r['pattern'], compound=r['mechanic'] == 'базова',
                equipment=frozenset(filter(None, r['equipment'].split(';'))), level=int(r['level']),
                primary=r['primary'], a=a, contra=frozenset(filter(None, r['contra'].split(';')))))
    return out


def filter_exercises(exercises, profile: Profile):
    """Множина допустимих вправ E_U, формула (2.3)."""
    return [e for e in exercises
            if e.equipment <= profile.equipment and not (e.contra & profile.contra)
            and e.level <= profile.level and e.id not in profile.excluded]
