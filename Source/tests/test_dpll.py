import ast
import itertools
import random
from pathlib import Path

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Status
from logic.cnf import CNF
from logic.variable_map import VariableMap
from solver.dpll import SolveResult, SolverTimeout, check_model, solve
from solver.stats import SolverStats


def brute_force_sat(clauses, n):
    for bits in itertools.product([False, True], repeat=n):
        if all(any(bits[abs(l) - 1] == (l > 0) for l in clause) for clause in clauses):
            return True
    return False


def pigeonhole(pigeons, holes):
    var = lambda i, j: (i - 1) * holes + j
    cnf = CNF()
    for i in range(1, pigeons + 1):
        cnf.add_clause([var(i, j) for j in range(1, holes + 1)])
    for j in range(1, holes + 1):
        for i in range(1, pigeons + 1):
            for k in range(i + 1, pigeons + 1):
                cnf.add_clause([-var(i, j), -var(k, j)])
    return cnf, pigeons * holes


def make_board(n=3):
    names = iter("ABCDEFGHIJKLMNOPQRSTUVWXY")
    data = {Cell(r, c).label: {"name": next(names), "profession": "X"}
            for r in range(1, n + 1) for c in range(1, n + 1)}
    return Board.from_dict(n, data)


# ---------- các ca cơ bản ----------
def test_empty_cnf_is_sat():
    r = solve(CNF())
    assert r.sat and r.model == {}
    assert (r.stats.decisions, r.stats.propagations, r.stats.backtracks) == (0, 0, 0)


def test_empty_cnf_with_num_vars_gives_full_model():
    r = solve(CNF(), num_vars=3)
    assert r.model == {1: False, 2: False, 3: False}


def test_empty_clause_is_unsat_without_decisions():
    r = solve(CNF([[]]))
    assert not r.sat and r.model is None
    assert r.stats.decisions == 0


def test_contradicting_units_are_unsat():
    r = solve(CNF([[1], [-1]]))
    assert not r.sat and r.model is None
    assert r.stats.decisions == 0


def test_unit_chain_needs_no_decision():
    r = solve(CNF([[1], [-1, 2], [-2, 3]]))
    assert r.sat
    assert r.model == {1: True, 2: True, 3: True}
    assert r.stats.decisions == 0
    assert r.stats.propagations == 3
    assert r.stats.backtracks == 0


def test_backtracking_counting_without_pure_literal():
    # biến 1 thử False trước: ép 2 = True rồi conflict -> backtrack, thử True
    r = solve(CNF([[1, 2], [1, -2]]), pure_literal=False)
    assert r.sat
    assert r.model == {1: True, 2: False}
    assert r.stats.decisions == 2
    assert r.stats.propagations == 1
    assert r.stats.backtracks == 1
    assert r.stats.pure_literals == 0


@pytest.mark.parametrize("pure", [True, False])
def test_backtracking_counting_when_no_pure_literal_exists(pure):
    # mọi biến đều có cả hai dấu nên pure literal không can thiệp: hai chế độ cho cùng số liệu
    cnf = CNF([[1, 2], [1, -2], [-1, 3], [-2, -3]])
    r = solve(cnf, pure_literal=pure)
    assert r.sat
    assert r.model == {1: True, 2: False, 3: True}
    assert (r.stats.decisions, r.stats.propagations, r.stats.backtracks) == (2, 3, 1)
    assert r.stats.pure_literals == 0


# ---------- pure literal elimination ----------
def test_pure_literal_is_assigned_without_decision():
    r = solve(CNF([[1, 2], [1, -2]]))
    assert r.sat
    assert r.model == {1: True, 2: False}
    s = r.stats
    assert (s.decisions, s.propagations, s.backtracks, s.pure_literals) == (0, 0, 0, 1)


def test_pure_literals_cascade():
    # biến 1 thuần -> mệnh đề (1 2) thỏa -> biến 2 chỉ còn dấu âm -> thuần
    r = solve(CNF([[1, 2], [-2, 3], [-2, -3]]))
    assert r.sat
    assert r.model == {1: True, 2: False, 3: False}
    assert (r.stats.decisions, r.stats.propagations, r.stats.pure_literals) == (0, 0, 2)


def test_pure_literal_ignores_satisfied_clauses():
    # sau khi 1 = True, mệnh đề (1 -2) đã thỏa nên biến 2 chỉ còn xuất hiện dương -> thuần
    r = solve(CNF([[1], [1, -2], [2, 3]]))
    assert r.sat
    assert r.model == {1: True, 2: True, 3: True}
    assert (r.stats.decisions, r.stats.propagations, r.stats.pure_literals) == (0, 1, 2)


