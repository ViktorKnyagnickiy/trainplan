"""Формує фіксовані запити до великої мовної моделі для підвибірки профілів (базовий метод «LLM»)."""
from pathlib import Path

from trainplan import config as C
from trainplan.domain import load_exercises
from experiments.profiles import load

HERE = Path(__file__).parent
LEVEL = {1: 'початковий', 2: 'середній', 3: 'високий'}
CONTRA_TXT = {'плече': 'біль у плечовому суглобі', 'поперек': 'біль у попереку', 'коліно': 'біль у колінному суглобі'}

TEMPLATE = """Ти — досвідчений персональний тренер. Склади тижневий план силових тренувань для користувача.

Параметри користувача:
- ціль: {goal};
- рівень підготовленості: {level};
- тренувальні дні: {days};
- максимальна тривалість одного заняття: {tmax} хв (разом із розминкою 10 хв, переходами між вправами близько 1 хв і відпочинком між підходами);
- доступне обладнання: {equip};
- обмеження за станом здоров'я: {contra}.

Для цілі «{goal}» у підходах виконується {r0}–{r1} повторень (приблизно 4 с на повторення), відпочинок між підходами — {rc} с для базових і {ri} с для ізолюючих вправ.

Використовуй ЛИШЕ вправи з каталогу нижче. Формат рядка: id | назва | обладнання | складність (1–3) | основна група м'язів | допоміжні групи.
{catalog}

Дотримуйся сучасних рекомендацій ACSM щодо обсягу, частоти тренувань і відновлення м'язових груп.
Відповідь надай ЛИШЕ у форматі JSON без пояснень:
{{"days": {{"<номер дня 1–7>": [{{"id": <id вправи>, "name": "<назва>", "sets": <кількість робочих підходів>}}]}}}}
"""


def catalog():
    E = load_exercises()
    return '\n'.join(f'{e.id} | {e.name} | {", ".join(sorted(e.equipment))} | {e.level} | '
                     f'{C.GROUP_NAMES[e.primary]} | {", ".join(C.GROUP_NAMES[g] for g in C.GROUPS if e.a[g] == 0.5) or "—"}'
                     for e in E)


def prompt_for(p):
    gp = C.GOALS[p.goal]
    days = ', '.join(f'{C.DAY_NAMES[d]} ({d})' for d in p.days)
    return TEMPLATE.format(goal=p.goal, level=LEVEL[p.level], days=days, tmax=int(p.tmax),
                           equip=', '.join(sorted(p.equipment)), contra=', '.join(CONTRA_TXT[c] for c in sorted(p.contra)) or 'немає',
                           r0=gp['reps'][0], r1=gp['reps'][1], rc=gp['rest_c'], ri=gp['rest_i'], catalog=catalog())


def select_subset(ps):
    """18 профілів: для кожної пари ціль × обладнання — два різні рівні (перший профіль комірки)."""
    out = []
    for g in range(3):
        for e in range(3):
            for lv in ((g + e) % 3, (g + e + 1) % 3):
                out.append(ps[g * 72 + lv * 24 + e * 8])
    return out


if __name__ == '__main__':
    ps = load(HERE.parent / 'results' / 'profiles.json')
    subset = select_subset(ps)
    (HERE / 'prompts').mkdir(exist_ok=True)
    for p in subset:
        pid = p.name.split('|')[0]
        (HERE / 'prompts' / f'{pid}.txt').write_text(prompt_for(p), 'utf-8')
    print(len(subset), [p.name for p in subset])
