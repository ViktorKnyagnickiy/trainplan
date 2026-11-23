"""Створює або відновлює демо-акаунт «demo» з готовим планом та історією тренувань.

Запуск із теки проєкту:
    python -m tools.create_demo            # вхід лише через кнопку «Демо-режим»
    python -m tools.create_demo ПАРОЛЬ     # додатково можна увійти як demo / ПАРОЛЬ
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trainplan.demo import ensure_demo          # noqa: E402
from trainplan.domain import DATA               # noqa: E402
from trainplan.repository import Repository     # noqa: E402
from trainplan.service import PlanService       # noqa: E402

if __name__ == '__main__':
    repo = Repository(os.environ.get('TRAINPLAN_DB', ROOT / 'trainplan.db'))
    repo.import_exercises_csv(DATA / 'exercises.csv')
    ensure_demo(repo, PlanService(repo), sys.argv[1] if len(sys.argv) > 1 else None)
    print('Демо-акаунт «demo» готовий: план та історія тренувань створені.')
