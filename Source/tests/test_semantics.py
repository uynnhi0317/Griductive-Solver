from dataclasses import dataclass
from itertools import product
from typing import Any, ClassVar, Iterable, Mapping

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Character, Status
from game.clue import (
    AtLeastClue,
    AtMostClue,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    SameClue,
)
from game.region import Column, ExplicitList, Neighbors, Row, Region
from game.semantics import (
    Assignment,
    count_criminals,
    evaluate_clue,
    evaluate_clue_unchecked,
    evaluate_clues,
    register_evaluator,
    validate_assignment,
)


@pytest.fixture
def board() -> Board:
    """Tạo bàn cờ 3x3 chuẩn gồm 9 nhân vật từ A1 đến C3."""
    cells = [Cell(r, c) for r in range(1, 4) for c in range(1, 4)]
    chars = {
        cell: Character(name=f"Char_{cell.label}", profession="Worker")
        for cell in cells
    }
    return Board(3, chars)


def _assign_criminals(
    board: Board, criminal_labels: Iterable[str] = ()
) -> dict[Cell, Status]:
    """
    Tạo một phép gán đầy đủ trên board:
    Các ô có nhãn trong criminal_labels là CRIMINAL, các ô còn lại là INNOCENT.
    """
    crim_set = {Cell.parse(label) for label in criminal_labels}
    return {
        cell: (Status.CRIMINAL if cell in crim_set else Status.INNOCENT)
        for cell in board.cells()
    }


def _row(i: int) -> Row:
    return Row(i)


def _col(letter: str) -> Column:
    return Column(letter)


def _nb(label: str) -> Neighbors:
    return Neighbors(Cell.parse(label))


def _explicit(*lbls: str) -> ExplicitList:
    return ExplicitList(tuple(Cell.parse(lbl) for lbl in lbls))


REGIONS: dict[str, Region] = {
    "row": _row(1),
    "column": _col("A"),
    "neighbors_corner": _nb("A1"),  # 3 ô
    "neighbors_edge": _nb("B1"),    # 5 ô
    "neighbors_center": _nb("B2"),  # 8 ô
    "explicit": _explicit("A1", "B2", "C3"),
}


# 1. Basic & Validation
def test_validate_assignment_valid(board: Board) -> None:
    assignment = _assign_criminals(board, ["A1", "C3"])
    validate_assignment(board, assignment)


def test_validate_assignment_missing_cell(board: Board) -> None:
    assignment = _assign_criminals(board, ["A1"])
    del assignment[Cell.parse("B2")]
    with pytest.raises(ValueError):
        validate_assignment(board, assignment)


def test_validate_assignment_extra_cell(board: Board) -> None:
    assignment = _assign_criminals(board, ["A1"])
    assignment[Cell.parse("D4")] = Status.INNOCENT
    with pytest.raises(ValueError):
        validate_assignment(board, assignment)


def test_validate_assignment_invalid_status_type(board: Board) -> None:
    assignment = _assign_criminals(board, ["A1"])
    assignment[Cell.parse("A1")] = True  # type: ignore[assignment]
    with pytest.raises(ValueError):
        validate_assignment(board, assignment)


def test_fact_clue(board: Board) -> None:
    a1 = Cell.parse("A1")
    clue_crim = FactClue(a1, Status.CRIMINAL)
    clue_inno = FactClue(a1, Status.INNOCENT)

    assign_a1_crim = _assign_criminals(board, ["A1"])
    assign_a1_inno = _assign_criminals(board, [])

    assert evaluate_clue(clue_crim, board, assign_a1_crim) is True
    assert evaluate_clue(clue_crim, board, assign_a1_inno) is False
    assert evaluate_clue(clue_inno, board, assign_a1_inno) is True
    assert evaluate_clue(clue_inno, board, assign_a1_crim) is False


def test_same_clue(board: Board) -> None:
    clue = SameClue(Cell.parse("A1"), Cell.parse("B2"))

    assert evaluate_clue(clue, board, _assign_criminals(board, ["A1", "B2"])) is True
    assert evaluate_clue(clue, board, _assign_criminals(board, ["C3"])) is True
    assert evaluate_clue(clue, board, _assign_criminals(board, ["A1"])) is False
    assert evaluate_clue(clue, board, _assign_criminals(board, ["B2"])) is False


def test_different_clue(board: Board) -> None:
    clue = DifferentClue(Cell.parse("A1"), Cell.parse("B2"))

    assert evaluate_clue(clue, board, _assign_criminals(board, ["A1"])) is True
    assert evaluate_clue(clue, board, _assign_criminals(board, ["B2"])) is True
    assert evaluate_clue(clue, board, _assign_criminals(board, ["A1", "B2"])) is False
    assert evaluate_clue(clue, board, _assign_criminals(board, [])) is False


# 2. Counting Boundaries
@pytest.mark.parametrize("name,region", list(REGIONS.items()))
def test_k_zero_and_k_full(board: Board, name: str, region: Region) -> None:
    cells = region.cells(board)
    n = len(cells)
    none = _assign_criminals(board, [])
    full = _assign_criminals(board, [c.label for c in cells])

    # k = 0
    assert evaluate_clue(ExactlyClue(region, 0), board, none) is True
    assert evaluate_clue(ExactlyClue(region, 0), board, full) is False
    assert evaluate_clue(AtLeastClue(region, 0), board, none) is True
    assert evaluate_clue(AtLeastClue(region, 0), board, full) is True  # luôn đúng
    assert evaluate_clue(AtMostClue(region, 0), board, none) is True
    assert evaluate_clue(AtMostClue(region, 0), board, full) is False

    # k = |R|
    assert evaluate_clue(ExactlyClue(region, n), board, full) is True
    assert evaluate_clue(ExactlyClue(region, n), board, none) is False
    assert evaluate_clue(AtLeastClue(region, n), board, full) is True
    assert evaluate_clue(AtLeastClue(region, n), board, none) is False
    assert evaluate_clue(AtMostClue(region, n), board, none) is True  # luôn đúng
    assert evaluate_clue(AtMostClue(region, n), board, full) is True


