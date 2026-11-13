from itertools import product

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import (AtLeastClue, AtMostClue, DifferentClue, ExactlyClue,
                       FactClue, SameClue)
from game.region import ExplicitList, Neighbors, Row
from game.semantics import evaluate_clue
from logic.cardinality import (at_least, at_least_clause_count, at_most,
                               at_most_clause_count, exactly)
from logic.clue_encoder import encode_clue
from logic.variable_map import VariableMap
import pytest


def sat(cnf, model):
    return all(any((model[abs(l)] if l > 0 else not model[abs(l)]) for l in c) for c in cnf)


@pytest.mark.parametrize("n", range(0, 6))
def test_cardinality_bruteforce(n):
    lits = list(range(1, n + 1))
    for k in range(n + 1):
        for bits in product([False, True], repeat=n):
            model = dict(zip(lits, bits))
            cnt = sum(bits)
            assert sat(at_most(lits, k), model) == (cnt <= k)
            assert sat(at_least(lits, k), model) == (cnt >= k)
            assert sat(exactly(lits, k), model) == (cnt == k)
        assert len(at_most(lits, k)) == at_most_clause_count(n, k)
        assert len(at_least(lits, k)) == at_least_clause_count(n, k)


def _board3():
    names = "Abel Bea Clara Derek Eliza Franz Grant Hannah Ivy".split()
    data = {Cell(r, c).label: {"name": names[(r - 1) * 3 + c - 1], "profession": "X"}
            for r in range(1, 4) for c in range(1, 4)}
    return Board.from_dict(3, data)


def _clues(board):
    c = Cell
    regions = [Row(2), Neighbors(c(2, 2)), Neighbors(c(1, 1)), ExplicitList((c(1, 1), c(3, 3), c(2, 3)))]
    out = [FactClue(c(1, 1), Status.CRIMINAL), FactClue(c(2, 2), Status.INNOCENT),
           SameClue(c(1, 1), c(3, 2)), DifferentClue(c(1, 3), c(2, 1))]
    for r in regions:
        n = len(r.cells(board))
        for k in range(n + 1):
            out += [ExactlyClue(r, k), AtLeastClue(r, k), AtMostClue(r, k)]
    return out


def test_encoder_matches_semantics():
    board = _board3()
    cells = board.cells()
    for clue in _clues(board):
        vmap = VariableMap(board)
        cnf = encode_clue(clue, vmap)
        assert vmap.num_aux == 0
        for bits in product([False, True], repeat=9):
            model = {vmap.var(cell): b for cell, b in zip(cells, bits)}
            assign = {cell: (Status.CRIMINAL if b else Status.INNOCENT) for cell, b in zip(cells, bits)}
            assert sat(cnf, model) == evaluate_clue(clue, board, assign), clue


def test_invalid_clue_rejected():
    board = _board3()
    with pytest.raises(ValueError):
        encode_clue(ExactlyClue(Row(1), 4), VariableMap(board))