"""
Dựng cơ sở tri thức tại bước suy diễn t:

    KB_t = CNF(các clue đã lộ) ∧ (unit clause cho mỗi verdict đã chứng minh)

+ Chỉ đọc từ PublicState: không nhận PuzzleFull, không thấy đáp án ẩn hay clue chưa lộ
+ Mỗi lần build tạo VariableMap mới nên đánh số biến luôn xác định
  (biến chính 1..N*N theo row-major, biến phụ nếu có được cấp sau, theo thứ tự lật thẻ)
+ Clue được mã hóa theo thứ tự lật, sau đó mới thêm các unit clause verdict
"""

from dataclasses import dataclass

from game.cell import Cell
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
    clue_clauses: int           # số mệnh đề sinh ra từ phần CNF(clue đã lộ)
    verdict_units: int          # số verdict đã chứng minh được thêm dưới dạng unit clause

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

    vmap = VariableMap(state.board)
    cnf = CNF()

    # CNF(clue đã lộ)
    for clue in state.revealed_clues().values():
        cnf.extend(encode_clue(clue, vmap))
    clue_clauses = len(cnf)

    # Unit clause cho verdict đã chứng minh
    verdicts = state.verdicts()
    for cell, status in verdicts.items():
        cnf.add_clause([vmap.status_literal(cell, status)])

    return KnowledgeBase(
        cnf=cnf,
        vmap=vmap,
        stats=compute_stats(cnf, vmap),
        clue_ids=state.active_clue_ids(),
        clue_clauses=clue_clauses,
        verdict_units=len(verdicts),
    )