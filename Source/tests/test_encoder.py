"""
Với mỗi clue, duyệt mọi assignment của các biến chính và kiểm tra:
    CNF(clue) thoả được dưới assignment đó  <=>  evaluate_clue(clue) là True
CNF được tự đánh giá bằng vòng lặp thuần, không dùng DPLL nên test độc lập với solver.
Nếu encoder có biến phụ, CNF được coi là thoả khi tồn tại
một cách gán biến phụ làm thoả mọi mệnh đề.
"""

import random
from itertools import product
from typing import Iterable, Iterator

import pytest

from game.public_state import PublicState, RevealedCard
from game.puzzle_loader import PuzzleFull
from game.semantics import count_criminals
from logic.kb_builder import build_kb
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
    model = {i + 1: b for i, b in enumerate(bits)}
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


# KB_t: unit clause và thông tin ẩn
_CRIMINALS = {"A1", "B2", "C3"}  # đáp án giả định cho các test KB_t


def _solution(board: Board) -> dict[Cell, Status]:
    return {c: (Status.CRIMINAL if c.label in _CRIMINALS else Status.INNOCENT) for c in board.cells()}


def _card(board: Board, label: str, clue: Clue) -> RevealedCard:
    cell = Cell.parse(label)
    return RevealedCard(cell, _solution(board)[cell], clue)


def test_kb_empty_state(board: Board) -> None:
    kb = build_kb(PublicState.empty(board))
    assert len(kb.cnf) == 0
    assert (kb.clue_ids, kb.clue_clauses, kb.verdict_units) == ((), 0, 0)
    assert kb.num_vars == 9
    assert (kb.stats.main_vars, kb.stats.aux_vars) == (9, 0)
    assert not kb.is_trivially_unsat()


def test_kb_contains_exactly_revealed_clues_and_verdicts(board: Board) -> None:
    clue_a1 = ExactlyClue(_nb("A1"), 1)  # A1 là Criminal, C1 là Innocent
    clue_c1 = ExactlyClue(_nb("C1"), 1)
    kb = build_kb(PublicState(board, [_card(board, "A1", clue_a1), _card(board, "C1", clue_c1)]))
    a1, c1 = Cell.parse("A1"), Cell.parse("C1")

    expected = encode_clues([clue_a1, clue_c1], VariableMap(board))
    expected.add_clauses([[kb.var(a1)], [-kb.var(c1)]])
    assert set(kb.cnf.clauses) == set(expected.clauses)
    assert (kb.var(a1),) in kb.cnf.clauses      # verdict CRIMINAL: literal dương
    assert (-kb.var(c1),) in kb.cnf.clauses     # verdict INNOCENT: literal âm
    assert kb.clue_ids == ("A1", "C1")
    assert kb.verdict_units == 2
    assert kb.clue_clauses + kb.verdict_units == len(kb.cnf) == kb.stats.clauses


def test_kb_is_satisfied_by_true_solution(board: Board) -> None:
    cards = [
        _card(board, "A1", ExactlyClue(_nb("A1"), 1)),
        _card(board, "C1", ExactlyClue(_nb("C1"), 1)),
        _card(board, "B2", ExactlyClue(_nb("B2"), 2)),
    ]
    kb = build_kb(PublicState(board, cards))
    model = {board.index_of(c): s is Status.CRIMINAL for c, s in _solution(board).items()}
    assert _cnf_true(kb.cnf, model)


def test_kb_does_not_leak_hidden_status(board: Board) -> None:
    """Chỉ lộ thẻ A1: các ô ngoài vùng clue (kể cả C3 là Criminal thật) không bị KB ép buộc."""
    kb = build_kb(PublicState(board, [_card(board, "A1", ExactlyClue(_nb("A1"), 1))]))
    models = [bits for bits in _all_bits(board)
              if _cnf_true(kb.cnf, {i + 1: b for i, b in enumerate(bits)})]
    for label in ("C1", "C2", "A3", "B3", "C3"):
        idx = board.index_of(Cell.parse(label)) - 1
        assert {m[idx] for m in models} == {False, True}, label


def test_kb_counts_only_added_verdict_units(board: Board) -> None:
    """Clue FACT trùng đúng unit clause của verdict thì verdict không được đếm thêm."""
    c1 = Cell.parse("C1")
    card = RevealedCard(c1, Status.INNOCENT, FactClue(c1, Status.INNOCENT))
    kb = build_kb(PublicState(board, [card]))
    assert kb.cnf.clauses == ((-kb.var(c1),),)
    assert (kb.clue_clauses, kb.verdict_units) == (1, 0)


def test_build_kb_only_accepts_public_state(board: Board) -> None:
    sol = _solution(board)
    clues = {
        c: ExactlyClue(Neighbors(c), count_criminals(Neighbors(c).cells(board), sol))
        for c in board.cells()
    }
    full = PuzzleFull("t", board, sol, clues, (Cell.parse("A1"),))

    with pytest.raises(TypeError):
        build_kb(full)
    with pytest.raises(TypeError):
        build_kb(None)  # type: ignore[arg-type]

    # State ban đầu chỉ chứa thẻ mở sẵn, không chứa clue của 8 thẻ còn úp
    assert build_kb(full.initial_state()).clue_ids == ("A1",)