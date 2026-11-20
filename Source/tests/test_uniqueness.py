from pathlib import Path
import pytest

from agent.uniqueness import UniquenessStatus, check_clues_uniqueness, check_puzzle_uniqueness
from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import DifferentClue, FactClue, SameClue
from game.puzzle_loader import load_puzzle
import agent.uniqueness as U
from solver.dpll import SolverTimeout
from solver.stats import SolverStats


def make_board(n=3):
    names = iter("ABCDEFGHIJKLMNOPQRSTUVWXY")
    data = {Cell(r, c).label: {"name": next(names), "profession": "X"}
            for r in range(1, n + 1) for c in range(1, n + 1)}
    return Board.from_dict(n, data)


def facts(board, skip=()):
    return [FactClue(c, Status.CRIMINAL if i % 2 else Status.INNOCENT)
            for i, c in enumerate(board.cells()) if c not in skip]


def test_unique_when_every_cell_is_fixed():
    board = make_board()
    r = check_clues_uniqueness(board, facts(board))
    assert r.status is UniquenessStatus.UNIQUE and r.is_unique
    assert r.sat_calls == 2 and r.second_solution is None
    assert len(r.solution) == 9


def test_multiple_returns_counterexample():
    board = make_board()
    free = board.cells()[0]
    r = check_clues_uniqueness(board, facts(board, skip=[free]))
    assert r.status is UniquenessStatus.MULTIPLE
    assert r.solution != r.second_solution
    assert r.differing_cells() == (free,)


def test_pair_clue_leaves_two_solutions():
    board = make_board()
    a, b = board.cells()[0], board.cells()[1]
    r = check_clues_uniqueness(board, facts(board, skip=[a, b]) + [DifferentClue(a, b)])
    assert r.status is UniquenessStatus.MULTIPLE
    assert set(r.differing_cells()) == {a, b}


def test_same_clue_with_fact_is_unique():
    board = make_board()
    a, b = board.cells()[0], board.cells()[1]
    r = check_clues_uniqueness(board, facts(board, skip=[a, b]) + [FactClue(a, Status.CRIMINAL), SameClue(a, b)])
    assert r.is_unique
    assert r.solution[b] is Status.CRIMINAL


def test_contradiction_is_no_solution():
    board = make_board()
    a = board.cells()[0]
    r = check_clues_uniqueness(board, [FactClue(a, Status.CRIMINAL), FactClue(a, Status.INNOCENT)])
    assert r.status is UniquenessStatus.NO_SOLUTION
    assert r.solution is None and r.sat_calls == 1


def test_timeout_on_first_call(monkeypatch):
    def fake(cnf, num_vars=None, time_limit=None):
        raise SolverTimeout(SolverStats())           # ép solver timeout ở lần giải 1
    monkeypatch.setattr(U, "solve", fake)
    board = make_board()
    r = check_clues_uniqueness(board, facts(board))
    assert r.status is UniquenessStatus.TIMEOUT
    assert r.solution is None and r.sat_calls == 1


def test_timeout_on_second_call_keeps_first_solution(monkeypatch):
    real, n = U.solve, [0]
    def flaky(cnf, num_vars=None, time_limit=None):
        n[0] += 1
        if n[0] == 2:                                # lần 1 giải thật, lần 2 ép timeout
            raise SolverTimeout(SolverStats())
        return real(cnf, num_vars=num_vars, time_limit=time_limit)
    monkeypatch.setattr(U, "solve", flaky)
    board = make_board()
    r = check_clues_uniqueness(board, facts(board))
    assert r.status is UniquenessStatus.TIMEOUT
    assert r.solution is not None and r.sat_calls == 2


def test_counting_clues_with_regions():
    from game.clue import ExactlyClue, AtMostClue
    from game.region import Row
    board = make_board()
    row1 = set(board.row_cells(1))
    rest = facts(board, skip=row1)
    # Row 1 có đúng 1 tội phạm: 3 khả năng -> MULTIPLE
    r = check_clues_uniqueness(board, rest + [ExactlyClue(Row(1), 1)])
    assert r.status is UniquenessStatus.MULTIPLE
    # Thêm AT_MOST(0) trên row 1 -> mâu thuẫn với EXACTLY 1
    r = check_clues_uniqueness(board, rest + [ExactlyClue(Row(1), 1), AtMostClue(Row(1), 0)])
    assert r.status is UniquenessStatus.NO_SOLUTION
    # EXACTLY 0 trên row 1 -> duy nhất
    r = check_clues_uniqueness(board, rest + [ExactlyClue(Row(1), 0)])
    assert r.is_unique


def test_known_makes_ambiguous_clues_unique():
    board = make_board()
    a, b = board.cells()[0], board.cells()[1]
    clues = facts(board, skip=[a, b]) + [DifferentClue(a, b)]
    assert check_clues_uniqueness(board, clues).status is UniquenessStatus.MULTIPLE   # không có known: mơ hồ
    r = check_clues_uniqueness(board, clues, known={a: Status.CRIMINAL})              # có known: duy nhất
    assert r.is_unique
    assert r.solution[b] is Status.INNOCENT


def test_known_contradicting_clue_is_no_solution():
    board = make_board()
    a = board.cells()[0]
    r = check_clues_uniqueness(board, [FactClue(a, Status.CRIMINAL)], known={a: Status.INNOCENT})
    assert r.status is UniquenessStatus.NO_SOLUTION


PUZZLE_DIR = Path(__file__).resolve().parents[1] / "puzzles"
PUZZLE_FILES = sorted(PUZZLE_DIR.rglob("*.json"))


@pytest.mark.skipif(not PUZZLE_FILES, reason="không tìm thấy puzzle nào")
@pytest.mark.parametrize("path", PUZZLE_FILES, ids=lambda p: p.name)
def test_bundled_puzzles_are_unique(path):
    puzzle = load_puzzle(path)
    r = check_puzzle_uniqueness(puzzle)
    assert r.is_unique, f"{path.name}: {r.status.value}"