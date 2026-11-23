"""Імпорт відкритого набору free-exercise-db (Unlicense) у схему моделі.
Використання: python tools/import_free_exercise_db.py <шлях до dist/exercises.json> data/exercises_large.csv
М'язи відображаються на 10 груп моделі, руховий патерн визначається евристично,
протипоказання для імпортованих вправ не розмічаються (потрібна експертна розмітка)."""
import csv
import json
import sys

MUSCLE = {'chest': 'ГР', 'lats': 'СП', 'middle back': 'СП', 'traps': 'СП', 'shoulders': 'ПЛ', 'biceps': 'БІ',
          'triceps': 'ТР', 'quadriceps': 'КВ', 'hamstrings': 'ЗС', 'glutes': 'СД', 'abductors': 'СД',
          'calves': 'ЛК', 'abdominals': 'ПР'}
EQUIP = {'barbell': 'штанга', 'e-z curl bar': 'штанга', 'dumbbell': 'гантелі', 'cable': 'блок',
         'machine': 'тренажер', 'body only': 'власна_вага', 'kettlebells': 'гиря', 'bands': 'гума'}
LEVEL = {'beginner': 1, 'intermediate': 2, 'expert': 3}


def pattern(x, g):
    name = x['name'].lower()
    if x.get('mechanic') != 'compound':
        return 'КР' if g == 'ПР' else 'ІЗ'
    if g in ('ГР', 'ТР'):
        return 'ВЖ' if any(k in name for k in ('overhead', 'military', 'shoulder press')) else 'ГЖ'
    if g == 'ПЛ':
        return 'ГТ' if x.get('force') == 'pull' else 'ВЖ'
    if g == 'СП':
        return 'ВТ' if any(k in name for k in ('pulldown', 'pull-up', 'pullup', 'chin')) else 'ГТ'
    if g == 'КВ':
        return 'ВП' if any(k in name for k in ('lunge', 'split', 'step')) else 'ПС'
    if g in ('ЗС', 'СД'):
        return 'ТЗ'
    return 'КР' if g == 'ПР' else 'ІЗ'


def convert(src, dst):
    data = json.load(open(src, encoding='utf-8'))
    rows = []
    for x in data:
        if x.get('category') not in ('strength', 'powerlifting', 'olympic weightlifting'):
            continue
        prim = [MUSCLE[m] for m in x['primaryMuscles'] if m in MUSCLE]
        if not prim or x.get('equipment') not in EQUIP:
            continue
        g = prim[0]
        sec = sorted({MUSCLE[m] for m in x['primaryMuscles'][1:] + x['secondaryMuscles'] if m in MUSCLE} - {g})
        rows.append(dict(id=1000 + len(rows), name=x['name'], pattern=pattern(x, g),
                         mechanic='базова' if x.get('mechanic') == 'compound' else 'ізолююча',
                         equipment=EQUIP[x['equipment']], level=LEVEL.get(x.get('level'), 2),
                         primary=g, secondary=';'.join(sec), contra=''))
    with open(dst, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return len(data), len(rows)


if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]))
