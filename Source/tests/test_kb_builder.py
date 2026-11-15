"""
Test KB builder: KB_t = CNF(clue đã lộ) và unit clause của verdict đã chứng minh.

Kiểm tra: verdict thành unit clause đúng dấu, KB_t chứa đúng clue đã lộ,
đáp án thật thoả KB_t, KB_t không ép các ô mà thông tin công khai chưa nói tới,
build_kb chỉ nhận PublicState (không nhận PuzzleFull).
"""

from itertools import product
from typing import Iterator

import pytest

from game.board import Board
from game.cell import Cell
from game.character import Character, Status
from game.clue import Clue, ExactlyClue, FactClue
from game.public_state import PublicState, RevealedCard
from game.puzzle_loader import PuzzleFull
from game.region import Neighbors
from game.semantics import count_criminals
from logic.clue_encoder import encode_clues
from logic.cnf import CNF
from logic.kb_builder import build_kb
from logic.variable_map import VariableMap


def _make_board(size: int) -> Board:
    cells = [Cell(r, c) for r in range(1, size + 1) for c in range(1, size + 1)]
    chars = {cell: Character(name=f"Char_{cell.label}", profession="Worker") for cell in cells}
    return Board(size, chars)


@pytest.fixture
def board() -> Board:
    """Bàn cờ 3x3 chuẩn gồm 9 nhân vật từ A1 đến C3."""
    return _make_board(3)


def _all_bits(board: Board) -> Iterator[tuple[bool, ...]]:
    return product((False, True), repeat=len(board.cells()))


def _cnf_true(cnf: CNF, model: dict[int, bool]) -> bool:
    """Mệnh đề rỗng cho False, CNF rỗng cho True."""
    return all(any(model[abs(l)] == (l > 0) for l in clause) for clause in cnf)


def _nb(label: str) -> Neighbors:
    return Neighbors(Cell.parse(label))


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