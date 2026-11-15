"""Test câu hiển thị (describe) của region và clue: chỉ kiểm tra chữ, không liên quan logic"""

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import (
    AtLeastClue,
    AtMostClue,
    ConnectedClue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    IfThenClue,
    NoAdjacentClue,
    OneOfKClue,
    ParityClue,
    SameClue,
)
from game.region import Column, ExplicitList, Neighbors, Row, join_names, possessive

C = Cell.parse
CRIM, INNO = Status.CRIMINAL, Status.INNOCENT


def _board3() -> Board:
    names = "Abel Bea Clara Derek Eliza Franz Grant Hannah James".split()
    data = {Cell(r, c).label: {"name": names[(r - 1) * 3 + c - 1], "profession": "X"}
            for r in range(1, 4) for c in range(1, 4)}
    return Board.from_dict(3, data)


BOARD = _board3()
PAIR = ExplicitList((C("A1"), C("C3")))           # Abel, James
TRIO = ExplicitList((C("A1"), C("B2"), C("C3")))  # Abel, Eliza, James
ONE = ExplicitList((C("B2"),))                    # Eliza


def test_helpers():
    assert join_names([]) == ""
    assert join_names(["A"]) == "A"
    assert join_names(["A", "B"]) == "A and B"
    assert join_names(["A", "B", "C"]) == "A, B and C"
    assert possessive("Eliza") == "Eliza's"
    assert possessive("James") == "James'"


@pytest.mark.parametrize("region, without_board, with_board", [
    (Row(2), "row 2", "row 2"),
    (Column("B"), "column B", "column B"),
    (Neighbors(C("B2")), "neighbors of B2", "Eliza's neighbors"),
    (Neighbors(C("C3")), "neighbors of C3", "James' neighbors"),
    (PAIR, "cells A1, C3", "Abel and James"),
    (TRIO, "cells A1, B2, C3", "Abel, Eliza and James"),
])
def test_region_describe(region, without_board, with_board):
    assert region.describe() == without_board
    assert region.describe(BOARD) == with_board


@pytest.mark.parametrize("clue, text", [
    # Clue lõi
    (FactClue(C("A1"), CRIM), "Abel is a criminal"),
    (FactClue(C("A1"), INNO), "Abel is innocent"),
    (SameClue(C("A1"), C("B1")), "Abel and Bea are the same (both criminals or both innocents)"),
    (DifferentClue(C("A1"), C("B1")), "Abel and Bea are different (one criminal, one innocent)"),
    # Row / Column
    (ExactlyClue(Row(2), 0), "There are no criminals in row 2"),
    (ExactlyClue(Row(2), 1), "There is exactly 1 criminal in row 2"),
    (ExactlyClue(Row(2), 2), "There are exactly 2 criminals in row 2"),
    (AtLeastClue(Column("A"), 1), "There is at least 1 criminal in column A"),
    (AtMostClue(Column("A"), 2), "There are at most 2 criminals in column A"),
    (AtMostClue(Column("A"), 0), "There are no criminals in column A"),
    # Neighbors
    (ExactlyClue(Neighbors(C("B2")), 0), "Eliza has no criminal neighbors"),
    (ExactlyClue(Neighbors(C("B2")), 1), "Eliza has exactly 1 criminal neighbor"),
    (AtLeastClue(Neighbors(C("C3")), 2), "James has at least 2 criminal neighbors"),
    (AtMostClue(Neighbors(C("A1")), 1), "Abel has at most 1 criminal neighbor"),
    # ExplicitList
    (ExactlyClue(PAIR, 0), "Neither Abel nor James is a criminal"),
    (ExactlyClue(PAIR, 1), "Exactly 1 of Abel and James is a criminal"),
    (ExactlyClue(PAIR, 2), "Both Abel and James are criminals"),
    (ExactlyClue(TRIO, 0), "None of Abel, Eliza and James are criminals"),
    (AtLeastClue(TRIO, 2), "At least 2 of Abel, Eliza and James are criminals"),
    (AtLeastClue(TRIO, 3), "All of Abel, Eliza and James are criminals"),
    (AtMostClue(TRIO, 1), "At most 1 of Abel, Eliza and James is a criminal"),
    (ExactlyClue(ONE, 1), "Eliza is a criminal"),
    (ExactlyClue(ONE, 0), "Eliza is innocent"),
    # PARITY
    (ParityClue(Row(1), "ODD"), "There is an odd number of criminals in row 1"),
    (ParityClue(Neighbors(C("B2")), "EVEN", status=INNO), "Eliza has an even number of innocent neighbors"),
    (ParityClue(TRIO, "ODD"), "An odd number of Abel, Eliza and James are criminals"),
    (ParityClue(ONE, "ODD"), "Eliza is a criminal"),
    (ParityClue(ONE, "EVEN", status=INNO), "Eliza is a criminal"),
    # CONNECTED
    (ConnectedClue(Column("A")), "All criminals in column A are connected"),
    (ConnectedClue(Row(2), status=INNO), "All innocents in row 2 are connected"),
    # NO_ADJACENT
    (NoAdjacentClue(Row(1)), "No two criminals in row 1 are next to each other"),
    (NoAdjacentClue(Neighbors(C("B2")), status=INNO), "No two innocents among Eliza's neighbors are next to each other"),
    (NoAdjacentClue(TRIO), "No two criminals among Abel, Eliza and James are next to each other"),
    # ONE_OF_K
    (OneOfKClue(cell=C("B1"), region=Row(1), k=1), "Bea is the only criminal in row 1"),
    (OneOfKClue(cell=C("B1"), region=Row(1), k=2, status=INNO), "Bea is one of the 2 innocents in row 1"),
    (OneOfKClue(cell=C("B1"), region=Neighbors(C("B2")), k=3), "Bea is one of Eliza's 3 criminal neighbors"),
    (OneOfKClue(cell=C("B2"), region=Neighbors(C("C3")), k=1, status=INNO), "Eliza is James' only innocent neighbor"),
    (OneOfKClue(cell=C("A1"), region=TRIO, k=2), "Abel is one of the 2 criminals among Abel, Eliza and James"),
    # IF_THEN: vế sau viết thường chữ đầu, trừ khi bắt đầu bằng tên nhân vật
    (IfThenClue(C("A1"), CRIM, ExactlyClue(Row(3), 0)), "If Abel is a criminal, then there are no criminals in row 3"),
    (IfThenClue(C("A1"), INNO, ExactlyClue(PAIR, 1)), "If Abel is innocent, then exactly 1 of Abel and James is a criminal"),
    (IfThenClue(C("A1"), CRIM, AtMostClue(Neighbors(C("B2")), 1)), "If Abel is a criminal, then Eliza has at most 1 criminal neighbor"),
    (IfThenClue(C("A1"), INNO, SameClue(C("B1"), C("C1"))),
     "If Abel is innocent, then Bea and Clara are the same (both criminals or both innocents)"),
])
def test_clue_describe(clue, text):
    clue.validate(BOARD)
    assert clue.describe(BOARD) == text