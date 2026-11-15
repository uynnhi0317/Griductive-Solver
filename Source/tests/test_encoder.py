"""
Test clue encoder: đối chiếu CNF với semantic evaluator.

Với mỗi clue, duyệt mọi assignment của các biến chính và kiểm tra:
    CNF(clue) thoả được dưới assignment đó  <=>  evaluate_clue(clue) là True
CNF được tự đánh giá bằng vòng lặp thuần, không dùng DPLL nên test độc lập với solver.
Nếu encoder có biến phụ, CNF được coi là thoả khi tồn tại một cách gán biến phụ làm thoả mọi mệnh đề.
"""

import random
from itertools import product
from typing import Iterable, Iterator

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
from game.region import Column, ExplicitList, Neighbors, Region, Row
from game.semantics import evaluate_clue, evaluate_clues
from logic.cardinality import (
    at_least_clause_count,
    at_most_clause_count,
    exactly_clause_count,
)
from logic.clue_encoder import encode_clue, encode_clues
from logic.cnf import CNF
from logic.variable_map import VariableMap


def _make_board(size: int) -> Board:
    cells = [Cell(r, c) for r in range(1, size + 1) for c in range(1, size + 1)]
    chars = {cell: Character(name=f"Char_{cell.label}", profession="Worker") for cell in cells}
    return Board(size, chars)


@pytest.fixture
def board() -> Board:
    """Bàn cờ 3x3 chuẩn gồm 9 nhân vật từ A1 đến C3."""
    return _make_board(3)


def _assignment(board: Board, bits: Iterable[bool]) -> dict[Cell, Status]:
    return {
        cell: (Status.CRIMINAL if b else Status.INNOCENT)
        for cell, b in zip(board.cells(), bits)
    }


def _all_bits(board: Board) -> Iterator[tuple[bool, ...]]:
    return product((False, True), repeat=len(board.cells()))


def _random_bits(board: Board, count: int, seed: int) -> Iterator[tuple[bool, ...]]:
    rng = random.Random(seed)
    n = len(board.cells())
    for _ in range(count):
        yield tuple(rng.random() < 0.5 for _ in range(n))


def _cnf_true(cnf: CNF, model: dict[int, bool]) -> bool:
    """Mệnh đề rỗng cho False, CNF rỗng cho True."""
    return all(any(model[abs(l)] == (l > 0) for l in clause) for clause in cnf)


def _satisfiable_under(cnf: CNF, vmap: VariableMap, bits: tuple[bool, ...]) -> bool:
    """CNF thoả khi biến chính nhận `bits` (row-major), biến phụ được chọn tuỳ ý."""
    model = {vmap.var(c): b for c, b in zip(vmap.board.cells(), bits)}
    aux = vmap.aux_vars()
    for aux_bits in product((False, True), repeat=len(aux)):
        model.update(zip(aux, aux_bits))
        if _cnf_true(cnf, model):
            return True
    return False


def _assert_equivalent(clue: Clue, board: Board, all_bits: Iterable[tuple[bool, ...]]) -> None:
    vmap = VariableMap(board)
    cnf = encode_clue(clue, vmap)
    for bits in all_bits:
        expected = evaluate_clue(clue, board, _assignment(board, bits))
        actual = _satisfiable_under(cnf, vmap, bits)
        criminals = [c.label for c, b in zip(board.cells(), bits) if b]
        assert actual == expected, (
            f"{clue.to_dict()}: evaluator={expected}, CNF={actual}, criminals={criminals}"
        )


def _row(i: int) -> Row:
    return Row(i)


def _col(letter: str) -> Column:
    return Column(letter)


def _nb(label: str) -> Neighbors:
    return Neighbors(Cell.parse(label))


def _explicit(*lbls: str) -> ExplicitList:
    return ExplicitList(tuple(Cell.parse(lbl) for lbl in lbls))


REGIONS: dict[str, Region] = {
    "row": _row(2),
    "column": _col("B"),
    "neighbors_corner": _nb("A1"),  # 3 ô
    "neighbors_edge": _nb("B1"),    # 5 ô
    "neighbors_center": _nb("B2"),  # 8 ô
    "explicit": _explicit("A1", "B2", "C3", "A3"),
    "explicit_single": _explicit("B2"),  # 1 ô
}

COUNT_CLUES = [ExactlyClue, AtLeastClue, AtMostClue]


# Encoder <=> evaluator: từng template, duyệt hết 512 assignment của 3x3
@pytest.mark.parametrize("label,status", [
    ("A1", Status.CRIMINAL), ("A1", Status.INNOCENT),
    ("B2", Status.CRIMINAL), ("C3", Status.INNOCENT),
])
def test_fact_matches_evaluator(board: Board, label: str, status: Status) -> None:
    _assert_equivalent(FactClue(Cell.parse(label), status), board, _all_bits(board))


