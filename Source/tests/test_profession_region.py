"""
Test vùng theo nghề: ExplicitList(profession=...) gồm mọi nhân vật làm nghề đó trên board.

Bàn 3x3 dùng trong test (nghề lặp lại):
    A1 Cop     B1 Doctor  C1 Cop
    A2 Guard   B2 Cop     C2 Doctor
    A3 Guard   B3 Chef    C3 Guard
"""

from itertools import product

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import (
    AtLeastClue,
    AtMostClue,
    ExactlyClue,
    IfThenClue,
    NoAdjacentClue,
    OneOfKClue,
    ParityClue,
    clue_from_dict,
)
from game.region import ExplicitList, region_from_dict
from game.semantics import evaluate_clue
from logic.clue_encoder import encode_clue
from logic.variable_map import VariableMap

C = Cell.parse
CRIM, INNO = Status.CRIMINAL, Status.INNOCENT

_LAYOUT = {
    "A1": ("Ann", "Cop"), "B1": ("Ben", "Doctor"), "C1": ("Cid", "Cop"),
    "A2": ("Dee", "Guard"), "B2": ("Eli", "Cop"), "C2": ("Fay", "Doctor"),
    "A3": ("Gus", "Guard"), "B3": ("Hal", "Chef"), "C3": ("Ivo", "Guard"),
}
BOARD = Board.from_dict(3, {k: {"name": n, "profession": p} for k, (n, p) in _LAYOUT.items()})
CELLS = BOARD.cells()

COPS = ExplicitList(profession="Cop")          # A1, C1, B2
DOCTORS = ExplicitList(profession="doctor")    # B1, C2 (khác hoa thường vẫn khớp)
GUARDS = ExplicitList(profession="Guard")      # A2, A3, C3
CHEF = ExplicitList(profession="Chef")         # B3
POLICE = ExplicitList(profession="Cop", plural="Police")


def _labels(cells):
    return [c.label for c in cells]


def _projected_sat(cnf, vmap: VariableMap, assignment) -> bool:
    """CNF thoả được với biến chính cố định theo assignment (vét cạn biến phụ)"""
    base = {vmap.var(c): assignment[c] is CRIM for c in CELLS}
    aux = vmap.aux_vars()
    for bits in product((False, True), repeat=len(aux)):
        model = {**base, **dict(zip(aux, bits))}
        if all(any(model[abs(l)] == (l > 0) for l in cl) for cl in cnf):
            return True
    return False


# Chọn ô theo nghề
def test_cells_with_profession_is_case_insensitive_and_row_major():
    assert _labels(BOARD.cells_with_profession("  cOP ")) == ["A1", "C1", "B2"]
    assert BOARD.cells_with_profession("Pilot") == ()


@pytest.mark.parametrize("region, expected", [
    (COPS, ["A1", "C1", "B2"]),
    (DOCTORS, ["B1", "C2"]),
    (GUARDS, ["A2", "A3", "C3"]),
    (CHEF, ["B3"]),
])
def test_region_cells(region, expected):
    assert _labels(region.cells(BOARD)) == expected


def test_unknown_profession_rejected_on_board():
    with pytest.raises(ValueError):
        ExplicitList(profession="Pilot").cells(BOARD)
    with pytest.raises(ValueError):
        ExactlyClue(ExplicitList(profession="Pilot"), 0).validate(BOARD)


def test_k_bounded_by_group_size():
    ExactlyClue(DOCTORS, 2).validate(BOARD)
    with pytest.raises(ValueError):
        ExactlyClue(DOCTORS, 3).validate(BOARD)


@pytest.mark.parametrize("make", [
    lambda: ExplicitList(),                                             # không có gì
    lambda: ExplicitList((C("A1"),), profession="Cop"),                 # cả hai
    lambda: ExplicitList(profession="   "),                             # nghề rỗng
    lambda: ExplicitList(profession=3),                                 # không phải chuỗi
    lambda: ExplicitList((C("A1"),), plural="Cops"),                    # plural không kèm nghề
    lambda: ExplicitList(profession="Cop", plural=""),                  # plural rỗng
])
def test_invalid_construction(make):
    with pytest.raises(ValueError):
        make()


# JSON
@pytest.mark.parametrize("region", [COPS, DOCTORS, POLICE, ExplicitList((C("A1"), C("C3")))])
def test_region_roundtrip(region):
    assert region_from_dict(region.to_dict()) == region


def test_region_dict_format():
    assert COPS.to_dict() == {"type": "CELLS", "profession": "Cop"}
    assert POLICE.to_dict() == {"type": "CELLS", "profession": "Cop", "plural": "Police"}


