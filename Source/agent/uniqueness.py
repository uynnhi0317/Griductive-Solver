"""
Kiểm tra tính duy nhất nghiệm của bộ clue đầy đủ (tách riêng khỏi vòng suy diễn của agent)

Cách làm:
+ Mã hóa toàn bộ clue của puzzle (kể cả thẻ chưa lật) thành CNF, cộng unit clause cho status của
  các thẻ mở sẵn (public knowledge); status của thẻ úp không được dùng
+ Giải lần 1: UNSAT -> NO_SOLUTION; SAT -> lấy một mô hình
+ Thêm mệnh đề chặn mô hình đó (chỉ trên biến chính C_i, biến phụ không tính là một nghiệm khác)
  rồi giải lần 2: UNSAT -> UNIQUE; SAT -> MULTIPLE kèm nghiệm thứ hai làm phản chứng
+ Timeout không bị loại bỏ mà được ghi nhận bằng trạng thái TIMEOUT kèm số liệu tính đến lúc dừng
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from game.board import Board
from game.cell import Cell
from game.character import Status
from game.clue import Clue
from game.puzzle_loader import PuzzleFull
from logic.clue_encoder import encode_clues
from logic.cnf import CNF
from logic.encoding_stats import EncodingStats, compute_stats
from logic.variable_map import VariableMap
from solver.dpll import SolverTimeout, solve
from solver.stats import SolverStats


class UniquenessStatus(Enum):
    UNIQUE = "UNIQUE"              # đúng một nghiệm
    MULTIPLE = "MULTIPLE"          # từ hai nghiệm trở lên (ambiguous)
    NO_SOLUTION = "NO_SOLUTION"    # bộ clue mâu thuẫn
    TIMEOUT = "TIMEOUT"            # vượt time_limit


@dataclass(frozen=True)
class UniquenessResult:
    status: UniquenessStatus
    solution: dict[Cell, Status] | None          # một nghiệm tìm được (None nếu NO_SOLUTION / TIMEOUT ở lần 1)
    second_solution: dict[Cell, Status] | None   # nghiệm khác, chỉ có khi MULTIPLE
    sat_calls: int
    stats: SolverStats                           # cộng dồn mọi lần gọi solver
    encoding: EncodingStats

    @property
    def is_unique(self) -> bool:
        return self.status is UniquenessStatus.UNIQUE

    def differing_cells(self) -> tuple[Cell, ...]:
        """Các ô khác nhau giữa hai nghiệm (phản chứng khi MULTIPLE)"""
        if self.solution is None or self.second_solution is None:
            return ()
        return tuple(c for c in self.solution if self.solution[c] is not self.second_solution[c])


def check_clues_uniqueness(
    board: Board,
    clues: Iterable[Clue],
    known: Mapping[Cell, Status] | None = None,
    time_limit: float | None = None,
) -> UniquenessResult:
    """Kiểm tra bộ clue có đúng một nghiệm trên board hay không.
    known: status của các thẻ mở sẵn (public knowledge), được thêm vào CNF dưới dạng unit clause"""
    vmap = VariableMap(board)
    cnf = encode_clues(clues, vmap)
    for cell, status in (known or {}).items():
        v = vmap.var(cell)            # dùng đúng tên hàm ánh xạ ô -> biến C_i
        cnf.add_clause([v if status is Status.CRIMINAL else -v])
    encoding = compute_stats(cnf, vmap)
    n = vmap.max_var

    total = SolverStats()
    calls = 0

    def result(status, first=None, second=None) -> UniquenessResult:
        return UniquenessResult(status, first, second, calls, total, encoding)

    # Lần 1: tìm một nghiệm
    try:
        calls += 1
        first = solve(cnf, num_vars=n, time_limit=time_limit)
    except SolverTimeout as exc:
        total.merge(exc.stats)
        return result(UniquenessStatus.TIMEOUT)
    total.merge(first.stats)
    if not first.sat:
        return result(UniquenessStatus.NO_SOLUTION)
    solution = vmap.decode(first.model)

    # Lần 2: chặn nghiệm vừa tìm, chỉ trên biến chính
    blocked = cnf.copy()
    blocked.add_clause([-v if first.model[v] else v for v in range(1, vmap.num_main + 1)])
    try:
        calls += 1
        second = solve(blocked, num_vars=n, time_limit=time_limit)
    except SolverTimeout as exc:
        total.merge(exc.stats)
        return result(UniquenessStatus.TIMEOUT, solution)
    total.merge(second.stats)
    if not second.sat:
        return result(UniquenessStatus.UNIQUE, solution)
    return result(UniquenessStatus.MULTIPLE, solution, vmap.decode(second.model))


def check_puzzle_uniqueness(puzzle: PuzzleFull, time_limit: float | None = None) -> UniquenessResult:
    """Kiểm tra puzzle đầy đủ: mọi clue của mọi thẻ + status của thẻ mở sẵn.
    Status của thẻ úp (đáp án ẩn) không được đưa vào CNF"""
    known = {c: puzzle.solution[c] for c in puzzle.initially_open}
    return check_clues_uniqueness(puzzle.board, puzzle.clues.values(), known=known, time_limit=time_limit)