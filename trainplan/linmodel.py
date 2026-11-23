"""Незалежне від розв'язувача подання цілочисельної лінійної моделі та два бекенди:
HiGHS (через scipy.optimize.milp) і OR-Tools CP-SAT."""
from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

INF = math.inf


@dataclass
class LinearModel:
    names: list = field(default_factory=list)
    lb: list = field(default_factory=list)
    ub: list = field(default_factory=list)
    obj: list = field(default_factory=list)
    rows: list = field(default_factory=list)       # (dict{var: coef}, lo, hi)
    index: dict = field(default_factory=dict)

    def var(self, key, lb=0, ub=INF, cost=0.0):
        self.index[key] = len(self.names)
        self.names.append(key); self.lb.append(lb); self.ub.append(ub); self.obj.append(cost)
        return self.index[key]

    def add(self, coefs, lo=-INF, hi=INF):
        """coefs: ітерований набір (ключ змінної, коефіцієнт)."""
        d = {}
        for k, c in coefs:
            if c:
                j = self.index[k]
                d[j] = d.get(j, 0.0) + c
        self.rows.append((d, lo, hi))

    @property
    def n_vars(self):
        return len(self.names)

    @property
    def n_cons(self):
        return len(self.rows)


@dataclass
class Solution:
    status: str               # optimal | feasible | infeasible | error
    values: dict
    objective: float | None
    bound: float | None
    runtime: float
    solver: str

    @property
    def gap(self):
        if self.objective is None or self.bound is None:
            return None
        return abs(self.objective - self.bound) / max(1e-9, abs(self.objective))


def solve_highs(m: LinearModel, time_limit=10.0, rel_gap=0.01) -> Solution:
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import csr_matrix
    data, ri, ci, lo, hi = [], [], [], [], []
    for i, (d, l, h) in enumerate(m.rows):
        for j, c in d.items():
            ri.append(i); ci.append(j); data.append(c)
        lo.append(l); hi.append(h)
    A = csr_matrix((data, (ri, ci)), shape=(m.n_cons, m.n_vars))
    t0 = time.perf_counter()
    res = milp(np.array(m.obj, dtype=float), constraints=LinearConstraint(A, lo, hi),
               integrality=np.ones(m.n_vars), bounds=Bounds(m.lb, m.ub),
               options=dict(time_limit=time_limit, mip_rel_gap=rel_gap, disp=False))
    dt = time.perf_counter() - t0
    if res.x is None:
        st = 'infeasible' if res.status == 2 else 'error'
        return Solution(st, {}, None, None, dt, 'HiGHS')
    vals = {m.names[j]: int(round(v)) for j, v in enumerate(res.x)}
    st = 'optimal' if res.status == 0 else 'feasible'
    return Solution(st, vals, float(res.fun), getattr(res, 'mip_dual_bound', None), dt, 'HiGHS')


def _int_row(coefs: dict, lo, hi):
    """Масштабує рядок так, щоб усі коефіцієнти були цілими (CP-SAT працює лише з цілими)."""
    fr = {j: Fraction(c).limit_denominator(1000) for j, c in coefs.items()}
    den = 1
    for f in fr.values():
        den = den * f.denominator // math.gcd(den, f.denominator)
    ic = {j: int(f * den) for j, f in fr.items()}
    l = -INF if lo == -INF else math.ceil(lo * den - 1e-9)
    h = INF if hi == INF else math.floor(hi * den + 1e-9)
    return ic, l, h, den


def solve_cpsat(m: LinearModel, time_limit=10.0, rel_gap=0.01, workers=8) -> Solution:
    from ortools.sat.python import cp_model
    big = 10 ** 6
    model = cp_model.CpModel()
    xs = [model.new_int_var(int(m.lb[j]), int(m.ub[j]) if m.ub[j] != INF else big, str(m.names[j]))
          for j in range(m.n_vars)]
    for d, lo, hi in m.rows:
        ic, l, h, _ = _int_row(d, lo, hi)
        expr = sum(c * xs[j] for j, c in ic.items())
        if l == h:
            model.add(expr == l)
        else:
            if l != -INF:
                model.add(expr >= l)
            if h != INF:
                model.add(expr <= h)
    oc, _, _, oden = _int_row({j: c for j, c in enumerate(m.obj) if c}, -INF, INF)
    model.minimize(sum(c * xs[j] for j, c in oc.items()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.relative_gap_limit = rel_gap
    solver.parameters.num_workers = workers
    t0 = time.perf_counter()
    status = solver.solve(model)
    dt = time.perf_counter() - t0
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution('infeasible' if status == cp_model.INFEASIBLE else 'error', {}, None, None, dt, 'CP-SAT')
    vals = {m.names[j]: int(solver.value(xs[j])) for j in range(m.n_vars)}
    return Solution('optimal' if status == cp_model.OPTIMAL else 'feasible', vals,
                    solver.objective_value / oden, solver.best_objective_bound / oden, dt, 'CP-SAT')


def available_solvers():
    out = ['highs']
    try:
        import ortools  # noqa: F401
        out.insert(0, 'cpsat')
    except ImportError:
        pass
    return out


def solve(m: LinearModel, solver='auto', **kw) -> Solution:
    if solver == 'auto':
        solver = available_solvers()[0]
    return solve_cpsat(m, **kw) if solver == 'cpsat' else solve_highs(m, **kw)