@pytest.mark.parametrize("data", [
    {"type": "CELLS"},
    {"type": "CELLS", "cells": ["A1"], "profession": "Cop"},
    {"type": "CELLS", "cells": ["A1"], "plural": "Cops"},
    {"type": "CELLS", "profession": ""},
])
def test_region_from_dict_errors(data):
    with pytest.raises(ValueError):
        region_from_dict(data)


def test_clue_with_profession_region_from_json():
    clue = clue_from_dict({"type": "EXACTLY", "k": 1, "region": {"type": "CELLS", "profession": "Cop"}})
    assert clue == ExactlyClue(COPS, 1)
    assert clue.referenced_cells(BOARD) == tuple(C(x) for x in ("A1", "C1", "B2"))


# Encoder <=> evaluator trên mọi 512 phép gán
GROUP_CLUES = [
    *(cls(region, k) for cls in (ExactlyClue, AtLeastClue, AtMostClue)
      for region in (COPS, DOCTORS, CHEF) for k in range(len(region.cells(BOARD)) + 1)),
    ParityClue(GUARDS, "ODD"),
    ParityClue(COPS, "EVEN", status=INNO),
    NoAdjacentClue(COPS),                                   # cặp kề: A1-B2, C1-B2
    NoAdjacentClue(GUARDS, status=INNO),                    # cặp kề: A2-A3
    OneOfKClue(cell=C("B2"), region=COPS, k=2),
    OneOfKClue(cell=C("B1"), region=DOCTORS, k=1, status=INNO),
    IfThenClue(C("B3"), CRIM, ExactlyClue(GUARDS, 1)),
    IfThenClue(C("A1"), INNO, ParityClue(DOCTORS, "ODD")),
]


@pytest.mark.parametrize("clue", GROUP_CLUES, ids=lambda c: c.describe(BOARD))
def test_encoder_matches_semantics(clue):
    vmap = VariableMap(BOARD)
    cnf = encode_clue(clue, vmap)
    for bits in product((False, True), repeat=len(CELLS)):
        assignment = {c: CRIM if b else INNO for c, b in zip(CELLS, bits)}
        assert _projected_sat(cnf, vmap, assignment) == evaluate_clue(clue, BOARD, assignment)


def test_no_adjacent_pairs_follow_board_positions():
    with pytest.raises(ValueError):          # nhóm 1 người: không có cặp kề nào
        NoAdjacentClue(CHEF).validate(BOARD)
    NoAdjacentClue(DOCTORS).validate(BOARD)  # B1 và C2 kề chéo nên hợp lệ


# Câu hiển thị
@pytest.mark.parametrize("clue, text", [
    (ExactlyClue(COPS, 1), "Exactly 1 of the 3 Cops is a criminal"),
    (ExactlyClue(COPS, 2), "Exactly 2 of the 3 Cops are criminals"),
    (ExactlyClue(COPS, 0), "None of the Cops are criminals"),
    (AtLeastClue(COPS, 3), "All Cops are criminals"),
    (ExactlyClue(DOCTORS, 2), "Both Doctors are criminals"),
    (AtMostClue(GUARDS, 1), "At most 1 of the 3 Guards is a criminal"),
    (ExactlyClue(CHEF, 1), "The Chef is a criminal"),
    (ExactlyClue(CHEF, 0), "The Chef is innocent"),
    (ExactlyClue(POLICE, 1), "Exactly 1 of the 3 Police is a criminal"),
    (ParityClue(GUARDS, "ODD"), "An odd number of the Guards are criminals"),
    (ParityClue(COPS, "EVEN", status=INNO), "An even number of the Cops are innocent"),
    (ParityClue(CHEF, "ODD"), "The Chef is a criminal"),
    (NoAdjacentClue(COPS), "No two criminals among the Cops are next to each other"),
    (OneOfKClue(cell=C("C2"), region=DOCTORS, k=1), "Fay is the only criminal Doctor"),
    (OneOfKClue(cell=C("B2"), region=COPS, k=2, status=INNO), "Eli is one of the 2 innocent Cops"),
    (IfThenClue(C("B3"), CRIM, ExactlyClue(GUARDS, 1)),
     "If Hal is a criminal, exactly 1 of the 3 Guards is a criminal"),
    (IfThenClue(C("A1"), INNO, ExactlyClue(CHEF, 0)), "If Ann is innocent, the Chef is innocent"),
])
def test_describe(clue, text):
    clue.validate(BOARD)
    assert clue.describe(BOARD) == text


def test_region_describe():
    assert COPS.describe(BOARD) == "the Cops"
    assert DOCTORS.describe(BOARD) == "the Doctors"   # viết theo thẻ, không theo JSON
    assert COPS.describe() == "profession Cop"