def test_pure_literal_can_be_disabled():
    cnf = CNF([[1, 2], [-2, 3], [-2, -3]])
    r = solve(cnf, pure_literal=False)
    assert r.sat and check_model(cnf, r.model)
    assert r.stats.pure_literals == 0


def test_pure_literal_never_overrides_assumptions():
    cnf = CNF([[1, 2], [1, 3]])           # biến 1 thuần dương
    r = solve(cnf, assumptions=[-1])
    assert r.sat
    assert r.model[1] is False and r.model[2] is True and r.model[3] is True


@pytest.mark.parametrize("bad", [1, 0, None, "yes"])
def test_invalid_pure_literal_flag(bad):
    with pytest.raises(ValueError):
        solve(CNF(), pure_literal=bad)


def test_all_four_clauses_on_two_vars_is_unsat():
    r = solve(CNF([[1, 2], [1, -2], [-1, 2], [-1, -2]]))
    assert not r.sat
    assert r.stats.backtracks == r.stats.decisions  # mọi decision đều thất bại


def test_pigeonhole_unsat_and_sat():
    cnf, n = pigeonhole(3, 2)
    assert not solve(cnf, num_vars=n).sat
    cnf, n = pigeonhole(3, 3)
    r = solve(cnf, num_vars=n)
    assert r.sat and check_model(cnf, r.model)


# ---------- model ----------
def test_model_is_full_and_satisfies_cnf():
    cnf = CNF([[1, 2, 3], [-1, 4], [-2, -4]])
    r = solve(cnf, num_vars=6)
    assert r.sat
    assert sorted(r.model) == [1, 2, 3, 4, 5, 6]
    assert check_model(cnf, r.model)


def test_num_vars_smaller_than_needed_is_expanded():
    r = solve(CNF([[5]]), num_vars=2)
    assert sorted(r.model) == [1, 2, 3, 4, 5]
    assert r.model[5] is True


def test_check_model_detects_violation_and_missing():
    cnf = CNF([[1, 2]])
    assert check_model(cnf, {1: True, 2: False})
    assert not check_model(cnf, {1: False, 2: False})
    with pytest.raises(ValueError):
        check_model(cnf, {1: False})


# ---------- assumptions ----------
def test_assumptions_force_values():
    cnf = CNF([[1, 2]])
    r = solve(cnf, assumptions=[-1])
    assert r.sat and r.model[1] is False and r.model[2] is True


def test_assumptions_can_make_unsat():
    assert not solve(CNF([[1, 2]]), assumptions=[-1, -2]).sat


def test_contradictory_assumptions_are_unsat():
    r = solve(CNF([[1, 2]]), assumptions=[1, -1])
    assert not r.sat and r.model is None


def test_assumption_conflicting_with_unit_clause():
    assert not solve(CNF([[1]]), assumptions=[-1]).sat


def test_assumption_with_new_variable_extends_model():
    r = solve(CNF([[1]]), assumptions=[5])
    assert sorted(r.model) == [1, 2, 3, 4, 5]
    assert r.model[5] is True


def test_assumptions_are_not_counted_as_decisions_or_propagations():
    r = solve(CNF(), assumptions=[1, -2])
    assert r.sat
    assert (r.stats.decisions, r.stats.propagations) == (0, 0)


@pytest.mark.parametrize("bad", [0, True, "1", 1.0, None])
def test_invalid_assumption_is_rejected(bad):
    with pytest.raises(ValueError):
        solve(CNF([[1]]), assumptions=[bad])


def test_entailment_pattern():
    # KB: (C1) ∧ (¬C1 ∨ C2)  =>  KB ⊨ C2
    kb = CNF([[1], [-1, 2]])
    assert not solve(kb, assumptions=[-2]).sat   # KB ∧ ¬C2 là UNSAT
    assert solve(kb, assumptions=[2]).sat        # KB ∧ C2 là SAT


# ---------- đối chiếu vét cạn ----------
def random_cnf(rng, n):
    cnf = CNF()
    for _ in range(rng.randint(1, 4 * n)):
        k = rng.randint(1, 3)
        cnf.add_clause([rng.choice([-1, 1]) * rng.randint(1, n) for _ in range(k)])
    return cnf


