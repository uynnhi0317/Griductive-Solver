"""
Thu thập số liệu thực nghiệm cho một lần chạy hệ thống trên một puzzle

Các nhóm số liệu:
+ Mã hoá: số biến chính, biến phụ, mệnh đề
    - full_*: CNF của toàn bộ clue (kể cả thẻ úp) + status thẻ mở sẵn, lấy từ uniqueness check
    - kb0_* / kb_final_*: KB_t lúc bắt đầu và lúc agent dừng, dựng lại bằng build_kb từ PublicState
+ SAT: số lần gọi solver của agent, của engine (phán xử verdict) và tổng
+ Solver: decisions, propagations, pure literals, backtracks, thời gian trong solver
  (cộng dồn mọi truy vấn của agent và engine trong vòng suy diễn)
+ Suy diễn: số bước
+ Runtime: thời gian thực (wall clock) của vòng suy diễn và của uniqueness check
+ Uniqueness: trạng thái, số SAT call và số liệu solver, tách riêng khỏi vòng suy diễn

Quy ước:
+ Mọi hàm trả về dict có thứ tự khoá cố định, khớp với SUMMARY_FIELDS
+ Lần chạy lỗi chỉ có một phần khoá, các cột còn lại để trống khi ghi CSV
+ Module chỉ đọc kết quả đã có (trace, history của engine, PublicState), không gọi lại solver
"""

import time
from dataclasses import dataclass
from typing import Any, Iterator

from agent.trace import DeductionTrace
from agent.uniqueness import UniquenessResult
from engine.game_engine import GameEngine
from game.public_state import PublicState
from game.puzzle_loader import PuzzleFull
from logic.encoding_stats import EncodingStats
from logic.kb_builder import build_kb
from solver.stats import SolverStats

# Cột của file tổng kết, một dòng cho mỗi (puzzle, chế độ, lần chạy)
SUMMARY_FIELDS: tuple[str, ...] = (
    # Định danh lần chạy
    "puzzle_id", "size", "file", "model_reuse", "run",
    # Kết quả
    "status", "verdicts_correct", "error",
    # Mã hoá
    "full_main_vars", "full_aux_vars", "full_clauses",
    "kb0_clauses", "kb_final_main_vars", "kb_final_aux_vars", "kb_final_clauses",
    # Suy diễn
    "initial_revealed", "steps", "unknown_left",
    # SAT
    "agent_sat_calls", "engine_sat_calls", "sat_calls", "skipped_queries",
    # Solver (vòng suy diễn)
    "decisions", "propagations", "pure_literals", "backtracks", "solver_time", "runtime",
    # Uniqueness check
    "uniqueness", "uniq_sat_calls", "uniq_decisions", "uniq_propagations", "uniq_backtracks",
    "uniq_solver_time", "uniq_runtime",
)

# Cột định danh được ghép vào đầu mỗi dòng của file trace chi tiết
STEP_ID_FIELDS: tuple[str, ...] = ("puzzle_id", "size", "model_reuse", "run")


@dataclass
class Stopwatch:
    """Đo thời gian thực của một khối lệnh"""
    elapsed: float = 0.0

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        # Vẫn ghi thời gian khi khối lệnh ném lỗi để dòng lỗi cũng có runtime
        self.elapsed = time.perf_counter() - self._start


# Mã hoá

def encoding_metrics(prefix: str, stats: EncodingStats) -> dict[str, int]:
    """Số biến chính, biến phụ, mệnh đề với tiền tố cột"""
    return {
        f"{prefix}_main_vars": stats.main_vars,
        f"{prefix}_aux_vars": stats.aux_vars,
        f"{prefix}_clauses": stats.clauses,
    }


def kb_metrics(initial: PublicState, final: PublicState) -> dict[str, int]:
    """
    Kích thước KB_t lúc bắt đầu và lúc dừng
    Dựng lại bằng build_kb (chỉ đọc PublicState) nên đúng là KB mà agent thấy, không lộ thông tin ẩn
    """
    kb0 = build_kb(initial).stats
    row = {"kb0_clauses": kb0.clauses}
    row.update(encoding_metrics("kb_final", build_kb(final).stats))
    return row


# Vòng suy diễn

def engine_stats(engine: GameEngine) -> SolverStats:
    """Cộng dồn số liệu solver của mọi truy vấn engine dùng để phán xử verdict"""
    total = SolverStats()
    for result in engine.history:
        for query in result.queries:
            total.merge(query.stats)
    return total


def engine_query_count(engine: GameEngine) -> int:
    """
    Số truy vấn engine dùng để phán xử verdict, đếm trên cùng nguồn engine.history với engine_stats
    Không lấy trace.engine_queries vì trace chỉ có các bước được chấp nhận, còn history giữ mọi lần nộp
    (vd. verdict bị từ chối dẫn tới AgentInvariantError) -> số lần gọi và số liệu solver luôn khớp nhau
    """
    return sum(result.sat_queries for result in engine.history)


def deduction_metrics(trace: DeductionTrace, engine: GameEngine) -> dict[str, Any]:
    """
    Số liệu của vòng suy diễn
    + sat_calls = truy vấn của agent (gồm lần phân loại cuối, kể cả truy vấn bị timeout)
      + truy vấn của engine (mỗi verdict nộp lên engine tự phân loại lại ô đó)
    + Phía agent lấy từ trace, phía engine lấy từ engine.history cho cả số lần gọi lẫn số liệu solver,
      nên sat_calls luôn đếm đúng tập truy vấn đã cộng vào decisions / propagations / backtracks
    """
    solver = trace.total_stats()
    solver.merge(engine_stats(engine))
    agent_calls = trace.agent_queries
    engine_calls = engine_query_count(engine)
    return {
        "status": trace.status.value,
        "initial_revealed": len(trace.initial_clue_ids),
        "steps": trace.num_steps,
        "unknown_left": " ".join(trace.final_unknown),
        "agent_sat_calls": agent_calls,
        "engine_sat_calls": engine_calls,
        "sat_calls": agent_calls + engine_calls,
        "skipped_queries": trace.skipped_queries,
        "decisions": solver.decisions,
        "propagations": solver.propagations,
        "pure_literals": solver.pure_literals,
        "backtracks": solver.backtracks,
        "solver_time": solver.runtime,
    }


def verdicts_correct(puzzle: PuzzleFull, state: PublicState) -> bool:
    """
    Kiểm tra chéo phía harness: mọi verdict đã chứng minh đều khớp đáp án
    Chỉ benchmark được đọc đáp án để kiểm tra, agent không bao giờ thấy hàm này
    """
    return all(puzzle.solution[cell] is status for cell, status in state.verdicts().items())


def step_rows(trace: DeductionTrace) -> Iterator[dict[str, Any]]:
    """Từng bước của trace dưới dạng dict"""
    for step in trace.steps:
        yield step.as_dict()


# Uniqueness check

def uniqueness_metrics(result: UniquenessResult, runtime: float) -> dict[str, Any]:
    """Số liệu của uniqueness check trên bộ clue đầy đủ, kèm kích thước CNF đầy đủ"""
    row: dict[str, Any] = {
        "uniqueness": result.status.value,
        "uniq_sat_calls": result.sat_calls,
        "uniq_decisions": result.stats.decisions,
        "uniq_propagations": result.stats.propagations,
        "uniq_backtracks": result.stats.backtracks,
        "uniq_solver_time": result.stats.runtime,
        "uniq_runtime": runtime,
    }
    row.update(encoding_metrics("full", result.encoding))
    return row