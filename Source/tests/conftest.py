"""
Fixture dùng chung cho test engine và agent

Puzzle 2x2 nhỏ, suy luận được bằng tay:
  Đáp án: A1 CRIMINAL, B1 INNOCENT, A2 INNOCENT, B2 CRIMINAL; mở sẵn A1
  KB_0 = {C_A1, DIFFERENT(A1, B1)}  -> chỉ B1 bị ép (INNOCENT), A2 và B2 còn UNKNOWN
  Lật B1 lộ SAME(B1, A2)            -> A2 bị ép INNOCENT
  Lật A2 lộ EXACTLY 1 trong hàng 2  -> B2 bị ép CRIMINAL
"""

import copy
from typing import Any, Callable

import pytest

from game.public_state import PublicState, RevealedCard
from game.puzzle_loader import PuzzleFull, parse_puzzle

MINI_PUZZLE: dict[str, Any] = {
    "id": "test_2x2",
    "size": 2,
    "characters": {
        "A1": {"name": "Ann", "profession": "Actor"},
        "B1": {"name": "Ben", "profession": "Baker"},
        "A2": {"name": "Cal", "profession": "Chef"},
        "B2": {"name": "Dee", "profession": "Doctor"},
    },
    "solution": {"A1": "CRIMINAL", "B1": "INNOCENT", "A2": "INNOCENT", "B2": "CRIMINAL"},
    "clues": {
        "A1": {"type": "DIFFERENT", "cells": ["A1", "B1"]},
        "B1": {"type": "SAME", "cells": ["B1", "A2"]},
        "A2": {"type": "EXACTLY", "k": 1, "region": {"type": "ROW", "number": 2}},
        "B2": {"type": "FACT", "cell": "A1", "status": "CRIMINAL"},
    },
    "initially_revealed": ["A1"],
}


@pytest.fixture
def mini_data() -> dict[str, Any]:
    """Bản sao dict của puzzle 2x2, test được sửa thoải mái để tạo biến thể"""
    return copy.deepcopy(MINI_PUZZLE)


@pytest.fixture
def puzzle(mini_data: dict[str, Any]) -> PuzzleFull:
    return parse_puzzle(mini_data)


@pytest.fixture
def rig_initial_state(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[RevealedCard]], None]:
    """
    Ép mọi PuzzleFull bắt đầu từ một state tuỳ ý (không sinh được từ puzzle hợp lệ)
    để kiểm tra các nhánh phòng lỗi: KB_t UNSAT, verdict được chứng minh nhưng khác đáp án
    """
    def rig(cards: list[RevealedCard]) -> None:
        def rigged(self: PuzzleFull) -> PublicState:
            return PublicState(self.board, cards)
        monkeypatch.setattr(PuzzleFull, "initial_state", rigged)
    return rig