@pytest.mark.parametrize("pair", [("A1", "C3"), ("B1", "B2"), ("A1", "B2"), ("C1", "A3")])
@pytest.mark.parametrize("clue_cls", [SameClue, DifferentClue])
def test_pair_clues_match_evaluator(board: Board, clue_cls: type, pair: tuple[str, str]) -> None:
    clue = clue_cls(Cell.parse(pair[0]), Cell.parse(pair[1]))
    _assert_equivalent(clue, board, _all_bits(board))


@pytest.mark.parametrize("name", list(REGIONS))
@pytest.mark.parametrize("clue_cls", COUNT_CLUES)
def test_counting_clues_match_evaluator_all_k(board: Board, name: str, clue_cls: type) -> None:
    """Mọi k từ 0 đến |R|, gồm các ca biên k = 0 và k = |R|."""
    region = REGIONS[name]
    for k in range(len(region.cells(board)) + 1):
        _assert_equivalent(clue_cls(region, k), board, _all_bits(board))


# Bàn lớn hơn: lấy mẫu ngẫu nhiên (seed cố định) vì duyệt hết quá chậm
@pytest.mark.parametrize("size,clue", [
    pytest.param(4, ExactlyClue(_nb("B2"), 3), id="4x4-EXACTLY-nbr-B2"),
    pytest.param(4, AtLeastClue(_nb("C3"), 2), id="4x4-AT_LEAST-nbr-C3"),
    pytest.param(4, AtMostClue(_col("D"), 1), id="4x4-AT_MOST-colD"),
    pytest.param(4, ExactlyClue(_row(1), 4), id="4x4-EXACTLY-row1-full"),
    pytest.param(5, ExactlyClue(_nb("C3"), 4), id="5x5-EXACTLY-nbr-C3"),
    pytest.param(5, AtMostClue(_nb("E5"), 0), id="5x5-AT_MOST-nbr-E5-k0"),
    pytest.param(5, DifferentClue(Cell.parse("A1"), Cell.parse("E5")), id="5x5-DIFFERENT"),
])
def test_matches_evaluator_random_larger_boards(size: int, clue: Clue) -> None:
    b = _make_board(size)
    _assert_equivalent(clue, b, _random_bits(b, 3000, seed=size * 1000 + 7))


# Nhiều clue cùng lúc
def test_encode_clues_is_conjunction(board: Board) -> None:
    clue_sets = [
        [ExactlyClue(_row(1), 1), SameClue(Cell.parse("A1"), Cell.parse("B1")), AtMostClue(_col("C"), 1)],
        [FactClue(Cell.parse("B2"), Status.CRIMINAL), ExactlyClue(_nb("B2"), 2)],
        [AtLeastClue(_row(3), 2), DifferentClue(Cell.parse("A3"), Cell.parse("C3")), AtMostClue(_row(3), 2)],
    ]
    for clues in clue_sets:
        vmap = VariableMap(board)
        cnf = encode_clues(clues, vmap)
        for bits in _all_bits(board):
            expected = evaluate_clues(clues, board, _assignment(board, bits))
            assert _satisfiable_under(cnf, vmap, bits) == expected


def test_encode_clues_empty_is_always_true(board: Board) -> None:
    vmap = VariableMap(board)
    cnf = encode_clues([], vmap)
    assert len(cnf) == 0
    assert all(_satisfiable_under(cnf, vmap, bits) for bits in _all_bits(board))


# Unit clause và literal
@pytest.mark.parametrize("label", ["A1", "B2", "C3"])
@pytest.mark.parametrize("status,sign", [(Status.CRIMINAL, +1), (Status.INNOCENT, -1)])
def test_fact_is_single_unit_clause_with_correct_sign(
    board: Board, label: str, status: Status, sign: int
) -> None:
    c = Cell.parse(label)
    cnf = encode_clue(FactClue(c, status), VariableMap(board))
    assert cnf.clauses == ((sign * board.index_of(c),),)


def test_fact_encoding_matches_status_literal(board: Board) -> None:
    vmap = VariableMap(board)
    for c in board.cells():
        for status in Status:
            cnf = encode_clue(FactClue(c, status), vmap)
            assert cnf.clauses == ((vmap.status_literal(c, status),),)


# Biến phụ và số mệnh đề
@pytest.mark.parametrize("name", list(REGIONS))
def test_core_templates_use_only_main_variables(board: Board, name: str) -> None:
    clues = [FactClue(Cell.parse("A1"), Status.CRIMINAL),
             SameClue(Cell.parse("A1"), Cell.parse("B2")),
             DifferentClue(Cell.parse("A1"), Cell.parse("B2")),
             *(cls(REGIONS[name], 1) for cls in COUNT_CLUES)]
    for clue in clues:
        vmap = VariableMap(board)
        cnf = encode_clue(clue, vmap)
        assert vmap.num_aux == 0
        assert all(vmap.is_main(v) for v in cnf.variables())


