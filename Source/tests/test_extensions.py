"""
Test cho 5 clue mở rộng (T10): PARITY, CONNECTED, NO_ADJACENT, ONE_OF_K, IF_THEN
(4 clue đầu có biến thể status = CRIMINAL / INNOCENT)

Kiểm tra chính: với MỌI phép gán trên bàn 3x3 (512 phép gán), CNF của clue thỏa được
(tồn tại giá trị cho biến phụ) khi và chỉ khi semantic evaluator trả True.
Phép chiếu lên biến chính được kiểm bằng vét cạn biến phụ, không phụ thuộc DPLL.
"""

from itertools import product

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import (
    ConnectedClue,
    ExactlyClue,
    FactClue,
    IfThenClue,
    NoAdjacentClue,
    OneOfKClue,
    ParityClue,
    SameClue,
    clue_from_dict,
)
from game.region import Column, ExplicitList, Neighbors, Row
from game.semantics import evaluate_clue
from logic.clue_encoder import encode_clue
from logic.variable_map import VariableMap

C = Cell.parse
CRIM, INNO = Status.CRIMINAL, Status.INNOCENT


def _board3() -> Board:
    names = "Abel Bea Clara Derek Eliza Franz Grant Hannah Ivy".split()
    data = {Cell(r, c).label: {"name": names[(r - 1) * 3 + c - 1], "profession": "X"}
            for r in range(1, 4) for c in range(1, 4)}
    return Board.from_dict(3, data)


BOARD = _board3()
CELLS = BOARD.cells()
ALL_ASSIGNMENTS = [dict(zip(CELLS, (CRIM if b else INNO for b in bits)))
                   for bits in product([False, True], repeat=len(CELLS))]


def _clause_sat(clause, model) -> bool:
    return any(model[abs(l)] == (l > 0) for l in clause)


def _projected_sat(cnf, vmap: VariableMap, assignment) -> bool:
    """CNF thỏa được với biến chính cố định theo assignment (vét cạn biến phụ)"""
    base = {vmap.var(c): assignment[c] is CRIM for c in CELLS}
    aux = vmap.aux_vars()
    for bits in product([False, True], repeat=len(aux)):
        model = {**base, **dict(zip(aux, bits))}
        if all(_clause_sat(cl, model) for cl in cnf):
            return True
    return False


EXT_CLUES = [
    # PARITY trên đủ 4 loại region, vùng 2..8 ô
    ParityClue(Row(1), "ODD"),
    ParityClue(Row(2), "EVEN"),
    ParityClue(Column("C"), "ODD"),
    ParityClue(Neighbors(C("B2")), "ODD"),     # 8 ô -> 6 biến phụ
    ParityClue(Neighbors(C("A1")), "EVEN"),    # góc, 3 ô
    ParityClue(ExplicitList((C("A1"), C("C3"))), "ODD"),
    ParityClue(ExplicitList((C("B2"),)), "EVEN"),
    ParityClue(Row(1), "ODD", status=INNO),
    ParityClue(Neighbors(C("B2")), "EVEN", status=INNO),
    ParityClue(ExplicitList((C("B2"),)), "ODD", status=INNO),
    # CONNECTED
    ConnectedClue(Row(1)),
    ConnectedClue(Column("B")),
    ConnectedClue(Row(2), status=INNO),
    ConnectedClue(Column("C"), status=INNO),
    # NO_ADJACENT
    NoAdjacentClue(Row(3)),
    NoAdjacentClue(Neighbors(C("B2"))),
    NoAdjacentClue(ExplicitList((C("A1"), C("B2"), C("C3")))),
    NoAdjacentClue(Row(1), status=INNO),
    NoAdjacentClue(Neighbors(C("B2")), status=INNO),
    # ONE_OF_K
    OneOfKClue(cell=C("B1"), region=Row(1), k=1),
    OneOfKClue(cell=C("B2"), region=Column("B"), k=2),
    OneOfKClue(cell=C("A2"), region=Neighbors(C("B2")), k=3),
    OneOfKClue(cell=C("A3"), region=Row(3), k=2, status=INNO),
    OneOfKClue(cell=C("B2"), region=Neighbors(C("A1")), k=1, status=INNO),
    # IF_THEN, vế sau là clue lõi lẫn clue mở rộng (kể cả clue có biến phụ và IF_THEN lồng)
    IfThenClue(C("A1"), CRIM, ExactlyClue(Row(3), 2)),
    IfThenClue(C("C3"), INNO, SameClue(C("A1"), C("B1"))),
    IfThenClue(C("B2"), CRIM, FactClue(C("B2"), INNO)),            # vế sau mâu thuẫn -> ép B2 vô tội
    IfThenClue(C("A2"), CRIM, ParityClue(Neighbors(C("B2")), "EVEN")),
    IfThenClue(C("C1"), INNO, ConnectedClue(Column("A"))),
    IfThenClue(C("B3"), CRIM, IfThenClue(C("A3"), CRIM, NoAdjacentClue(Row(2)))),
    IfThenClue(C("C2"), CRIM, OneOfKClue(cell=C("C2"), region=Column("C"), k=2)),
    IfThenClue(C("A1"), INNO, ParityClue(Column("B"), "ODD", status=INNO)),
]


@pytest.mark.parametrize("clue", EXT_CLUES, ids=lambda c: c.describe(BOARD))
def test_encoder_matches_semantics(clue):
    vmap = VariableMap(BOARD)
    cnf = encode_clue(clue, vmap)
    for assignment in ALL_ASSIGNMENTS:
        assert _projected_sat(cnf, vmap, assignment) == evaluate_clue(clue, BOARD, assignment), \
            {c.label: s.value for c, s in assignment.items()}


