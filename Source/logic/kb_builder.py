"""
Dựng cơ sở tri thức tại bước suy diễn t:

    KB_t = CNF(các clue đã lộ) ∧ (unit clause cho mỗi verdict đã chứng minh)

+ Chỉ đọc từ PublicState: không nhận PuzzleFull, không thấy đáp án ẩn hay clue chưa lộ
+ Mỗi lần build tạo VariableMap mới nên đánh số biến luôn xác định
  (biến chính 1..N*N theo row-major, biến phụ nếu có được cấp sau, theo thứ tự lật thẻ)
+ Clue được mã hóa theo thứ tự lật, sau đó mới thêm các unit clause verdict
"""

from dataclasses import dataclass
from typing import Iterable, Mapping

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import Clue
from game.public_state import PublicState

from .clue_encoder import encode_clue
from .cnf import CNF
from .encoding_stats import EncodingStats, compute_stats
from .variable_map import VariableMap


@dataclass(frozen=True)
class KnowledgeBase:
    """KB_t đã mã hóa, kèm VariableMap để agent dịch ô <-> biến"""
    cnf: CNF
    vmap: VariableMap
    stats: EncodingStats
    clue_ids: tuple[str, ...]   # định danh các clue đang có trong KB_t, theo thứ tự lật
    clue_clauses: int           # số mệnh đề phân biệt từ phần CNF(clue đã lộ), sau khi bỏ trùng và tautology
    verdict_units: int          # số unit clause verdict thực sự được thêm (verdict trùng mệnh đề đã có không được tính)

    @property
    def num_vars(self) -> int:
        """Số biến cần có trong model khi gọi solver (gồm cả biến phụ)"""
        return self.vmap.max_var

    def var(self, cell: Cell) -> int:
        """Biến chính C_i của một ô"""
        return self.vmap.var(cell)

    def is_trivially_unsat(self) -> bool:
        """KB chứa mệnh đề rỗng thì chắc chắn UNSAT, không cần gọi solver"""
        return self.cnf.has_empty_clause()


def build_kb(state: PublicState) -> KnowledgeBase:
    """Dựng KB_t từ public state hiện tại"""
    if not isinstance(state, PublicState):
        raise TypeError(f"[KBBuilder]: Chỉ nhận PublicState, nhận được {type(state).__name__}")
    return encode_kb(state.board, state.revealed_clues().values(), state.verdicts(), state.active_clue_ids())


def encode_kb(board: Board, clues: Iterable[Clue], verdicts: Mapping[Cell, Status],
              clue_ids: tuple[str, ...] = ()) -> KnowledgeBase:
    """
    Mã hóa KB từ một tập clue và verdict bất kỳ
    + build_kb dùng với toàn bộ clue đã lộ của PublicState
    + Hint dùng với một phần clue để tìm tập clue tối thiểu
    """
    vmap = VariableMap(board)
    cnf = CNF()

    # CNF(clue)
    for clue in clues:
        cnf.extend(encode_clue(clue, vmap))
    clue_clauses = len(cnf)

    # Unit clause cho verdict đã chứng minh
    for cell, status in verdicts.items():
        cnf.add_clause([vmap.status_literal(cell, status)])
    verdict_units = len(cnf) - clue_clauses

    return KnowledgeBase(
        cnf=cnf,
        vmap=vmap,
        stats=compute_stats(cnf, vmap),
        clue_ids=clue_ids,
        clue_clauses=clue_clauses,
        verdict_units=verdict_units,
    )