@pytest.mark.parametrize("name", list(REGIONS))
def test_counting_clause_counts_match_formulas(board: Board, name: str) -> None:
    region = REGIONS[name]
    n = len(region.cells(board))
    for k in range(n + 1):
        assert len(encode_clue(AtMostClue(region, k), VariableMap(board))) == at_most_clause_count(n, k)
        assert len(encode_clue(AtLeastClue(region, k), VariableMap(board))) == at_least_clause_count(n, k)
        assert len(encode_clue(ExactlyClue(region, k), VariableMap(board))) == exactly_clause_count(n, k)


def test_trivially_true_counting_clues_give_empty_cnf(board: Board) -> None:
    """AT_LEAST 0 và AT_MOST |R| luôn đúng nên CNF rỗng, không phải UNSAT."""
    for clue in (AtLeastClue(_row(1), 0), AtMostClue(_row(1), 3)):
        cnf = encode_clue(clue, VariableMap(board))
        assert len(cnf) == 0
        assert not cnf.has_empty_clause()


# Validate trước khi mã hoá
@pytest.mark.parametrize("clue", [
    pytest.param(ExactlyClue(_row(1), 4), id="k>|R|-row"),
    pytest.param(AtLeastClue(_nb("A1"), 4), id="k>|R|-neighbors-corner"),
    pytest.param(AtMostClue(_explicit("A1", "B1"), 3), id="k>|R|-explicit"),
    pytest.param(ExactlyClue(_row(5), 1), id="row-outside"),
    pytest.param(AtLeastClue(_col("D"), 1), id="column-outside"),
    pytest.param(FactClue(Cell(4, 4), Status.CRIMINAL), id="FACT-outside"),
    pytest.param(SameClue(Cell.parse("A1"), Cell(4, 4)), id="SAME-outside"),
    pytest.param(DifferentClue(Cell(4, 1), Cell.parse("A1")), id="DIFFERENT-outside"),
    pytest.param(ExactlyClue(_explicit("A1", "D4"), 1), id="explicit-outside"),
])
def test_invalid_clue_rejected(board: Board, clue: Clue) -> None:
    with pytest.raises(ValueError):
        encode_clue(clue, VariableMap(board))


def test_non_clue_rejected(board: Board) -> None:
    with pytest.raises(TypeError):
        encode_clue("EXACTLY", VariableMap(board))  # type: ignore[arg-type]


def test_invalid_clue_in_batch_rejected(board: Board) -> None:
    clues = [FactClue(Cell.parse("A1"), Status.CRIMINAL), ExactlyClue(_row(1), 9)]
    with pytest.raises(ValueError):
        encode_clues(clues, VariableMap(board))


# Số mệnh đề của vùng một ô
@pytest.mark.parametrize("clue_cls,k,sign", [
    (ExactlyClue, 0, -1), (ExactlyClue, 1, +1),
    (AtLeastClue, 0, 0), (AtLeastClue, 1, +1),
    (AtMostClue, 0, -1), (AtMostClue, 1, 0),   # sign 0: không sinh mệnh đề nào
])
def test_single_cell_region_clauses(board: Board, clue_cls: type, k: int, sign: int) -> None:
    v = board.index_of(Cell.parse("B2"))
    cnf = encode_clue(clue_cls(_explicit("B2"), k), VariableMap(board))
    expected = ((sign * v,),) if sign else ()
    assert cnf.clauses == expected


def test_single_cell_exactly_matches_fact(board: Board) -> None:
    """EXACTLY(1, {c}) cùng dạng với FACT Criminal, EXACTLY(0, {c}) cùng dạng với FACT Innocent."""
    c = Cell.parse("B2")
    for k, status in ((1, Status.CRIMINAL), (0, Status.INNOCENT)):
        region_cnf = encode_clue(ExactlyClue(_explicit("B2"), k), VariableMap(board))
        fact_cnf = encode_clue(FactClue(c, status), VariableMap(board))
        assert region_cnf.clauses == fact_cnf.clauses



# Số mệnh đề của SAME và DIFFERENT
PAIRS = [("A1", "C3"), ("B1", "B2"), ("A1", "B2"), ("C1", "A3"), ("B2", "A1")]


@pytest.mark.parametrize("pair", PAIRS)
@pytest.mark.parametrize("clue_cls,make_expected", [
    (SameClue, lambda a, b: {frozenset({-a, b}), frozenset({a, -b})}),
    (DifferentClue, lambda a, b: {frozenset({a, b}), frozenset({-a, -b})}),
])
def test_pair_clue_has_exactly_two_clauses(
    board: Board, clue_cls: type, make_expected, pair: tuple[str, str]
) -> None:
    a, b = Cell.parse(pair[0]), Cell.parse(pair[1])
    vmap = VariableMap(board)
    cnf = encode_clue(clue_cls(a, b), vmap)
    assert len(cnf) == 2
    assert {frozenset(c) for c in cnf} == make_expected(vmap.var(a), vmap.var(b))
    assert (cnf.tautologies_skipped, cnf.duplicates_skipped) == (0, 0)
    assert vmap.num_aux == 0