@pytest.mark.parametrize("clue", EXT_CLUES, ids=lambda c: c.kind)
def test_dict_roundtrip(clue):
    assert clue_from_dict(clue.to_dict()) == clue


@pytest.mark.parametrize("n_region, expected_aux, expected_clauses", [
    (Row(1), 1, 6),                    # n = 3: n-2 biến phụ, 4(n-2)+2 mệnh đề
    (Neighbors(C("B2")), 6, 26),       # n = 8
    (ExplicitList((C("A1"), C("C3"))), 0, 2),
    (ExplicitList((C("B2"),)), 0, 1),
])
@pytest.mark.parametrize("status", [CRIM, INNO])
def test_parity_aux_and_size(n_region, expected_aux, expected_clauses, status):
    vmap = VariableMap(BOARD)
    cnf = encode_clue(ParityClue(n_region, "ODD", status=status), vmap)
    assert vmap.num_aux == expected_aux
    assert len(cnf) == expected_clauses
    assert all(vmap.is_aux(v) for v in range(vmap.num_main + 1, cnf.max_var() + 1))


def test_core_clues_use_no_aux():
    vmap = VariableMap(BOARD)
    for clue in (ConnectedClue(Row(1)), NoAdjacentClue(Row(1), status=INNO), OneOfKClue(cell=C("A1"), region=Row(1), k=2, status=INNO)):
        encode_clue(clue, vmap)
    assert vmap.num_aux == 0


def test_connected_and_no_adjacent_sizes():
    vmap = VariableMap(BOARD)
    assert len(encode_clue(ConnectedClue(Row(1)), vmap)) == 1           # C(3, 3)
    assert len(encode_clue(NoAdjacentClue(Row(1)), vmap)) == 2          # A1-B1, B1-C1
    assert len(encode_clue(NoAdjacentClue(Neighbors(C("B2"))), vmap)) == 12


def test_referenced_cells():
    assert OneOfKClue(cell=C("B1"), region=Row(1), k=1).referenced_cells(BOARD) == (C("A1"), C("B1"), C("C1"))
    clue = IfThenClue(C("C3"), CRIM, ExactlyClue(Row(1), 1))
    assert clue.referenced_cells(BOARD) == tuple(sorted((C("A1"), C("B1"), C("C1"), C("C3"))))


@pytest.mark.parametrize("make", [
    lambda: ParityClue(Row(1), "odd"),
    lambda: ConnectedClue(Neighbors(C("B2"))),
    lambda: ConnectedClue(ExplicitList((C("A1"), C("B1")))),
    lambda: OneOfKClue(cell=C("A1"), region=Row(1), k=0),
    lambda: OneOfKClue(cell=C("A1"), region=Row(1), k=True),
    lambda: IfThenClue(C("A1"), "CRIMINAL", FactClue(C("B1"), CRIM)),
    lambda: IfThenClue(C("A1"), CRIM, "not a clue"),
    lambda: ParityClue(Row(1), "ODD", status="INNOCENT"),
    lambda: NoAdjacentClue(Row(1), status=None),
])
def test_invalid_construction(make):
    with pytest.raises(ValueError):
        make()


@pytest.mark.parametrize("clue", [
    OneOfKClue(cell=C("A1"), region=Row(2), k=1),                                # ô không thuộc vùng
    OneOfKClue(cell=C("A1"), region=Row(1), k=4),                                # k > |R|
    ConnectedClue(Row(4)),                                                       # hàng ngoài board
    NoAdjacentClue(ExplicitList((C("A1"), C("C3")))),                            # không có cặp kề
    IfThenClue(C("A1"), CRIM, OneOfKClue(cell=C("A1"), region=Row(2), k=1)),     # vế sau sai
])
def test_invalid_against_board(clue):
    with pytest.raises(ValueError):
        clue.validate(BOARD)


@pytest.mark.parametrize("data", [
    {"type": "PARITY", "parity": "ODD", "region": {"type": "ROW", "number": 1}},
    {"type": "CONNECTED", "region": {"type": "ROW", "number": 1}},
    {"type": "NO_ADJACENT", "region": {"type": "ROW", "number": 1}},
    {"type": "ONE_OF_K", "cell": "A1", "k": 1, "region": {"type": "ROW", "number": 1}},
], ids=lambda d: d["type"])
def test_status_defaults_to_criminal(data):
    clue = clue_from_dict(data)
    assert clue.status is CRIM
    assert clue.to_dict()["status"] == "CRIMINAL"


@pytest.mark.parametrize("data", [
    {"type": "PARITY", "region": {"type": "ROW", "number": 1}},
    {"type": "ONE_OF_K", "cell": "A1", "region": {"type": "ROW", "number": 1}},
    {"type": "IF_THEN", "cell": "A1", "status": "CRIMINAL"},
    {"type": "IF_THEN", "cell": "A1", "status": "GUILTY", "then": {"type": "FACT", "cell": "B1", "status": "CRIMINAL"}},
    {"type": "IF_THEN", "cell": "A1", "status": "CRIMINAL", "then": "FACT"},
    {"type": "CONNECTED", "status": "GUILTY", "region": {"type": "ROW", "number": 1}},
])
def test_from_dict_errors(data):
    with pytest.raises(ValueError):
        clue_from_dict(data)


def test_showcase_puzzle_uses_all_extensions():
    from pathlib import Path
    from game.puzzle_loader import load_puzzle
    path = Path(__file__).resolve().parent.parent / "puzzles" / "3x3" / "3x3_03.json"
    puzzle = load_puzzle(path)   # loader đã kiểm tra mọi clue đúng với đáp án
    kinds = {clue.kind for clue in puzzle.clues.values()}
    assert {"PARITY", "CONNECTED", "NO_ADJACENT", "ONE_OF_K", "IF_THEN"} <= kinds