@pytest.mark.parametrize("pure", [True, False])
def test_matches_brute_force_on_random_cnfs(pure):
    rng = random.Random(2026)
    sat_seen = unsat_seen = 0
    for _ in range(400):
        n = rng.randint(2, 8)
        cnf = random_cnf(rng, n)
        r = solve(cnf, num_vars=n, pure_literal=pure)
        expected = brute_force_sat(list(cnf), n)
        assert r.sat == expected, list(cnf)
        if r.sat:
            sat_seen += 1
            assert sorted(r.model) == list(range(1, n + 1))
            assert check_model(cnf, r.model)
        else:
            unsat_seen += 1
            assert r.model is None
    assert sat_seen > 20 and unsat_seen > 20  # bộ dữ liệu có cả hai loại


@pytest.mark.parametrize("pure", [True, False])
def test_matches_brute_force_with_assumptions(pure):
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(2, 7)
        cnf = random_cnf(rng, n)
        assumptions = [rng.choice([-1, 1]) * v for v in rng.sample(range(1, n + 1), rng.randint(1, min(3, n)))]
        r = solve(cnf, num_vars=n, assumptions=assumptions, pure_literal=pure)
        extended = list(cnf) + [(a,) for a in assumptions]
        assert r.sat == brute_force_sat(extended, n), (list(cnf), assumptions)
        if r.sat:
            assert check_model(cnf, r.model)
            assert all(r.model[abs(a)] == (a > 0) for a in assumptions)


# ---------- tính chất của solver ----------
def test_cnf_is_not_modified():
    cnf = CNF([[1, 2], [-1, 3], [-2, -3]])
    before = cnf.clauses
    solve(cnf, num_vars=5, assumptions=[1])
    assert cnf.clauses == before


def test_deterministic_results_and_stats():
    cnf, n = pigeonhole(4, 3)
    a = solve(cnf, num_vars=n)
    b = solve(cnf, num_vars=n)
    assert (a.sat, a.model) == (b.sat, b.model)
    assert (a.stats.decisions, a.stats.propagations, a.stats.backtracks) == \
           (b.stats.decisions, b.stats.propagations, b.stats.backtracks)


def test_runtime_is_recorded():
    r = solve(CNF([[1, 2]]))
    assert r.stats.runtime >= 0.0
    assert isinstance(r, SolveResult)


def test_timeout_raises_with_stats():
    cnf, n = pigeonhole(6, 5)
    with pytest.raises(SolverTimeout) as info:
        solve(cnf, num_vars=n, time_limit=1e-9)
    assert isinstance(info.value.stats, SolverStats)
    assert info.value.stats.runtime > 0


@pytest.mark.parametrize("bad", [-1, True, 1.5, "3"])
def test_invalid_num_vars(bad):
    with pytest.raises(ValueError):
        solve(CNF(), num_vars=bad)


@pytest.mark.parametrize("bad", [0, -1, True, "1"])
def test_invalid_time_limit(bad):
    with pytest.raises(ValueError):
        solve(CNF(), time_limit=bad)


def test_stats_merge_and_as_dict():
    a = SolverStats(decisions=1, propagations=2, pure_literals=4, backtracks=3, runtime=0.5)
    b = SolverStats(decisions=10, propagations=20, pure_literals=40, backtracks=30, runtime=1.5)
    a.merge(b)
    assert a.as_dict() == {
        "decisions": 11, "propagations": 22, "pure_literals": 44, "backtracks": 33, "runtime": 2.0,
    }
    assert list(a.as_dict()) == ["decisions", "propagations", "pure_literals", "backtracks", "runtime"]


def test_solver_modules_do_not_import_game():
    """Solver phải độc lập với game/"""
    root = Path(__file__).resolve().parent.parent / "solver"
    for name in ("dpll.py", "stats.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not any(m == "game" or m.startswith("game.") for m in imported), name


# ---------- ghép với VariableMap ----------
def test_pipeline_with_variable_map():
    board = make_board(3)
    vmap = VariableMap(board)
    a1, c3 = Cell.parse("A1"), Cell.parse("C3")

    kb = CNF()
    kb.add_clause([-vmap.literal(a1), vmap.literal(c3)])   # SAME(A1, C3)
    kb.add_clause([vmap.literal(a1), -vmap.literal(c3)])
    kb.add_clause([vmap.status_literal(a1, Status.CRIMINAL)])

    v = vmap.var(c3)
    assert not solve(kb, vmap.max_var, assumptions=[-v]).sat   # C3 không thể Innocent
    r = solve(kb, vmap.max_var, assumptions=[v])
    assert r.sat
    statuses = vmap.decode(r.model)
    assert statuses[a1] is Status.CRIMINAL
    assert statuses[c3] is Status.CRIMINAL
    assert len(statuses) == 9