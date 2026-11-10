import unittest
from typing import Iterable

from game.board import Board
from game.cell import Cell
from game.character import Character, Status
from game.clue import (
    AtLeastClue,
    AtMostClue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    SameClue,
)
from game.region import Column, ExplicitList, Neighbors, Row
from game.semantics import (
    Assignment,
    count_criminals,
    evaluate_clue,
    evaluate_clues,
    validate_assignment,
)


def _make_board_3x3() -> Board:
    """Tạo bàn cờ 3x3 chuẩn gồm 9 nhân vật từ A1 đến C3."""
    cells = [Cell(r, c) for r in range(1, 4) for c in range(1, 4)]
    chars = {
        cell: Character(name=f"Char_{cell.label}", profession="Worker")
        for cell in cells
    }
    return Board(3, chars)


def _assign_criminals(board: Board, criminal_labels: Iterable[str] = ()) -> dict[Cell, Status]:
    """
    Tạo một phép gán đầy đủ trên board:
    Các ô có nhãn trong criminal_labels là CRIMINAL, các ô còn lại là INNOCENT.
    """
    crim_set = {Cell.parse(label) for label in criminal_labels}
    return {
        cell: (Status.CRIMINAL if cell in crim_set else Status.INNOCENT)
        for cell in board.cells()
    }


class TestSemanticsBasicAndValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.board = _make_board_3x3()

    def test_validate_assignment_valid(self) -> None:
        assignment = _assign_criminals(self.board, ["A1", "C3"])
        # Không ném lỗi
        validate_assignment(self.board, assignment)

    def test_validate_assignment_missing_cell(self) -> None:
        assignment = _assign_criminals(self.board, ["A1"])
        del assignment[Cell.parse("B2")]  # Làm thiếu ô B2
        with self.assertRaises(ValueError):
            validate_assignment(self.board, assignment)

    def test_validate_assignment_invalid_status_type(self) -> None:
        assignment = _assign_criminals(self.board, ["A1"])
        assignment[Cell.parse("A1")] = True  # type: ignore[assignment] # Gán nhầm bool thay vì Status
        with self.assertRaises(ValueError):
            validate_assignment(self.board, assignment)

    def test_fact_clue(self) -> None:
        a1 = Cell.parse("A1")
        clue_crim = FactClue(a1, Status.CRIMINAL)
        clue_inno = FactClue(a1, Status.INNOCENT)

        assign_a1_crim = _assign_criminals(self.board, ["A1"])
        assign_a1_inno = _assign_criminals(self.board, [])

        self.assertTrue(evaluate_clue(clue_crim, self.board, assign_a1_crim))
        self.assertFalse(evaluate_clue(clue_crim, self.board, assign_a1_inno))
        self.assertTrue(evaluate_clue(clue_inno, self.board, assign_a1_inno))
        self.assertFalse(evaluate_clue(clue_inno, self.board, assign_a1_crim))

    def test_same_clue(self) -> None:
        clue = SameClue(Cell.parse("A1"), Cell.parse("B2"))

        # Cả hai cùng CRIMINAL -> True
        self.assertTrue(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["A1", "B2"])))
        # Cả hai cùng INNOCENT -> True
        self.assertTrue(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["C3"])))
        # Một CRIMINAL, một INNOCENT -> False
        self.assertFalse(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["A1"])))
        self.assertFalse(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["B2"])))

    def test_different_clue(self) -> None:
        clue = DifferentClue(Cell.parse("A1"), Cell.parse("B2"))

        # Một CRIMINAL, một INNOCENT -> True
        self.assertTrue(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["A1"])))
        self.assertTrue(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["B2"])))
        # Cả hai cùng trạng thái -> False
        self.assertFalse(evaluate_clue(clue, self.board, _assign_criminals(self.board, ["A1", "B2"])))
        self.assertFalse(evaluate_clue(clue, self.board, _assign_criminals(self.board, [])))