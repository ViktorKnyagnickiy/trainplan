"""Сервісний шар: сценарії використання, що поєднують модель, адаптацію і сховище."""
from __future__ import annotations
from datetime import date

from . import config as C
from .adaptation import SetLog, next_session
from .domain import load_exercises, Profile
from .generator import generate, diagnose
from .metrics import evaluate
from .screening import screen


class PlanService:
    def __init__(self, repo, exercises=None, solver='auto'):
        self.repo = repo
        self.exercises = exercises or load_exercises()
        self.byid = {e.id: e for e in self.exercises}
        self.solver = solver

    def create_plan(self, profile: Profile, general_answers, local_tags, user_id=None):
        s = screen(general_answers, local_tags)
        if not s['allowed']:
            return dict(ok=False, message=s['message'])
        profile.contra = frozenset(s['contra'])
        plan = generate(profile, self.exercises, solver=self.solver)
        if plan.status not in ('optimal', 'feasible'):
            return dict(ok=False, message=' '.join(diagnose(profile, self.exercises)))
        pid = self.repo.save_profile(profile, user_id)
        plan_id = self.repo.save_plan(pid, plan, user_id=user_id)
        return dict(ok=True, plan_id=plan_id, metrics=evaluate(plan))

    def _step(self, item):
        e = self.byid[item['exercise_id']]
        return min([C.EQUIP_STEP[q] for q in e.equipment if q in C.EQUIP_STEP] or [2.5])

    def last_recommendation(self, item_id):
        """Рекомендація за останнім записаним заняттям (без збереження) або None, якщо журнал порожній."""
        item = self.repo.db.execute('SELECT * FROM plan_item WHERE id=?', (item_id,)).fetchone()
        last = self.repo.db.execute('SELECT session_date FROM set_log WHERE plan_item_id=? ORDER BY id DESC LIMIT 1',
                                    (item_id,)).fetchone()
        if not last:
            return None
        rows = self.repo.db.execute('SELECT * FROM set_log WHERE plan_item_id=? AND session_date=? ORDER BY id',
                                    (item_id, last['session_date'])).fetchall()
        sets = [SetLog(r['load'], r['reps'], r['rir']) for r in rows]
        return next_session(sets, (item['reps_min'], item['reps_max']), item['rir'], step=self._step(item))

    def record_session(self, item_id, sets: list[SetLog], session_date=None):
        """Зберігає підходи і обчислює навантаження на наступне заняття (п. 2.5)."""
        item = self.repo.db.execute('SELECT * FROM plan_item WHERE id=?', (item_id,)).fetchone()
        step = self._step(item)
        self.repo.log_sets(item_id, (session_date or date.today()).isoformat(), sets)
        rec = next_session(sets, (item['reps_min'], item['reps_max']), item['rir'], step=step)
        self.repo.update_item_target(item_id, rec['load'], rec['reps_target'])
        return rec
