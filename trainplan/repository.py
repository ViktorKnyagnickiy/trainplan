"""Шар доступу до даних (SQLite)."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exercise (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, pattern TEXT NOT NULL, mechanic TEXT NOT NULL,
    equipment TEXT NOT NULL, level INTEGER NOT NULL, primary_group TEXT NOT NULL,
    secondary_groups TEXT NOT NULL DEFAULT '', contra TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL REFERENCES profile(id),
    method TEXT, status TEXT, objective REAL, runtime REAL, mesocycle INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plan_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
    day INTEGER NOT NULL, position INTEGER NOT NULL, exercise_id INTEGER NOT NULL REFERENCES exercise(id),
    sets INTEGER NOT NULL, reps_min INTEGER NOT NULL, reps_max INTEGER NOT NULL, rir INTEGER NOT NULL,
    rest INTEGER NOT NULL, load REAL, reps_target INTEGER);
CREATE TABLE IF NOT EXISTS set_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, plan_item_id INTEGER NOT NULL REFERENCES plan_item(id) ON DELETE CASCADE,
    session_date TEXT NOT NULL, set_no INTEGER NOT NULL, load REAL NOT NULL, reps INTEGER NOT NULL,
    rir INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_item_plan ON plan_item(plan_id);
CREATE INDEX IF NOT EXISTS ix_log_item ON set_log(plan_item_id);
"""


class Repository:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Додає колонку user_id до таблиць, створених попередньою версією системи."""
        for table in ('profile', 'plan'):
            cols = [r['name'] for r in self.db.execute(f'PRAGMA table_info({table})')]
            if 'user_id' not in cols:
                self.db.execute(f'ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES user(id)')
        self.db.execute('CREATE INDEX IF NOT EXISTS ix_plan_user ON plan(user_id)')
        self.db.commit()

    # ------------------------------------------------------------ користувачі
    def create_user(self, login, password_hash) -> int:
        cur = self.db.execute('INSERT INTO user(login, password_hash, created_at) VALUES (?,?,?)',
                              (login, password_hash, datetime.now().isoformat(timespec='seconds')))
        self.db.commit()
        return cur.lastrowid

    def user_by_login(self, login):
        return self.db.execute('SELECT * FROM user WHERE login=?', (login,)).fetchone()

    def user_by_id(self, uid):
        return self.db.execute('SELECT * FROM user WHERE id=?', (uid,)).fetchone()

    # ------------------------------------------------------------ вправи
    def import_exercises_csv(self, path):
        import csv
        with open(path, encoding='utf-8') as f:
            rows = [(int(r['id']), r['name'], r['pattern'], r['mechanic'], r['equipment'], int(r['level']),
                     r['primary'], r['secondary'], r['contra']) for r in csv.DictReader(f)]
        self.db.executemany('INSERT OR REPLACE INTO exercise VALUES (?,?,?,?,?,?,?,?,?)', rows)
        self.db.commit()

    def exercises_csv_rows(self):
        return self.db.execute('SELECT * FROM exercise ORDER BY id').fetchall()

    # ------------------------------------------------------------ профілі та плани
    def save_profile(self, profile, user_id=None) -> int:
        cur = self.db.execute('INSERT INTO profile(name, data, created_at, user_id) VALUES (?,?,?,?)',
                              (profile.name, json.dumps(profile.to_dict(), ensure_ascii=False),
                               datetime.now().isoformat(timespec='seconds'), user_id))
        self.db.commit()
        return cur.lastrowid

    def get_profile(self, pid):
        from .domain import Profile
        r = self.db.execute('SELECT data FROM profile WHERE id=?', (pid,)).fetchone()
        return Profile.from_dict(json.loads(r['data'])) if r else None

    def save_plan(self, profile_id, plan, mesocycle=1, user_id=None) -> int:
        cur = self.db.execute(
            'INSERT INTO plan(profile_id, method, status, objective, runtime, mesocycle, created_at, user_id) '
            'VALUES (?,?,?,?,?,?,?,?)', (profile_id, plan.method, plan.status, plan.objective, plan.runtime,
                                         mesocycle, datetime.now().isoformat(timespec='seconds'), user_id))
        pid = cur.lastrowid
        for d, items in plan.days.items():
            for k, it in enumerate(items):
                self.db.execute(
                    'INSERT INTO plan_item(plan_id, day, position, exercise_id, sets, reps_min, reps_max, rir, '
                    'rest, load, reps_target) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (pid, d, k, it.exercise.id, it.sets, it.reps[0], it.reps[1], it.rir, it.rest, it.load,
                     it.reps[0]))
        self.db.commit()
        return pid

    def plan_items(self, plan_id):
        return self.db.execute(
            'SELECT pi.*, e.name, e.equipment FROM plan_item pi JOIN exercise e ON e.id = pi.exercise_id '
            'WHERE plan_id=? ORDER BY day, position', (plan_id,)).fetchall()

    def plan_row(self, plan_id):
        return self.db.execute('SELECT * FROM plan WHERE id=?', (plan_id,)).fetchone()

    def latest_plans(self, user_id, limit=20):
        return self.db.execute('SELECT p.*, pr.name AS profile_name, pr.data AS profile_data FROM plan p JOIN profile pr '
                               'ON pr.id = p.profile_id WHERE p.user_id=? ORDER BY p.id DESC LIMIT ?',
                               (user_id, limit)).fetchall()

    def delete_plan(self, plan_id):
        """Видаляє план разом з елементами та журналом (каскадно) і профіль, якщо він більше не використовується."""
        row = self.plan_row(plan_id)
        if not row:
            return
        self.db.execute('DELETE FROM plan WHERE id=?', (plan_id,))
        self.db.execute('DELETE FROM profile WHERE id=? AND NOT EXISTS (SELECT 1 FROM plan WHERE profile_id=?)',
                        (row['profile_id'], row['profile_id']))
        self.db.commit()

    # ------------------------------------------------------------ журнал і адаптація
    def log_sets(self, item_id, date, sets):
        self.db.executemany('INSERT INTO set_log(plan_item_id, session_date, set_no, load, reps, rir) '
                            'VALUES (?,?,?,?,?,?)', [(item_id, date, i + 1, s.load, s.reps, s.rir)
                                                     for i, s in enumerate(sets)])
        self.db.commit()

    def update_item_target(self, item_id, load, reps_target):
        self.db.execute('UPDATE plan_item SET load=?, reps_target=? WHERE id=?', (load, reps_target, item_id))
        self.db.commit()

    def item_logs(self, item_id):
        return self.db.execute('SELECT * FROM set_log WHERE plan_item_id=? ORDER BY id',
                               (item_id,)).fetchall()