def test_criminals_outside_region_ignored(board: Board) -> None:
    a = _assign_criminals(board, ["A3", "B3", "C3", "B2"])
    assert evaluate_clue(ExactlyClue(_row(1), 0), board, a) is True


def test_neighbors_exclude_self(board: Board) -> None:
    a = _assign_criminals(board, ["B2"])
    assert evaluate_clue(ExactlyClue(_nb("B2"), 0), board, a) is True
    assert evaluate_clue(ExactlyClue(_nb("A1"), 1), board, a) is True


@pytest.mark.parametrize(
    "name", ["row", "neighbors_corner", "neighbors_edge", "neighbors_center"]
)
def test_exhaustive_all_k(board: Board, name: str) -> None:
    region = REGIONS[name]
    cells = region.cells(board)
    for bits in product([False, True], repeat=len(cells)):
        a = _assign_criminals(
            board, [c.label for c, b in zip(cells, bits) if b]
        )
        n = sum(bits)
        for k in range(len(cells) + 1):
            assert evaluate_clue(ExactlyClue(region, k), board, a) is (n == k)
            assert evaluate_clue(AtLeastClue(region, k), board, a) is (n >= k)
            assert evaluate_clue(AtMostClue(region, k), board, a) is (n <= k)


# 3. Helpers & Errors
def test_count_criminals(board: Board) -> None:
    a = _assign_criminals(board, ["A1", "B2"])
    cells = [Cell.parse(x) for x in ("A1", "B1", "B2")]
    assert count_criminals(cells, a) == 2
    assert count_criminals([], a) == 0


def test_evaluate_clues(board: Board) -> None:
    a = _assign_criminals(board, ["A1"])
    ok = FactClue(Cell.parse("A1"), Status.CRIMINAL)
    bad = FactClue(Cell.parse("B2"), Status.CRIMINAL)

    assert evaluate_clues([], board, a) is True
    assert evaluate_clues([ok], board, a) is True
    assert evaluate_clues([ok, bad], board, a) is False
    # Hỗ trợ truyền generator/iterator mà không bị cạn sau bước validate
    assert evaluate_clues((c for c in [ok]), board, a) is True


def test_k_above_region_size_rejected(board: Board) -> None:
    a = _assign_criminals(board, [])
    with pytest.raises(ValueError):  # k=4 > |Row|=3, bị bắt ở clue.validate
        evaluate_clue(ExactlyClue(_row(1), 4), board, a)


def test_cell_outside_board_rejected(board: Board) -> None:
    a = _assign_criminals(board, [])
    with pytest.raises(ValueError):
        evaluate_clue(FactClue(Cell(4, 4), Status.CRIMINAL), board, a)


def test_missing_cell_rejected(board: Board) -> None:
    a = _assign_criminals(board, [])
    del a[Cell.parse("C3")]
    with pytest.raises(ValueError):
        evaluate_clue(ExactlyClue(_row(1), 0), board, a)


def test_non_clue_rejected(board: Board) -> None:
    with pytest.raises(TypeError):
        evaluate_clue("not a clue", board, _assign_criminals(board))  # type: ignore[arg-type]


# 4. Registry & Unchecked
def test_evaluate_clue_unchecked_matches_checked(board: Board) -> None:
    clue = FactClue(Cell.parse("A1"), Status.CRIMINAL)
    assign_true = _assign_criminals(board, ["A1"])
    assign_false = _assign_criminals(board, ["B2"])

    assert evaluate_clue_unchecked(clue, board, assign_true) is True
    assert evaluate_clue_unchecked(clue, board, assign_false) is False


def test_unregistered_clue_raises_type_error(board: Board) -> None:
    @dataclass(frozen=True)
    class DummyClue(Clue):
        kind: ClassVar[str] = "DUMMY"

        def validate(self, board: Board) -> None:
            pass

        def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
            return ()

        def to_dict(self) -> dict[str, Any]:
            return {}

        def describe(self, board: Board) -> str:
            return "dummy"

        @classmethod
        def from_dict(cls, data: Mapping[str, Any]) -> "DummyClue":
            return cls()

    assignment = _assign_criminals(board, [])
    with pytest.raises(TypeError):
        evaluate_clue(DummyClue(), board, assignment)


def test_register_evaluator_validation() -> None:
    # Không truyền class nào -> TypeError
    with pytest.raises(TypeError):
        register_evaluator()

    # Truyền đối tượng không phải subclass của Clue -> TypeError
    with pytest.raises(TypeError):
        @register_evaluator(int)  # type: ignore[arg-type]
        def _bad_eval(clue: Any, board: Board, assignment: Assignment) -> bool:
            return True

    # Đăng ký trùng loại clue đã có -> ValueError
    with pytest.raises(ValueError):
        @register_evaluator(FactClue)
        def _dup_eval(clue: FactClue, board: Board, assignment: Assignment) -> bool:
            return True


def test_subclass_inherits_parent_evaluator_via_mro(board: Board) -> None:
    @dataclass(frozen=True)
    class SubFactClue(FactClue):
        pass

    sub_clue = SubFactClue(Cell.parse("B2"), Status.CRIMINAL)
    assignment = _assign_criminals(board, ["B2"])
    assert evaluate_clue(sub_clue, board, assignment) is True