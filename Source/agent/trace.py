"""
Deduction trace của Logic Agent

Mỗi bước suy diễn ghi lại:
+ step: số thứ tự bước (bắt đầu từ 1)
+ active_clue_ids: định danh các clue đang có trong KB_t (trước khi lật thẻ của bước này)
+ sat_queries: số lần agent gọi solver để phân loại state (gồm truy vấn kiểm tra KB_t)
+ verdict: verdict ép buộc mà agent chọn và nộp cho engine
+ revealed_clue_id: clue mới lộ sau khi verdict được chấp nhận

Quy ước:
+ Truy vấn của agent và truy vấn engine dùng để phán xử được đếm riêng,
engine tự phân loại lại ô được nộp, agent không thể bỏ qua bước đó
+ Bước kết thúc (SOLVED / AMBIGUOUS / INCONSISTENT / TIMEOUT) không tạo TraceStep,
mà ghi vào DeductionTrace.status, kèm các ô còn UNKNOWN nếu dừng vì ambiguous
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from game.board import Board
from game.cell import Cell
from solver.stats import SolverStats

from .entailment import Verdict


class AgentStatus(Enum):
    """Trạng thái của agent sau khi chạy"""
    RUNNING = "RUNNING"            # chưa tới trạng thái kết thúc
    SOLVED = "SOLVED"              # mọi ô đã có verdict
    AMBIGUOUS = "AMBIGUOUS"        # KB_t SAT nhưng không ô nào bị ép buộc, agent không đoán
    INCONSISTENT = "INCONSISTENT"  # KB_t UNSAT
    TIMEOUT = "TIMEOUT"            # một SAT query vượt time_limit

    @property
    def is_terminal(self) -> bool:
        """Agent đã dừng hay chưa"""
        return self is not AgentStatus.RUNNING


@dataclass(frozen=True)
class TraceStep:
    """Một bước suy diễn: phân loại state, chọn verdict ép buộc, nộp cho engine"""
    step: int                              # số thứ tự bước, bắt đầu từ 1
    active_clue_ids: tuple[str, ...]       # các clue đang có trong KB_t trước khi lật thẻ, theo thứ tự lật
    forced_cells: tuple[str, ...]          # mọi ô bị ép buộc tại bước này, theo row-major
    unknown_cells: tuple[str, ...]         # các ô còn UNKNOWN tại bước này
    cell: Cell                             # ô được chọn (ô ép buộc đầu tiên theo row-major)
    verdict: Verdict                       # verdict đã được engine chấp nhận
    sat_queries: int                       # truy vấn của agent
    skipped_queries: int                   # truy vấn agent bỏ qua nhờ ModelPool
    engine_queries: int                    # truy vấn engine dùng để phán xử verdict
    stats: SolverStats                     # cộng dồn truy vấn của agent tại bước này
    revealed_clue_id: str | None           # clue mới lộ sau khi lật thẻ (= nhãn ô vừa lật)

    def describe(self, board: Board) -> str:
        """Một dòng mô tả bước"""
        clues = _names(board, self.active_clue_ids)
        line = (f"Step {self.step}: clues [{clues}] -> {board.character_at(self.cell).name} "
                f"is {self.verdict.value}, {self.sat_queries} SAT queries")
        if self.revealed_clue_id is not None:
            line += f"; revealed {_names(board, (self.revealed_clue_id,))}'s clue"
        return line

    def as_dict(self) -> dict[str, Any]:
        """Khoá ổn định để ghi CSV / JSON"""
        return {
            "step": self.step,
            "active_clues": " ".join(self.active_clue_ids),
            "num_active_clues": len(self.active_clue_ids),
            "forced_cells": " ".join(self.forced_cells),
            "unknown_cells": " ".join(self.unknown_cells),
            "cell": self.cell.label,
            "verdict": self.verdict.value,
            "sat_queries": self.sat_queries,
            "skipped_queries": self.skipped_queries,
            "engine_queries": self.engine_queries,
            **self.stats.as_dict(),
            "revealed_clue": self.revealed_clue_id or "",
        }


@dataclass
class DeductionTrace:
    """Toàn bộ quá trình suy diễn của agent trên một puzzle"""
    puzzle_id: str                                                  # id của puzzle đang giải (vd. "3x3_01")
    initial_clue_ids: tuple[str, ...] = ()                          # các clue mở sẵn lúc bắt đầu, theo thứ tự lật
    steps: list[TraceStep] = field(default_factory=list)            # các bước đã thực hiện, theo thứ tự
    status: AgentStatus = AgentStatus.RUNNING                       # trạng thái hiện tại; RUNNING cho tới khi dừng
    final_unknown: tuple[str, ...] = ()                             # các ô còn UNKNOWN khi dừng (AMBIGUOUS)
    final_queries: int = 0                                          # truy vấn của lần phân loại cuối (không dẫn tới verdict)
    final_stats: SolverStats = field(default_factory=SolverStats)   # số liệu solver của lần phân loại cuối (kể cả khi TIMEOUT)

    @property
    def num_steps(self) -> int:
        """Số verdict đã nộp"""
        return len(self.steps)

    @property
    def agent_queries(self) -> int:
        """Tổng truy vấn của agent, gồm cả lần phân loại cuối"""
        return sum(s.sat_queries for s in self.steps) + self.final_queries

    @property
    def engine_queries(self) -> int:
        """Tổng truy vấn engine dùng để phán xử các verdict"""
        return sum(s.engine_queries for s in self.steps)

    @property
    def total_queries(self) -> int:
        """Tổng truy vấn của agent và engine"""
        return self.agent_queries + self.engine_queries

    @property
    def skipped_queries(self) -> int:
        """Tổng truy vấn agent bỏ qua nhờ ModelPool"""
        return sum(s.skipped_queries for s in self.steps)

    def total_stats(self) -> SolverStats:
        """Cộng dồn số liệu solver của mọi truy vấn của agent"""
        total = SolverStats()
        for s in self.steps:
            total.merge(s.stats)
        total.merge(self.final_stats)
        return total

    def summary(self) -> dict[str, Any]:
        """Một dòng tổng kết cho benchmark"""
        return {
            "puzzle_id": self.puzzle_id,
            "status": self.status.value,
            "steps": self.num_steps,
            "agent_queries": self.agent_queries,
            "engine_queries": self.engine_queries,
            "skipped_queries": self.skipped_queries,
            **self.total_stats().as_dict(),
            "unknown_left": " ".join(self.final_unknown),
        }

    def to_text(self, board: Board) -> str:
        """Trace dạng văn bản, mỗi bước một dòng, ô ghi bằng tên nhân vật"""
        lines = [f"Puzzle {self.puzzle_id}: initial clues [{_names(board, self.initial_clue_ids)}]"]
        lines += [s.describe(board) for s in self.steps]
        end = f"Finished: {self.status.value}"
        if self.final_unknown:
            end += f", still UNKNOWN: {_names(board, self.final_unknown)}"
        lines.append(end)
        lines.append(f"Total: {self.num_steps} steps, {self.agent_queries} agent SAT queries, "
                     f"{self.engine_queries} engine SAT queries; {self.total_stats()}")
        return "\n".join(lines)


def _names(board: Board, labels: tuple[str, ...]) -> str:
    """Đổi nhãn ô sang tên nhân vật, '-' nếu rỗng"""
    return ", ".join(board.character_at(Cell.parse(label)).name for label in labels) or "-"
