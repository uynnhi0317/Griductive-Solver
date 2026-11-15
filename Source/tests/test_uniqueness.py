from agent.uniqueness import UniquenessStatus, check_clues_uniqueness
from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import DifferentClue, FactClue, SameClue


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


def test_timeout_is_reported_not_raised():
    board = make_board()
    r = check_clues_uniqueness(board, [], time_limit=1e-9)
    assert r.status in (UniquenessStatus.TIMEOUT, UniquenessStatus.MULTIPLE)


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